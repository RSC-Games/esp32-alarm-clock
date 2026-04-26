from . import output

import threading
import binascii
import hashlib
import struct
import serial
import time

# Device imager protocol (data link layer). Mostly reused from bootrom
_IMAGER_CONN_RETRIES = 10
_IMAGER_CONN_MAX_BYTES_TO_TIMEOUT = 512
_IMAGER_BANNER = b"\x55IMAGER_COMM_DEV\xAA"
_IMAGER_CONN_ESTABLISHED = b"\xAAIMAGER_COMM_PC\x55"

# Header contains 8b header prefix then 4 byte length field
# Meant to be used with struct.pack(). crc32 is calculated over the entire
# packet minus the last 4 bytes (left as zeroes)
# RCM packet has:
# - 4 byte header
# - 2 byte flags field (0b(ready)(okay)XXXX(invalid)(badcrc))
# - 2 byte length field (payload size + 4 bytes crc32)
# - n - 4 bytes data payload
# - 4 bytes crc32
_IMAGER_HEADER = "<4sHH"
_IMAGER_HEADER_LEN = struct.calcsize(_IMAGER_HEADER)
_IMAGER_PACKET = "<8s{}sI"
_IMAGER_HEADER_PREFIX = b"\x64RCM"
_IMAGER_FLAG_READY = 0x80
_IMAGER_FLAG_ACCEPT = 0x40
_IMAGER_FLAG_COMMAND_ERROR = 0x4
_IMAGER_FLAG_INVALID_PACKET = 0x2
_IMAGER_FLAG_CORRUPT_PACKET = 0x1

# RCM (transport layer)
# - 2 byte command, 
# - n - 2 bytes payload
_IMAGER_DATA_PACKET = "<H{}s"

# WRITE_FIRM command payload has
# - 512 bytes signature
# - n - 512 bytes data
_IMAGER_CMD_WRITE_FIRM = 3
_IMAGER_CMD_R2B_UART = 4
_IMAGER_CMD_R2B_RECOVERY = 5
_IMAGER_CMD_REBOOT = 6


def _establish_connection(uart: serial.Serial) -> bool:
    """
    Attempt connection to the device 10 times. After those 10 times,
    if a valid header is not found, give up.

    :param uart: Created serial object representing this device.
    :return: Whether the device could be connected to.
    """

    for i in range(_IMAGER_CONN_RETRIES):
        # Seek forward in the input stream until a start byte is found.
        found_end_byte = False

        for _ in range(_IMAGER_CONN_MAX_BYTES_TO_TIMEOUT):
            c = uart.read(1)
            print(c.decode(errors="replace"), end="", flush=True)

            if c == _IMAGER_BANNER[-1].to_bytes(1):
                found_end_byte = True
                break

        if not found_end_byte:
            output.print_tool(f"no found start byte; retrying ({i+1}/{_IMAGER_CONN_RETRIES})")
            time.sleep(0.1)
            continue
            
        # Wait for the full header (header will be sent right after a newline)
        while uart.in_waiting < len(_IMAGER_BANNER):
            pass

        if uart.read(len(_IMAGER_BANNER)) == _IMAGER_BANNER:
            print()
            output.print_tool("got header; sending connection request...")
            uart.write(_IMAGER_CONN_ESTABLISHED)
            uart.flush()
            return True
        
        output.print_tool(f"connection attempt failed; retrying ({i+1}/{_IMAGER_CONN_RETRIES})")
        
    return False


def _build_datalink_packet(flags: int, payload: bytes) -> bytearray:
    """
    Build a UART packet to send to the bootrom with the provided flags and payload.
    """

    payload_sz = len(payload)
    header = struct.pack(_IMAGER_HEADER, _IMAGER_HEADER_PREFIX, flags, payload_sz + 4)
    data_packet = bytearray(_IMAGER_HEADER_LEN + payload_sz + 4)

    struct.pack_into(_IMAGER_PACKET.format(payload_sz), data_packet, 0, header, payload, 0)
    struct.pack_into("<I", data_packet, _IMAGER_HEADER_LEN + payload_sz, binascii.crc32(data_packet))
    return data_packet


def _get_datalink_packet(uart: serial.Serial) -> tuple[int, bytes] | None:
    """
    Get a full packet from the device and return its undecoded contents and flags.

    :param uart: The device port
    :return: Packet flags and the raw payload bytes
    """

    # Wait for the header to be available.
    header = uart.read(_IMAGER_HEADER_LEN)
    header_magic, flags, size = struct.unpack(_IMAGER_HEADER, header)

    # Ensure valid header (can't really read anything with an illegal header)
    # NOTE: This will spam packets to the host until the payload is fully transferred
    # unless transmission is cut off early.
    if header_magic != _IMAGER_HEADER_PREFIX:
        raise OSError(f"got illegal header magic {header_magic}")

    # NOTE: Flags are a DONT CARE (ignore them)
    # Read the rest of the packet payload.
    packet = bytearray(_IMAGER_HEADER_LEN + size)
    payload_section = memoryview(packet)[_IMAGER_HEADER_LEN:-4]

    struct.pack_into(_IMAGER_HEADER, packet, 0, header_magic, flags, size)

    # Ensure CRC section is zeroed
    uart.readinto(payload_section)
    recv_crc = int.from_bytes(uart.read(4), "little")

    packet_crc = binascii.crc32(packet)

    # Ensure packet hasn't been corrupted during transfer.
    if packet_crc != recv_crc:
        print(f"warning: packet corrupt: got crc {packet_crc} recv'd {recv_crc}")
        print(f"packet contents {packet}")
        return None
    
    return int(flags), bytes(payload_section)

def connect(uart: serial.Serial) -> bool:
    """
    Create a new connection to the device. Serial port is already open
    (since that's required for a download boot payload)
    The returned device will be fully initialized and in UART boot mode.

    :param uart: The existing handle to the device.

    :throws OSError: When the serial port could not be connected to.
    """
    if not _establish_connection(uart):
        output.print_tool("connection attempt failed")
        return False
    
    if not device_is_ready(uart):
        output.print_tool("imager refused handshake")
        return False
    
    output.print_tool("connection succeeded; ready for commands")

    return True

def device_is_ready(uart: serial.Serial) -> bool:
    """
    Determine if the device is waiting for another command.

    :return: If the device is waiting for command issuance.
    """

    res = _get_datalink_packet(uart)

    if res is None:
        output.print_tool("response: bad crc")
        return False
    
    flags, payload = res

    output.print_tool(f"response: flags {flags} payload {payload}")

    return flags & (_IMAGER_FLAG_READY | _IMAGER_FLAG_ACCEPT) != 0


def upload_firm(uart: serial.Serial, firm_path: str) -> bool:
    firm_sig_path = f"{firm_path}.sig"

    with open(firm_path, "rb") as firm_f:
        firm_bytes = firm_f.read()
    
    with open(firm_sig_path, "rb") as sig_f:
        sig_bytes = sig_f.read()

    firm_array = bytearray(len(firm_bytes) + 512)
    firm_array[:2] = int.to_bytes(_IMAGER_CMD_WRITE_FIRM, 2, "little")
    firm_array[2:2 + 512] = sig_bytes
    firm_array[2 + 512:] = firm_bytes

    output.print_tool(f"uploading firm sha256 {hashlib.sha256(firm_bytes).hexdigest()} len {len(firm_array[2+512:])} B")

    packet = _build_datalink_packet(0, firm_array)
    uart.write(packet)

    if not device_is_ready(uart):
        output.print_tool(f"firm upload failed")
        return False
    
    return True

def reboot_to_uart(uart: serial.Serial) -> None:
    output.print_tool("rebooting device to uart boot")

    packet = _build_datalink_packet(0, int.to_bytes(_IMAGER_CMD_R2B_UART, 2, "little"))
    uart.write(packet)

    if not device_is_ready(uart):
        output.print_tool(f"software reboot to uart failed")

def reboot_to_recovery(uart: serial.Serial) -> None:
    output.print_tool("rebooting device to recovery.img")

    packet = _build_datalink_packet(0, int.to_bytes(_IMAGER_CMD_R2B_RECOVERY, 2, "little"))
    uart.write(packet)

    if not device_is_ready(uart):
        output.print_tool(f"reboot to recovery.img failed")

def reboot(uart: serial.Serial) -> None:
    output.print_tool("rebooting device to main firm.img")

    packet = _build_datalink_packet(0, int.to_bytes(_IMAGER_CMD_REBOOT, 2, "little"))
    uart.write(packet)

    #if not device_is_ready(uart):
    #    output.print_tool(f"software reboot to firm.img failed")