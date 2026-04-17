# Initial boot context.
# This file replaces the default MicroPython boot code. This means we have NO
# prior existing boot context (notably, NOR is not mounted) and so we must do
# that here.
# THIS BOOTLOADER IS NOT FULLY SECURE IN ISOLATION! It can protect your app
# from internet exploits and some local ones, but protection works best with
# full flash encryption ENABLED and either esp uart download boot disabled or
# esp secure boot (to prevent overwriting the interpreter ROM). Additionally,
# NVS lockout isn't fully hardened and would require modification to the mpy
# NVS driver (to prevent accessing the app NVS) to fully lock down. 

# NOTE: performing initial lockout (can be disabled in the mpy firmware). Idea
# is to prevent circumventing the secure boot chain with a keyboard interrupt.
import micropython
micropython.kbd_intr(-1)

from machine import reset, unique_id, Pin
from ucrypto.ufastrsa.rsa import RSA
from binascii import hexlify, crc32
from __nvs_perms import ReadOnlyNVS
from typing import NoReturn, Any
from vfs import mount
import time
import logs
import sys
import gc

#################################### CONFIGURATION ######################################

# Enforce signature checks permanently. Set this if using the secure bootloader
# for an application where end-user modification is not desirable.
_FORCE_SIGNATURE_VALIDATION = micropython.const(False)

# Force the boot NVS read-only whenever a payload is executed irrespective of the current
# NVS setting. This does not affect UART/USB recovery mode payloads.
_FORCE_NVS_LOCKOUT = micropython.const(False)

# Permanently disable SD booting. Set this if your device does not have an SD card
# slot (so it's literally infeasible to perform an SD boot).
_FORCE_DISABLE_SD_BOOT = micropython.const(False)

################################## END CONFIGURATION ####################################

# USB/UART recovery bootloader (data link layer)
_UART_RCM_DEFAULT_BAUD = micropython.const(115200)
_UART_RCM_CONN_RETRIES = micropython.const(10)
_UART_RCM_BANNER = micropython.const(b"\x55BOOT_RCM_RSC\xAA")
_UART_RCM_CONN_ESTABLISHED = micropython.const(b"\xAARSC_RCM_BOOT\x55")

# Header contains 8b header prefix then 4 byte length field
# Meant to be used with struct.pack(). crc32 is calculated over the entire
# packet minus the last 4 bytes (left as zeroes)
# RCM packet has:
# - 4 byte header
# - 2 byte flags field (0b(ready)XXXXX(invalid)(badcrc))
# - 2 byte length field (payload size + 4 bytes crc32)
# - n - 4 bytes data payload
# - 4 bytes crc32
_UART_RCM_HEADER = micropython.const("4s<H<H")
_UART_RCM_PACKET = micropython.const("6s<{}s<I")
_UART_RCM_HEADER_PREFIX = micropython.const(b"\x64RCM")
_UART_RCM_FLAG_READY = micropython.const(0x80)
_UART_RCM_FLAG_COMMAND_ERROR = micropython.const(0x4)
_UART_RCM_FLAG_INVALID_PACKET = micropython.const(0x2)
_UART_RCM_FLAG_CORRUPT_PACKET = micropython.const(0x1)

# RCM (transport layer)
# - 2 byte command, 
# - n - 2 bytes payload
_UART_RCM_DATA_PACKET = micropython.const("<H{}s")

# BOOT command payload has
# - 512 bytes signature
# - n - 512 bytes data
_UART_RCM_CMD_BOOT = micropython.const(2)

# Error reporting
_DEBUG_LED_GPIO = micropython.const(2)
_DEBUG_FLASH_LONG_MS = micropython.const(1000)
_DEBUG_FLASH_SHORT_MS = micropython.const(300)
_DEBUG_FLASH_OFF_MS = micropython.const(200)

_SD_BOOT_BUTTON = micropython.const(0)

_SD_BUS_SLOT = micropython.const(3)
_SD_BUS_FREQ = micropython.const(20_000_000)
_SD_BUS_SCK = micropython.const(14)
_SD_BUS_MISO = micropython.const(12)
_SD_BUS_MOSI = micropython.const(13)
_SD_BUS_CS = micropython.const(15)

# Display potential errors at rom boot time. Errors can and will be reported as
# LED flash codes (starting with long flashes, then short flashes). A short list
# of error codes will be displayed below. Long flashes indicate an error category,
# and short flashes indicate the specific error.
#
# PRE-BOOT ERRORS (1 long flash, repeats):
#   2 short: NVS not initialized (factory init not performed properly)
#   3 short: Internal FS unmountable (NOR wasn't formatted? factory)
#   4 short: SD card cannot be read (only when in SD boot mode)
#   5 short: SD card fs unmountable (SD is corrupt/unformatted)
#   6 short: bootrom internal error (some kind of crash)
#
# FIRMWARE PACKAGE BOOT ERRORS (2 long flashes, repeats):
#   1 short: cannot locate <firmware>.img in NOR
#   2 short: <firmware>.img missing/bad RSA signature
#   3 short: <firmware>.img version mismatch (firmware installed is older than NVS)
#   4 short: <firmware>.img hash on dbx blacklist (provided at update time in separate partition)
#   5 short: <firmware>.img unmountable (must be mounted as read-only)
#   6 short: cannot locate firm_boot.bin in <firmware>.img (also used for SD boot)
#
# SD BOOT ERRORS (3 long flashes, repeats):
#   1 short: cannot locate <firmware>.img on SD
#   2 short: <firmware>.img has bad RSA signature on SD
#   3 short: <firmware>.img version mismatch (firmware installed is older than NVS)
#   4 short: <firmware>.img hash on dbx blacklist (provided at update time in separate partition)
#   5 short: <firmware>.img unmountable (must be mounted as read-only)
#
# UART BOOT ERRORS (4 long flashes, immediate reboot)
#   1 short: failed to negotiate connection to pc
#   2 short: payload execution error
#   3 short: payload hash on dbx blacklist
#
# APPLICATION ERRORS (5 long flashes, immediate reboot):
#   1 short: exception in firmware; stack dumped, rebooting
#
# This function is NOT erased at boot lockout.
def _fatal_error_led(long_flashes: int, short_flashes: int, reboot: bool=False) -> NoReturn:
    led_internal = Pin(_DEBUG_LED_GPIO, Pin.OUT)

    def flash_led(delay_ms_on: int) -> None:
        led_internal.on()
        time.sleep_ms(delay_ms_on)
        led_internal.off()
        time.sleep_ms(_DEBUG_FLASH_OFF_MS)

    while True:
        for _ in range(0, long_flashes):
            flash_led(_DEBUG_FLASH_LONG_MS)
        for _ in range(0, short_flashes):
            flash_led(_DEBUG_FLASH_SHORT_MS)

        if reboot:
            reset()


# Avoid accidentally importing any unverified files on the raw filesystem
#
# NOTE: Pointer erased at boot lockout.
def _boot_clean_syspath() -> None:
    sys.path.clear()
    sys.path.append(".frozen")


# Load the boot nvs. Key is the device unique id XOR the public key modulus.
# The boot NVS has the following REQUIRED keys:
# X "prod_id" (blob): product name/id (identical for all devices of a given product line)
# X "prod_id_len" (int): length of the product id
# - "serial" (blob): contains the device serial (randomly generated at provisioning)
# - "serial_len" (int): contains the length of the device serial
# - "firm" (blob): contains the name of the NOR firmware.img app to load
# - "firm_len" (int): length of the name of the NOR image
# - "version" (int): version id of the firmware image to load
# X "dbx" (blob): contains blacklisted hashes (not currently used)
# X "dbx_len" (int): length of the dbx entry
# - "nvs_lock" (int): disallow writes to the fields in this NVS
# - "en_sd_boot" (int): allow booting from an SD card
# - "en_insecure_boot" (int): disable signature validation and allow booting any payload
# - "boot_mpy" (int): look for firm_boot.mpy rather than firm_boot.bin when loading 
#
# NOTE: Pointer erased at boot lockout.
def _boot_load_nvs(pubkey: RSA, uart_boot_on_fail: bool) -> ReadOnlyNVS:
    # Mask off the first 7 bytes (nvs names are limited to 15 bytes)
    nvs_uid = pubkey.n ^ int.from_bytes(unique_id(), "little") & 0x00FFFFFFFFFFFFFF
    nvs_name = b"k" + hexlify(int.to_bytes(nvs_uid, 7, "little", signed=False))

    logs.print_info("boot", f"loading boot nvs {nvs_name}")
    boot_nvs = ReadOnlyNVS(nvs_name.decode())

    try:
        # Test namespace existence by reading the serial (will panic if nonexistent).
        serial = boot_nvs.get_str("serial")

        logs.print_info("boot", f"unit serial is {serial}")
        return boot_nvs

    except OSError:
        if uart_boot_on_fail:
            _boot_launch_uart_rcm(pubkey, boot_nvs)

        # ERR_NON_INITIALIZED_NVS
        _fatal_error_led(1, 2)


# Launch the recovery mode listener on UART0. Log messages will no
# longer be printed as long as the rcm listener is running.
#
# NOTE: Pointer erased at boot lockout.
def _boot_launch_uart_rcm(pubkey: RSA, nvs: ReadOnlyNVS) -> NoReturn:
    from machine import UART
    import struct

    logs.print_info("boot", "entered USB/UART recovery mode boot mode")

    sys.stdout.flush()
    rcm_pipe = UART(0, baudrate=_UART_RCM_DEFAULT_BAUD)
    connected = False

    # Announce startup to connected device (if any)
    for _ in range(0, _UART_RCM_CONN_RETRIES):
        rcm_pipe.write(_UART_RCM_BANNER)
        time.sleep_ms(100)
        
        # Wait for the connection accepted flag (if it exists)
        if rcm_pipe.any() < len(_UART_RCM_CONN_ESTABLISHED):
            continue

        # Connection accepted
        if rcm_pipe.read(len(_UART_RCM_CONN_ESTABLISHED)) == _UART_RCM_CONN_ESTABLISHED:
            connected = True
            break

    if not connected:
        # Fatal: no pc connection
        _fatal_error_led(4, 1, reboot=True)

    # Command packet parser.
    header_sz = struct.calcsize(_UART_RCM_HEADER)

    def build_packet(flags: int, payload: bytes) -> bytearray:
        payload_sz = len(payload)
        header = struct.pack(_UART_RCM_HEADER, _UART_RCM_HEADER_PREFIX, flags, payload_sz + 4)
        data_packet = bytearray(header_sz + payload_sz + 4)

        struct.pack_into(_UART_RCM_PACKET.format(payload_sz), data_packet, 0, header, payload, 0)
        struct.pack_into("<I", data_packet, header_sz + payload_sz, crc32(data_packet))
        return data_packet

    while True:
        # Wait for the header to be available.
        if rcm_pipe.any() < header_sz:
            continue

        header_magic, flags, size = struct.unpack(_UART_RCM_HEADER, rcm_pipe.read(header_sz))

        # Ensure valid header (can't really read anything with an illegal header)
        # NOTE: This will spam packets to the host until the payload is fully transferred
        # unless transmission is cut off early.
        if header_magic != _UART_RCM_HEADER_PREFIX:
            err_packet = build_packet(_UART_RCM_FLAG_INVALID_PACKET, b"BAD_HEADER")
            rcm_pipe.write(err_packet)
            rcm_pipe.flush()
            continue

        # NOTE: Flags are a DONT CARE (ignore them)
        # Read the rest of the packet payload.
        packet = bytearray(header_sz + size)
        payload_section = memoryview(packet)[header_sz:]

        struct.pack_into(_UART_RCM_HEADER, packet, 0, header_magic, flags, size)

        # Ensure CRC section is zeroed
        rcm_pipe.readinto(payload_section, size - 4) 
        recv_crc = rcm_pipe.read(4)

        # Ensure packet hasn't been corrupted during transfer.
        if crc32(packet) != recv_crc:
            err_packet = build_packet(_UART_RCM_FLAG_CORRUPT_PACKET, b"BAD_CRC")
            rcm_pipe.write(err_packet)
            rcm_pipe.flush()
            continue

        # Process packet data
        packet_cmd = int.from_bytes(payload_section[:2], 'little', signed=False)
        transport_layer_payload = payload_section[2:]

        # Should use a switch statement/LUT but ehh
        if packet_cmd == _UART_RCM_CMD_BOOT:  # BOOT_FIRM
            valid = _boot_exec_signed_firm(pubkey, nvs, transport_layer_payload[:512], transport_layer_payload[512:])

            if not valid:
                err_packet = build_packet(_UART_RCM_FLAG_COMMAND_ERROR, b"BAD_SIGNATURE")
                rcm_pipe.write(err_packet)
                rcm_pipe.flush()

            # Won't ever return if the signature is valid.

        else:
            err_packet = build_packet(_UART_RCM_FLAG_COMMAND_ERROR, b"E_INVAL")
            rcm_pipe.write(err_packet)
            rcm_pipe.flush()


# Execute a signed firmware file (not a firmware image, just a raw signed .mpy)
#
# TODO: Use ECDSA and ASN.1 encode signatures
# NOTE: Pointer erased at boot lockout.
def _boot_exec_signed_firm(pubkey: RSA, nvs: ReadOnlyNVS, sig: memoryview[int], bin: memoryview[int]) -> bool:
    from hashlib import sha256

    sig_hash = pubkey.pkcs_verify(sig)
    bin_hash = sha256(bin).digest()

    # Invalid binary; refuse to boot it.
    if bin_hash != sig_hash:
        return False
    
    logs.print_info("boot", f"signature valid. booting payload sha256 {hexlify(bin_hash)}")
    sys.stdout.flush()
    gc.collect()

    _boot_lockout(nvs, False)

    # Execute payload with no environment (security; NOTE: do we need it for signed firm booting?)
    # App does require access to the boot NVS.
    try:
        exec(bin, {"boot_nvs": nvs}, {})
    except Exception:
        # Payload execution error
        _fatal_error_led(4, 2, reboot=True)

    # Payload finished executing.
    reset()


# Mount the NOR as the root filesystem unless SD boot has been enabled.
#
# NOTE: Pointer erased at boot lockout.
def _boot_mount_root(boot_from_sd: bool) -> None:
    if boot_from_sd:
        from machine import SDCard

        # SD boot mode
        logs.print_info("boot", "attempting sd boot")

        sd = None

        try:
            sd = SDCard(
                slot=_SD_BUS_SLOT,
                freq=_SD_BUS_FREQ,
                sck=Pin(_SD_BUS_SCK, Pin.OUT),
                miso=Pin(_SD_BUS_MISO, Pin.OUT), 
                mosi=Pin(_SD_BUS_MOSI, Pin.OUT), 
                cs=Pin(_SD_BUS_CS, Pin.OUT)
            )
        except OSError:
            logs.print_error("boot", "sd card unreadable/not present")
            _fatal_error_led(1, 4)

        try:
            mount(sd, "/")
        except OSError:
            logs.print_error("boot", "sd card unmountable/corrupt")
            _fatal_error_led(1, 5)

        # SD mount done

    else:
        from esp32 import Partition

        # NOR boot mode
        logs.print_info("boot", "attempting nor flash boot")

        data_partitions = Partition.find(Partition.TYPE_DATA, label="vfs")

        if len(data_partitions) == 0:
            # Partition unmountable (since it cannot be found)
            logs.print_error("boot", "cannot locate data partition")
            _fatal_error_led(1, 3)

        try: 
            mount(data_partitions[0], "/")
        except OSError:
            logs.print_error("boot", "data partition corrupt/unmountable")
            _fatal_error_led(1, 3)

        # NOR mount done


# Validate the firmware image on disk, and mount it if sig checks passed.
# SD boot has a different flash code set (but is otherwise functionally
# identical).
#
# NOTE: Pointer erased at boot lockout.
def _boot_validate_firmware(pubkey: RSA, nvs: ReadOnlyNVS, sd_boot: bool) -> None:
    from __firmimg import FirmwareImage
    import os

    # Error reporting
    flashes = 3 if sd_boot else 2

    def exists(file_path: str) -> bool:
        try:
            os.stat(file_path)
            return True
        except OSError:
            return False
        
    # Signature checks
    disable_sig_checks = nvs.get_i32("en_insecure_boot") == 1 and not _FORCE_SIGNATURE_VALIDATION

    if disable_sig_checks:
        logs.print_warning("boot", "signature checking disabled! allowing insecure payloads")

    firm_name = f"{nvs.get_str("firm")}.img"
    firm_sig = f"{firm_name}.sig"
    logs.print_info("boot", f"loading firmware image {firm_name}")

    # Look for our firm
    if not exists(firm_name):
        logs.print_error("boot", "missing firmware image")
        _fatal_error_led(flashes, 1)

    # Find the signature
    if not disable_sig_checks and not exists(firm_sig):
        logs.print_error("boot", "missing firmware signature")
        _fatal_error_led(flashes, 2)

    firm_f = open(firm_name, "rb")

    # Signature validation stage (other checks are performed but not here)
    if not disable_sig_checks:
        from hashlib import sha256

        logs.print_info("boot", "verifying firmware signature")

        sig_f = open(firm_sig, "rb")
        sig = sig_f.read()
        sig_f.close()

        # 4096 bit signature = 512 bytes (also can be bad pkcs#1 sig but we'll get there
        # later)
        if len(sig) != 512:
            logs.print_error("boot", "corrupt/malformed signature")
            _fatal_error_led(flashes, 2)

        firm_buffer = memoryview(bytearray(64))
        firm_hasher = sha256()

        # Zero copy hash the full firmware
        while True:
            bytes_read = firm_f.readinto(firm_buffer)

            if bytes_read < len(firm_buffer):
                firm_hasher.update(firm_buffer[:bytes_read])
                break
            else:
                firm_hasher.update(firm_buffer)

        gc.collect()

        hashes_equal = False

        try:
            sig_hash = pubkey.pkcs_verify(sig)
            calc_hash = firm_hasher.digest()

            # Signature verification done here!!!!!
            hashes_equal = calc_hash == sig_hash

            # TODO: DBX is not checked. (error flash 2/3, 4)
        except:
            logs.print_error("boot", "invalid pkcs#1 signature")
            _fatal_error_led(flashes, 2)

        if not hashes_equal:
            logs.print_error("boot", "signature validation failed")
            _fatal_error_led(flashes, 2)

    # Mount firm (sig checks probably passed)
    # NOTE: Reusing buffer to avoid possible TOCTOU vulnerability
    try:
        firm_bdev = FirmwareImage(firm_f, firm_name, None, None, block_size=512)
        mount(firm_bdev, "/firm", readonly=True)
    except OSError:
        logs.print_error("boot", "failed to mount firmware")
        _fatal_error_led(flashes, 5)

    # Anti-downgrade firmware check.
    # NOTE: /firm/version is a single-line file with only a 4 byte number contained inside.
    if not disable_sig_checks:
        last_booted_ver = nvs.get_i32("version")

        if not exists("/firm/version"):
            logs.print_error("boot", "no version info found")
            _fatal_error_led(flashes, 3)

        firm_ver_f = open("/firm/version", "r")
        firm_version = int(firm_ver_f.read().strip())
        firm_ver_f.close()

        # Firmware is older than what was last booted.
        if firm_version < last_booted_ver:
            logs.print_error("boot", "found firmware older than installed")
            _fatal_error_led(flashes, 3)

        # Ensure nvs version is up to date (especially after a firmware update)
        if firm_version > last_booted_ver:
            nvs.set_i32("version", firm_version)

        logs.print_info("boot", f"found firmware version {firm_version}")

    
    # Firmware has passed all checks; is now bootable.


# Load the boot payload (typically firm_boot.bin but can be firm_boot.mpy
# for custom code)
#
# NOTE: Pointer erased at boot lockout.
def _boot_read_firm_file(nvs: ReadOnlyNVS) -> bytes:
    boot_mpy = nvs.get_i32("boot_mpy")

    try:
        firm_file = open(f"/firm/firm_boot.{"mpy" if boot_mpy else "bin"}", "rb")
        firm_bin = firm_file.read()
        firm_file.close()
    except OSError:
        logs.print_error("boot", "unable to launch firmware")
        _fatal_error_led(2, 6)

    return firm_bin


# Stub out all potentially dangerous functionality to prevent
# external code from calling back into the bootloader.
#
# NOTE: This function stubs itself too.
def _boot_lockout(nvs: ReadOnlyNVS, nvs_lockout=True) -> None:
    global _boot_clean_syspath
    global _boot_load_nvs
    global _boot_launch_uart_rcm
    global _boot_exec_signed_firm
    global _boot_mount_root
    global _boot_validate_firmware
    global _boot_read_firm_file
    global _boot_lockout
    global boot_main

    # Used to stub out all of the sensitive boot functions at lockout
    # time.
    def _boot_func_stub(*args, **kwargs) -> Any:
        raise OSError("called stubbed bootloader function")

    # Stub (nearly) everything
    _boot_clean_syspath = _boot_func_stub
    _boot_load_nvs = _boot_func_stub
    _boot_launch_uart_rcm = _boot_func_stub
    _boot_exec_signed_firm = _boot_func_stub
    _boot_mount_root = _boot_func_stub
    _boot_validate_firmware = _boot_func_stub
    _boot_read_firm_file = _boot_func_stub
    _boot_lockout = _boot_func_stub
    boot_main = _boot_func_stub

    # Force NVS read-only to all payloads.
    if (_FORCE_NVS_LOCKOUT or nvs.get_i32("nvs_lock")) and nvs_lockout:
        nvs._lockout()

    # Prepare for entry into firm code (clean up memory)
    gc.collect()
    gc.collect()


# Main bootloader. From start to finish, the code must:
# - Remove all external paths from sys.path (to avoid injection attacks)
# - Initialize the security engine and NVS
# - Enter USB/UART recovery mode with a specific button press. Does not return
# - Determine SD/NOR boot mode
#   - Initialize and mount the NOR filesystem iff booting from NOR (at /)
#   - Initialize and mount the SD filesystem iff booting from SD (at /)
# - Locate and verify firmware.img
# - Mount firmware.img read-only at (/firm), and locate firm_boot.bin
# - Boot lockout (erase pointers, clear up everything dangerous)
# - Execute firm_boot.bin (does not return)
#
# NOTE: Pointer erased at boot lockout.
def boot_main() -> None:
    logs.print_info("boot", "secure bootloader copyleft 2026 rsc games")

    _boot_clean_syspath()

    # Security engine initialization already performed (see imports)
    # Private key provides n, e, d; public key only requires n, e.
    # TODO: Generate a key 
    pubkey = RSA(4096, 0, 0)

    # Determine boot mode (NOR or UART/SD)
    boot_pressed = Pin(_SD_BOOT_BUTTON, Pin.IN, Pin.PULL_UP).value() == 0

    # Attempt to load the boot config nvs.
    boot_nvs = _boot_load_nvs(pubkey, boot_pressed)

    # Determine boot mode, and only allow SD boot if the BOOT button is pressed.
    sd_boot_enabled = boot_nvs.get_i32("en_sd_boot") == 1
    sd_boot = sd_boot_enabled and boot_pressed

    # UART BOOT MODE
    # Alternate code path to repair/reinstall firmware for devices which cannot
    # boot from the SD or have elected not to allow that boot mode.
    if (_FORCE_DISABLE_SD_BOOT or not sd_boot_enabled) and boot_pressed:
        _boot_launch_uart_rcm(pubkey, boot_nvs) # does not return

    _boot_mount_root(sd_boot)
    _boot_validate_firmware(pubkey, boot_nvs, sd_boot)

    # Load firm_boot.bin and execute it.
    firm_bin = _boot_read_firm_file(boot_nvs)

    # Isolate secure bootloader scope.
    _boot_lockout(boot_nvs)

    # Run payload
    try:
        firm_globals = {}
        exec(firm_bin, firm_globals, {})

        # Payload must have a function (app_main) taking the nvs as an argument
        # (mostly for static type analysis reasons). This should never return.
        if "app_main" in firm_globals and type(firm_globals["app_main"]) == type(exec):
            firm_globals["app_main"](boot_nvs)

    except Exception as ie:
        logs.print_error("boot", "fatal exception encountered; printing backtrace")
        sys.print_exception(ie)

    finally:
        # Application error (should never return)
        _fatal_error_led(5, 1, reboot=True)
        

try:
    if __name__ == "__main__":
        boot_main()
finally:
    # Unspecified bootrom error (catch all)
    _fatal_error_led(1, 6)
        
