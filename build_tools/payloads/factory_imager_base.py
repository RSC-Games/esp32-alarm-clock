from bootrom import reboot_to_uart, reboot_to_recovery
from ucrypto.ufastrsa.rsa import RSA
from __nvs_perms import ReadOnlyNVS
from vfs import mount, VfsLfs2
from micropython import const
from binascii import hexlify
from esp32 import Partition
from hashlib import sha256
from machine import reset
import time
import logs
import sys
import gc

#################################### CONFIGURATION ######################################

# Most devices with the secure bootrom share the same UART boot public key. Only
# allow the below product type to run this signed copy of the payload.
_PRODUCT_ID = const("esp32_alarm_clock")

# Debugging flag. Not recommended for production.
_SKIP_FORMAT_NOR = const(True)

# Do not perform a filesystem format and do not reinject recovery to the filesystem.
# Instead, the tool only writes the received <app_name>.img to NOR, then reboots.
_FAST_APP_REIMAGE = const(True)

# Skip running the command parser after recovery injection. Useful for only formatting
# the filesystem and reinstalling recovery.img. Speeds up device recovery but requires
# an internet connection to install the main device firmware image.
_SKIP_COMMAND_PARSER = const(False)

################################## END CONFIGURATION ####################################

# Full recovery filesystem image (must be small to stay under the bootrom limit)
RECOVERY_IMG = bytes()

# Recovery hash is pre-computed (to prevent injecting a bad image)
RECOVERY_IMG_SHA256 = bytes()

# Device imager protocol (data link layer). Mostly reused from bootrom
_IMAGER_CONN_RETRIES = const(10)
_IMAGER_BANNER = const(b"\x55IMAGER_COMM_DEV\xAA")
_IMAGER_CONN_ESTABLISHED = const(b"\xAAIMAGER_COMM_PC\x55")

# Header contains 8b header prefix then 4 byte length field
# Meant to be used with struct.pack(). crc32 is calculated over the entire
# packet minus the last 4 bytes (left as zeroes)
# RCM packet has:
# - 4 byte header
# - 2 byte flags field (0b(ready)XXXXX(invalid)(badcrc))
# - 2 byte length field (payload size + 4 bytes crc32)
# - n - 4 bytes data payload
# - 4 bytes crc32
_IMAGER_HEADER = const("<4sHH")
_IMAGER_PACKET = const("<8s{}sI")
_IMAGER_HEADER_PREFIX = const(b"\x64RCM")
_IMAGER_FLAG_READY = const(0x80)
_IMAGER_FLAG_ACCEPT = const(0x40)
_IMAGER_FLAG_COMMAND_ERROR = const(0x4)
_IMAGER_FLAG_INVALID_PACKET = const(0x2)
_IMAGER_FLAG_CORRUPT_PACKET = const(0x1)

# RCM (transport layer)
# - 2 byte command, 
# - n - 2 bytes payload
_IMAGER_DATA_PACKET = const("<H{}s")

# WRITE_FIRM command payload has
# - 512 bytes signature
# - n - 512 bytes data
_IMAGER_CMD_WRITE_FIRM = const(3)
_IMAGER_CMD_R2B_UART = const(4)
_IMAGER_CMD_R2B_RECOVERY = const(5)
_IMAGER_CMD_REBOOT = const(6)


def mount_internal_fs() -> bool:
    """
    Format the internal NOR flash data partition. Should work in nearly all cases
    excluding dying flash or electrical interference (basically hardware issues).
    This will also transparently mount the NOR flash at root for future operations.
    """

    if not _SKIP_FORMAT_NOR:
        logs.print_warning("imager", "FORMATTING NOR! ALL DATA WILL BE ERASED!")
        print("waiting 5s", end="")

        for i in range(5):
            time.sleep(1)
            print(".", end="")
        
        print("GO")

    data_partitions = Partition.find(Partition.TYPE_DATA, label="vfs")

    if len(data_partitions) == 0:
        # Partition unmountable (since it cannot be found)
        logs.print_error("imager", "cannot locate data partition")
        return False

    try: 
        if not _SKIP_FORMAT_NOR:
            VfsLfs2.mkfs(data_partitions[0])
        
        mount(data_partitions[0], "/")

    except OSError as ie:
        logs.print_error("imager", "nor format failure. hardware issue likely")
        sys.print_exception(ie)
        return False

    return True


def write_recovery_img() -> bool:
    """
    Install the embedded recovery image if it's not corrupt. Even though the payload
    size is limited to 32kB, 516B of that payload are used by packet structures and
    are therefore unusable by the booted firm.
    """

    logs.print_warning("imager", "installing recovery.img")

    # Verify recovery image hash (avoid writing a corrupt recovery image even
    # though in theory these payloads are signed).
    recovery_hash = sha256(RECOVERY_IMG).digest()

    if recovery_hash != RECOVERY_IMG_SHA256:
        logs.print_error("imager", f"bad recovery.img; calc sha{hexlify(recovery_hash)}")
        return False
    
    with open("recovery.img", "wb") as recovery_f:
        recovery_f.write(RECOVERY_IMG)

    return True


def do_command_parser(nvs: ReadOnlyNVS):
    # TODO: Steal from the bootrom command parser (with more commands)    
    from select import poll, POLLIN
    from binascii import crc32
    from io import BytesIO
    import struct
    import time

    logs.print_warning("imager", "entering command parser")

    rcm_pipe_in = sys.stdin.buffer
    rcm_pipe_out = sys.stdout.buffer

    # Stdin can't poll itself (and stdin/stdout actively prevents directly using
    # the UART)
    read_poll = poll()
    read_poll.register(rcm_pipe_in, POLLIN)

    def get_n_bytes(n: int, timeout_ms: int) -> bytes:
        in_buf = BytesIO()
        buf_len = 0

        end_time = time.ticks_add(time.ticks_ms(), timeout_ms)

        while (timeout_ms == -1 or time.ticks_diff(time.ticks_ms(), end_time) < 0) and buf_len < n:
            if len(read_poll.poll(1)) != 0:
                char = rcm_pipe_in.read(1)
                in_buf.write(char)
                buf_len += 1

        return in_buf.getvalue()
    
    connected = False
        
    # Announce startup to connected device (if any)
    for _ in range(0, _IMAGER_CONN_RETRIES):
        rcm_pipe_out.write(_IMAGER_BANNER)
        
        # Wait for the connection accepted flag (if it exists)
        read_chars = get_n_bytes(len(_IMAGER_CONN_ESTABLISHED), 500)

        # Connection accepted
        if read_chars == _IMAGER_CONN_ESTABLISHED:
            connected = True
            break

        gc.collect()

    if not connected:
        # Fatal: no pc connection
        print()
        logs.print_warning("imager", "conn timed out")
        reboot_to_uart()

    # Command packet parser.
    header_sz = struct.calcsize(_IMAGER_HEADER)

    def build_packet(flags: int, payload: bytes) -> bytearray:
        payload_sz = len(payload)
        header = struct.pack(_IMAGER_HEADER, _IMAGER_HEADER_PREFIX, flags, payload_sz + 4)
        data_packet = bytearray(header_sz + payload_sz + 4)

        struct.pack_into(_IMAGER_PACKET.format(payload_sz), data_packet, 0, header, payload, 0)
        #crc = crc32(data_packet)
        struct.pack_into("<I", data_packet, header_sz + payload_sz, crc32(data_packet))
        return data_packet
    
    # Finish 3 way handshake
    conn_packet = build_packet(_IMAGER_FLAG_READY, b"DEV_READY")
    rcm_pipe_out.write(conn_packet)
    del conn_packet

    while True:    
        gc.collect()

        # Wait for the header to be available.
        header = get_n_bytes(header_sz, -1)

        header_magic, flags, size = struct.unpack(_IMAGER_HEADER, header)
        del header

        # Ensure valid header (can't really read anything with an illegal header)
        if header_magic != _IMAGER_HEADER_PREFIX:
            err_packet = build_packet(_IMAGER_FLAG_CORRUPT_PACKET, b"BAD_HEADER")
            rcm_pipe_out.write(err_packet)
            continue

        # Max payload size is 32 kB to avoid memory allocation issues in the FIRM.
        # TODO: circumvent packet size limits with layer 2 framing
        if size >= 65536:
            err_packet = build_packet(_IMAGER_FLAG_INVALID_PACKET, b"E_TOO_LONG")
            rcm_pipe_out.write(err_packet)

            # Read everything left in the packet anyway (but don't allocate memory for it)
            # to reduce the chance of desynchronizing with the PC
            dump_buf = bytearray(4096)
            rcm_pipe_in.read(size % len(dump_buf))

            for _ in range(size // len(dump_buf)):
                rcm_pipe_in.readinto(dump_buf)  # type: ignore

            continue

        # NOTE: Flags are a DONT CARE (ignore them)
        # Read the rest of the packet payload.
        packet = bytearray(header_sz + size)
        payload_section = memoryview(packet)[header_sz:]

        struct.pack_into(_IMAGER_HEADER, packet, 0, header_magic, flags, size)

        # Ensure CRC section is zeroed
        rcm_pipe_in.readinto(payload_section, size - 4)  # type: ignore
        recv_crc = int.from_bytes(rcm_pipe_in.read(4), "little")

        # Ensure packet hasn't been corrupted during transfer.
        if crc32(packet) != recv_crc:
            err_packet = build_packet(_IMAGER_FLAG_CORRUPT_PACKET, b"BAD_CRC")
            rcm_pipe_out.write(err_packet)
            continue

        del packet, header_magic, flags, size, recv_crc

        # Packet accepted
        conn_packet = build_packet(_IMAGER_FLAG_ACCEPT, b"OK")
        rcm_pipe_out.write(conn_packet)
        del conn_packet

        # Process packet data
        packet_cmd = int.from_bytes(payload_section[:2], 'little')
        transport_layer_payload = payload_section[2:-4]

        # Should use a switch statement/LUT but ehh
        if packet_cmd == _IMAGER_CMD_WRITE_FIRM:  # WRITE_FIRM
            firm_name = nvs.get_str("firm")

            with open(f"{firm_name}.img.sig", "wb") as f:
                f.write(transport_layer_payload[:512])
            
            with open(f"{firm_name}.img", "wb") as f:
                f.write(transport_layer_payload[512:])

        elif packet_cmd == _IMAGER_CMD_R2B_UART:  # reboot to uart mode
            time.sleep_ms(10)
            reboot_to_uart()

        elif packet_cmd == _IMAGER_CMD_R2B_RECOVERY:  # reboot to recovery.img
            time.sleep_ms(50)
            reboot_to_recovery()

        elif packet_cmd == _IMAGER_CMD_REBOOT:  # reboot
            time.sleep_ms(50)
            reset()

        else:
            err_packet = build_packet(_IMAGER_FLAG_COMMAND_ERROR, f"CMD:{packet_cmd}".encode())
            rcm_pipe_out.write(err_packet)


# For an alarm clock to boot, it needs to have the following provisioned:
# - NVS MUST BE INITIALIZED (done by boot_nvs_imager)
# - Internal filesystem must be formatted and usable
# - <app_name>.img/recovery.img must be present and bootable
#
# This tool ensures the second two requirements are satisfied.
# TODO: This tool can also inject <app_name>.img but it must be loaded via
# another channel (another command processor).
# TODO: As long as the bootrom NOR/SD bootflow is broken, a stub bootloader must
# be injected after this to fully boot the device.
#
# Due to the size of this payload, it does not perform chainloading and will
# reset the system so the bootrom bootflow is observed.
#
# NOTE: To avoid writing another command parser, recovery.img will be injected 
# as part of this boot stub. However, THAT MEANS IT IS SUBJECT TO THE 32kB MAX
# PAYLOAD SIZE IMPOSED BY THE BOOTROM!
def firm_entry(pubkey: RSA, nvs: ReadOnlyNVS):
    logs.print_info("imager", f"{_PRODUCT_ID} imager firm booted")

    if nvs.get_str("prod_id") != _PRODUCT_ID:
        logs.print_error("imager", f"bad product id")
        return
    
    # internal fs format required/recovery.img injection
    if not mount_internal_fs():
        time.sleep(5)
        return

    if not _FAST_APP_REIMAGE:        
        if not write_recovery_img():
            time.sleep(5)
            return

    if not _SKIP_COMMAND_PARSER:
        # command parser time (for installing firmware files)
        do_command_parser(nvs)

    logs.print_info("imager", "imager firm DONE")