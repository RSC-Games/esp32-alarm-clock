# Initial boot context.
# This file replaces the default MicroPython boot code. This means we have NO
# prior existing boot context (notably, NOR is not mounted) and so we must do
# that here.
# NOTE: performing initial lockout (can be disabled in the mpy firmware). Idea
# is to prevent circumventing the secure boot chain with a keyboard interrupt.
import micropython
micropython.kbd_intr(-1)

from ucrypto.ufastrsa.rsa import RSA
from binascii import hexlify
from typing import NoReturn
from esp32 import NVS
from vfs import mount
import machine 
import time
import logs
import sys
import gc

# Error reporting
_DEBUG_LED_GPIO = micropython.const(2)
_DEBUG_FLASH_LONG_MS = micropython.const(1000)
_DEBUG_FLASH_SHORT_MS = micropython.const(300)
_DEBUG_FLASH_OFF_MS = micropython.const(200)

_SD_BOOT_BUTTON = micropython.const(0)

# Enforce signature checks permanently. Set this if using the secure bootloader
# for an application where end-user modification is not desirable.
_FORCE_SIGNATURE_VALIDATION = micropython.const(False)

# Permanently disable SD booting. Set this if your device does not have an SD card
# slot (so it's literally infeasible to perform an SD boot).
_FORCE_DISABLE_SD_BOOT = micropython.const(False)

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
#
# FIRMWARE PACKAGE BOOT ERRORS (2 long flashes, repeats):
#   1 short: cannot locate <firmware>.img in NOR
#   2 short: <firmware>.img missing/bad RSA signature
#   3 short: <firmware>.img version mismatch (firmware installed is older than NVS)
#   4 short: <firmware>.img hash on dbx blacklist (provided at update time in separate partition)
#   5 short: <firmware>.img unmountable (must be mounted as read-only)
#   6 short: cannot locate firm_boot.bin in <firmware>.img
#
# SD BOOT ERRORS (3 long flashes, repeats):
#   1 short: cannot locate recovery.img on SD
#   2 short: recovery.img has bad RSA signature on SD
#   3 short: recovery.img version mismatch (firmware installed is older than NVS)
#   4 short: recovery.img hash on dbx blacklist (provided at update time in separate partition)
#   5 short: recovery.img unmountable (must be mounted as read-only)
#   6 short: cannot locate firm_boot.bin in recovery.img
#
# APPLICATION ERRORS (4 long flashes, immediate reboot):
#   1 short: exception in firmware; stack dumped, rebooting
def _fatal_error_led(long_flashes: int, short_flashes: int, reboot: bool=True) -> NoReturn:
    led_internal = machine.Pin(_DEBUG_LED_GPIO, machine.Pin.OUT)

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
            machine.reset()


# Avoid accidentally importing any unverified files on the raw filesystem
def _boot_clean_syspath() -> None:
    sys.path.clear()
    sys.path.append(".frozen")


# Load the boot nvs. Key is the device unique id XOR the public key modulus.
# The boot NVS has the following REQUIRED keys:
# - "prod_id" (blob): product name/id (identical for all devices of a given product line)
# - "prod_id_len" (int): length of the product id
# - "serial" (blob): contains the device serial (randomly generated at provisioning)
# - "serial_len" (int): contains the length of the device serial
# - "firm" (blob): contains the name of the NOR firmware.img app to load
# - "firm_len" (int): length of the name of the NOR image
# - "version" (int): version id of the firmware image to load
# - "dbx" (blob): contains blacklisted hashes (not currently used)
# - "dbx_len" (int): length of the dbx entry
# - "en_sd_boot" (int): allow booting from an SD card
# - "en_insecure_boot" (int): disable signature validation and allow booting any payload
# - "boot_mpy" (int): look for firm_boot.mpy rather than firm_boot.bin when loading 
#
def _boot_load_nvs(pubkey: RSA) -> NVS:
    # Mask off the first 7 bytes (nvs names are limited to 15 bytes)
    nvs_uid = pubkey.n ^ int.from_bytes(machine.unique_id(), "little") & 0x00FFFFFFFFFFFFFF
    nvs_name = b"k" + int.to_bytes(nvs_uid, 14, "little", signed=False)

    logs.print_info("boot", f"loading boot nvs {nvs_name}")

    try:
        boot_nvs = NVS(nvs_name.decode())

        # Test namespace existence by reading the serial (will panic if nonexistent).
        serial_len = boot_nvs.get_i32("serial_len")
        serial = bytearray(serial_len)
        boot_nvs.get_blob("serial", serial)

        logs.print_info("boot", f"unit serial is {serial.decode()}")
        return boot_nvs

    except OSError:
        # ERR_NON_INITIALIZED_NVS
        _fatal_error_led(1, 2)


def _boot_launch_uart_rcm() -> NoReturn:
    while True:
        pass


# Mount the NOR as the root filesystem unless SD boot has been enabled.
def _boot_mount_root(boot_from_sd: bool) -> None:
    if boot_from_sd:
        # SD boot mode
        logs.print_info("boot", "attempting sd boot")

    else:
        # NOR boot mode
        logs.print_info("boot", "attempting nor flash boot")

        # TODO: Do the annoying esp32 partition loading stuff


# Main bootloader. From start to finish, the code must:
# - Remove all external paths from sys.path (to avoid injection attacks)
# - Initialize the security engine and NVS
# - Enter USB/UART recovery mode with a specific button press. Does not return
# - Determine SD/NOR boot mode
#   - Initialize and mount the NOR filesystem iff booting from NOR (at /)
#   - Initialize and mount the SD filesystem iff booting from SD (at /)
# - Locate and verify firmware.img
# - Mount firmware.img read-only at (/firm), and locate firm_boot.bin
# - Execute firm_boot.bin (does not return)
#
def boot_main() -> None:
    logs.print_info("boot", "secure bootloader copyleft 2026 rsc games")

    _boot_clean_syspath()

    # Security engine initialization already performed (see imports)
    # Private key provides n, e, d; public key only requires n, e.
    # TODO: Generate a key 
    pubkey = RSA(4096, 0, 0)

    boot_nvs = _boot_load_nvs(pubkey)

    # Determine boot mode, and only allow SD boot if the BOOT button is pressed.
    boot_pressed = machine.Pin(_SD_BOOT_BUTTON, machine.Pin.IN, machine.Pin.PULL_UP).value() == 0
    sd_boot_enabled = boot_nvs.get_i32("en_sd_boot") == 1
    boot_sd = sd_boot_enabled and boot_pressed

    # UART BOOT MODE. DOES NOT RETURN!!!!
    # Alternate code path to repair/reinstall firmware for devices which cannot
    # boot from the SD or have elected not to allow that boot mode.
    if (_FORCE_DISABLE_SD_BOOT or not sd_boot_enabled) and boot_pressed:
        _boot_launch_uart_rcm(pubkey)
        pass

    fs = _boot_mount_root(boot_sd)
