# FIRM patcher. Replaces second half of the BOOTROM boot chain so that code
# will be needlessly duplicated here (due to bootrom lockout)
from ucrypto.ufastrsa.rsa import RSA
from __nvs_perms import ReadOnlyNVS
from typing import NoReturn, Any, Callable
import micropython
import logs
import sys
import gc

#################################### CONFIGURATION ######################################

# Enforce signature checks permanently. Set this if using the secure bootloader
# for an application where end-user modification is not desirable.
_FORCE_SIGNATURE_VALIDATION = const(False)

# Force the boot NVS read-only whenever a payload is executed irrespective of the current
# NVS setting. This does not affect UART/USB recovery mode payloads.
# XXX: NVS lockout NOT performed at UART FIRM boot
_FORCE_NVS_LOCKOUT = const(False)

# Permanently disable SD booting. Set this if your device does not have an SD card
# slot (so it's literally infeasible to perform an SD boot).
# NOTE: Native firm patcher only patches the native firm in NOR.
_FORCE_DISABLE_SD_BOOT = const(False)

################################## END CONFIGURATION ####################################

# Error reporting
_DEBUG_LED_GPIO = const(2)
_DEBUG_FLASH_LONG_MS = const(750)
_DEBUG_FLASH_SHORT_MS = const(225)
_DEBUG_FLASH_OFF_MS = const(150)
_DEBUG_FLASH_IN_BETWEEN_MS = const(250)
_DEBUG_FLASH_WAIT_MS = const(800)

_SD_BOOT_BUTTON = const(0)

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
#   6 short: cannot locate firmboot.bin in <firmware>.img (also used for SD boot)
#   7 short: recovery.img could not be found/unbootable
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
def _fatal_error_led(pubkey: RSA | None, boot_nvs: ReadOnlyNVS | None, long_flashes: int, 
                     short_flashes: int, reboot: Callable | None=None) -> NoReturn:
    from machine import Pin
    from time import sleep_ms

    led_internal = Pin(_DEBUG_LED_GPIO, Pin.OUT)

    def flash_led(delay_ms_on: int) -> None:
        led_internal.on()
        sleep_ms(delay_ms_on)
        led_internal.off()
        sleep_ms(_DEBUG_FLASH_OFF_MS)

    while True:
        for _ in range(0, long_flashes):
            flash_led(_DEBUG_FLASH_LONG_MS)

        sleep_ms(_DEBUG_FLASH_IN_BETWEEN_MS)

        for _ in range(0, short_flashes):
            flash_led(_DEBUG_FLASH_SHORT_MS)

        sleep_ms(_DEBUG_FLASH_WAIT_MS)

        # Since uart_rcm also calls here, avoid a technical infinite loop.
        if reboot is not None:
            reboot()

# PayloadFS wrapper (to allow executing arbitrary code without a true filesystem
# to load it from).
#
# NOTE: Pointer erased at boot lockout.
def _boot_mount_payload_fs(mount_pt: str, f_path: str, bin: memoryview[int]) -> None:
    from io import BytesIO
    from vfs import mount

    class PayloadFS:
        def __init__(self, fname: str, in_bytes: bytes) -> None:
            """
            Initializes a fake FS. Takes the filename (target file path) of the singular file
            and creates a fake file entry.
            """
            self.fname = f"/{fname}"
            self.f_bytes = in_bytes

        def mount(self, readonly: bool, _: bool) -> None:
            if not readonly:
                raise OSError("rw mount on ro fs")

        def umount(self) -> None:
            del self.fname
            del self.f_bytes

        def open(self, path: str, perms: str) -> BytesIO:
            if not path == self.fname:
                raise OSError("ENOENT")
            
            if not perms == "rb":
                raise OSError("EPERM")
            
            return BytesIO(self.f_bytes)
        
        def stat(self, path: str) -> tuple:
            if not path == self.fname:
                raise OSError("ENOENT")
            
            return (0x8000, 0, 0, 0, 0, 0, len(self.f_bytes), 0, 0, 0)
        
        def ilistdir(self, path: str):
            if not path == "/":
                raise OSError("ENOENT")
            
            return iter([(self.fname, 0x8000, 0, len(self.f_bytes))])

        def getcwd(self) -> str:
            return "/"
        
    payload_fs = PayloadFS(f_path, bin)
    mount(payload_fs, mount_pt, readonly=True)

# Mount the NOR as the root filesystem unless SD boot has been enabled.
#
# NOTE: Pointer erased at boot lockout.
def _boot_mount_root(pubkey: RSA, nvs: ReadOnlyNVS) -> None:
    from vfs import mount
    from esp32 import Partition

    # NOR boot mode
    logs.print_info("boot", "attempting nor flash boot")

    data_partitions = Partition.find(Partition.TYPE_DATA, label="vfs")

    if len(data_partitions) == 0:
        # Partition unmountable (since it cannot be found)
        logs.print_error("boot", "cannot locate data partition")
        _fatal_error_led(pubkey, nvs, 1, 3)

    try: 
        mount(data_partitions[0], "/")
    except OSError:
        logs.print_error("boot", "data partition corrupt/unmountable")
        _fatal_error_led(pubkey, nvs, 1, 3)

    # NOR mount done


# Validate the firmware image on disk, and mount it if sig checks passed.
# SD boot has a different flash code set (but is otherwise functionally
# identical).
#
# Returns none if firmware validation and mounting was successful; otherwise
# returns the error code.
#
# NOTE: Pointer erased at boot lockout.
def _boot_validate_firmware(pubkey: RSA, nvs: ReadOnlyNVS, firm_name: str, sd_boot: bool, 
                            version_check=True) -> tuple[int, int] | None:
    from __firmimg import FirmwareImage
    from vfs import mount, umount
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
    disable_sig_checks = nvs.get_i32("dis_sig_verif") == 1 and not _FORCE_SIGNATURE_VALIDATION

    if disable_sig_checks:
        logs.print_warning("boot", "signature checking disabled! allowing insecure payloads")

    firm_sig = f"{firm_name}.sig"
    logs.print_info("boot", f"loading firmware image {firm_name}")

    # Look for our firm
    if not exists(firm_name):
        logs.print_error("boot", "missing firmware image")
        return flashes, 1

    # Find the signature
    if not disable_sig_checks and not exists(firm_sig):
        logs.print_error("boot", "missing firmware signature")
        return flashes, 2

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
            return flashes, 2

        # FIXME: Why is the buffer SO MICROSCOPIC
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

            # IMPORTANT: Signature verification done here!!!!!
            # TODO: probably vulnerable to timing side channel
            hashes_equal = calc_hash == sig_hash

            # TODO: DBX is not checked. (error flash 2/3, 4)
        except:
            logs.print_error("boot", "invalid pkcs#1 signature")
            return flashes, 2

        if not hashes_equal:
            logs.print_error("boot", "signature validation failed")
            return flashes, 2

    # Mount firm (sig checks probably passed)
    # NOTE: Reusing buffer to avoid possible TOCTOU vulnerability
    try:
        firm_bdev = FirmwareImage(firm_f, firm_name, None, None, block_size=512)
        mount(firm_bdev, "/firm", readonly=True)
    except OSError:
        logs.print_error("boot", "failed to mount firmware")
        return flashes, 5

    # Anti-downgrade firmware check. Recovery firm does not have version checks.
    # NOTE: /firm/version is a single-line file with only a 4 byte number contained inside.
    if not disable_sig_checks and version_check:
        last_booted_ver = nvs.get_i32("version")

        if not exists("/firm/version"):
            logs.print_error("boot", "no version info found")
            umount("/firm")
            return flashes, 3

        firm_ver_f = open("/firm/version", "r")
        firm_version = int(firm_ver_f.read().strip())
        firm_ver_f.close()

        # Firmware is older than what was last booted.
        if firm_version < last_booted_ver:
            logs.print_error("boot", "found firmware older than installed")
            umount("/firm")
            return flashes, 3

        # Ensure nvs version is up to date (especially after a firmware update)
        if firm_version > last_booted_ver:
            nvs.set_i32("version", firm_version)

        logs.print_info("boot", f"found firmware version {firm_version}")

    # Firmware has passed all checks; is now bootable.
    return None


# Load the boot payload (typically firmboot.bin but can be firmboot.mpy
# for custom code)
#
# NOTE: Pointer erased at boot lockout.
def _boot_read_firm_file(pubkey: RSA, nvs: ReadOnlyNVS) -> bytes:
    boot_mpy = nvs.get_i32("boot_mpy")

    try:
        firm_file = open(f"/firm/firmboot.{"mpy" if boot_mpy else "bin"}", "rb")
        firm_bin = firm_file.read()
        firm_file.close()
    except OSError:
        logs.print_error("boot", "unable to launch firmware")
        _fatal_error_led(pubkey, nvs, 2, 6)

    return firm_bin


# Stub out all potentially dangerous functionality to prevent
# external code from calling back into the bootloader.
#
# NOTE: This function stubs itself too.
def _boot_lockout(nvs: ReadOnlyNVS, nvs_lockout=True) -> None:
    global _boot_mount_payload_fs
    global _boot_validate_firmware
    global _boot_read_firm_file
    global _boot_lockout
    global firm_entry

    # Used to stub out all of the sensitive boot functions at lockout
    # time.
    def _boot_func_stub(*args, **kwargs) -> Any:
        raise OSError("called stubbed bootloader function")

    # Stub (nearly) everything
    _boot_mount_payload_fs = _boot_func_stub
    _boot_validate_firmware = _boot_func_stub
    _boot_read_firm_file = _boot_func_stub
    _boot_lockout = _boot_func_stub
    firm_entry = _boot_func_stub

    # Force NVS read-only to all payloads.
    if nvs_lockout and (_FORCE_NVS_LOCKOUT or nvs.get_i32("nvs_lock")):
        nvs._lockout()

    # Prepare for entry into firm code (clean up memory)
    gc.collect()
    gc.collect()

_ORIG_IMPORT = __import__

# Runtime import patcher stub
#
# NOTE: invoked at import time (WILL HOOK ALL IMPORTS)
def _patched_import(name: str, i_globals: dict | None=None, i_locals: dict | None=None, fromlist: tuple=(), level: int=0):
    if name in sys.modules:
        return sys.modules[name]

    in_module = _ORIG_IMPORT(name, i_globals, i_locals, fromlist, level)

    if name in _PATCH_LISTS:
        patch_def = _PATCH_LISTS[name]
        logs.print_warning("import", f"module {name} has patch definitions")

        for abs_sym_name in patch_def:
            # TODO: recursive look up attribute
            rel_sym_name, sym_module = _resolve_symbol(in_module, abs_sym_name)
            logs.print_info("import", f"resolved {rel_sym_name} mod {sym_module.__name__}")

            if hasattr(sym_module, rel_sym_name):
                delattr(sym_module, rel_sym_name)
                patch_attr = patch_def[abs_sym_name]
                _patch_attribute(sym_module, patch_attr, rel_sym_name)
                
            else:
                logs.print_warning("import.hook", f"missing symbol {rel_sym_name} dir {in_module.__dict__}")
                logs.print_info("import", "attempting inject anyway")
                # TEMPORARY-?!
                patch_attr = patch_def[abs_sym_name]
                _patch_attribute(sym_module, patch_attr, rel_sym_name)

        logs.print_warning("import", f"module patching finished!")
        
    #else:
        #logs.print_info("import", f"module {name}: no patch def found")

    return in_module

def _resolve_symbol(in_module: Any, sym_name: str) -> tuple[str, Any]:
    cur_mod = in_module

    sym_path = sym_name.split(".")
    relative_sym_name = sym_path.pop()

    for sym in sym_path:
        cur_mod = getattr(cur_mod, sym)

    return relative_sym_name, cur_mod

def _patch_attribute(in_module: Any, patch_attr: Any, sym_name: str) -> None:
    # Global scope function patcher
    if callable(patch_attr):
        # TODO: only patches functions properly (not attrs/classes)
        def inject_helper_xx(*args, **kwargs):
            # TODO: class function patching not currently functional?
            logs.print_warning("import.hook", f"trigger: call inject handler: {sym_name} ptr {patch_attr}")
            globals().update(in_module.__dict__)
            #print(f"in dict {in_module.__dict__}")
            #print(f"exec patched {patch_attr}: locals {globals()}")
            patch_attr(*args, **kwargs)

        logs.print_info("import.hook", f"patching func {sym_name}")
        setattr(in_module, sym_name, inject_helper_xx)
    else:
        logs.print_warning("import.hook", f"unsupported patch sym type {type(patch_attr)}")

####################################################################################
# DYNAMIC PATCHING METADATA
####################################################################################
# patch functions
def _patch_stub(*args):
    print(f"warning: stubbed function called")


def init():
    """
    Fully initialize all peripheral hardware. Most of the hardware has already been
    partially initialized, but network/display/pwr_sense require a bit more.
    """

    # Kick up the CPU clock (currently powersave not required)
    freq(240_000_000)

    # TODO: Make less ANNOYINGLY NOISY (set vcom_desel/precharge/clock div)
    # see https://www.hpinfotech.ro/SSD1309.pdf
    # TODO: Background thread
    #NIC.bring_up()

    DISPLAY.contrast(0)
    DISPLAY.set_precharge(1, 1)
    DISPLAY.set_vcomdesel(0)

    # XXX: fbcon auto show not supported
    FBCON.set_hidden(True)

    # TODO: start pwr_sense monitoring driver to detect power loss events and prevent
    # the device from wasting CMOS battery energy

    if not _mount_sd("/sd"):
        logs.print_warning("hal", "/sd node not accessible")

def main():
    # XXX: should not be doing NTP time sync on main thread
    import ntptime

    logs.print_warning("app", "running alpha test firmware which is FEATURE INCOMPLETE! YOU WILL RUN INTO ISSUES!")
    
    dev.NIC.bring_up()

    if dev.NIC.link_is_up():
        import ntptime
        print("ntp time sync complete (hacky)")
        ntptime.settime()

    # Hardware is online (NTP time sync not guaranteed)
    # Start clock
    clock = Clock()

    # XXX: Neither of these should be hardcoded.
    #audio_sampled.play_oneshot("/sd/other/02 - One Step Closer-slowed.wav")
    clock.local_time.utc_offset = -5  # EST
    clock.alarms.append(Alarm((9, 45, -1, -1), (0, 1, 2, 3, 4)))
    print(f"weekday: {clock.local_time.get_local_time()[6]}")

    #time.sleep(100)
    # TODO: clock applet needs to be refreshed after being in any other menu
    while True:
        if dev.get_button(dev.BTN_BACK):
            raise RuntimeError("Resetting to RECOVERY MODE FIRM")

        clock.tick()
        clock.repaint(dev.DISPLAY)
        time.sleep_ms(33)

    #time.sleep(100)

    # NOTE: Showing advanced stuff on screen doesn't play nice with the buffer refill ISR
    # we can only play music for alarms because of this (without a more advanced driver)
    # may be worth increasing the file read speed....
    #osk.prompt_ok("Hello!", ["testing osk print", "does ok work", "yes or no", "hehe"])
    #osk.prompt_yn("Hello!", ["testing osk print", "does ok work", "yes or no", "hehe"])

    #osk.prompt_text(osk.LAYOUT_KEYBOARD, 50, False)

# patch definitions below here

_PATCH_LISTS = {
    "main": {
        "main": main
    },
    # TODO: attribute patching (non-function)
    "ui.clock": {
    },
    "hal.peripherals": {
        "init": init
    }
}
####################################################################################

# Main bootloader. From start to finish, the code must:
# - Remove all external paths from sys.path (to avoid injection attacks)
# - Initialize the security engine and NVS
# - Enter USB/UART recovery mode with a specific button press. Does not return
# - Determine SD/NOR boot mode
#   - Initialize and mount the NOR filesystem iff booting from NOR (at /)
#   - Initialize and mount the SD filesystem iff booting from SD (at /)
# - Locate and verify firmware.img
# - Mount firmware.img read-only at (/firm), and locate firmboot.bin
# - Boot lockout (erase pointers, clear up everything dangerous)
# - Execute firmboot.bin (does not return)
#
# TODO: Better manage bootloader memory (to reduce fragmentation)
# NOTE: Pointer erased at boot lockout.
def firm_entry(pubkey: RSA, boot_nvs: ReadOnlyNVS) -> NoReturn:
    global _patched_import

    from vfs import umount

    logs.print_info("boot", "loaded FIRM patcher")
    _boot_mount_root(pubkey, boot_nvs)

    # Load firmware package
    err_code = _boot_validate_firmware(pubkey, boot_nvs, f"{boot_nvs.get_str("firm")}.img", False)

    if err_code is not None:
        _fatal_error_led(pubkey, boot_nvs, err_code[0], err_code[1])

    # Load firmboot.bin/mpy and execute it.
    firm_bin = _boot_read_firm_file(pubkey, boot_nvs)

    # Isolate secure bootloader scope.
    _boot_mount_payload_fs("/initrd", "firmboot.mpy", memoryview(firm_bin))
    _boot_lockout(boot_nvs)
    del firm_bin

    # TODO: Install module patcher
    import builtins
    builtins.__import__ = _patched_import
    del _patched_import
    del sys.modules["firmboot"] # (this very file is imported as firmboot)

    # Run payload
    try:
        sys.path.append("/initrd")
        firmboot = __import__("firmboot", {}, {})
        umount("/initrd")
        sys.path.remove("/initrd")
        gc.collect()

        # TODO: sys.modules purge?

        # Payload must have a function (app_main) taking the nvs as an argument
        # (mostly for static type analysis reasons). This should never return.
        if hasattr(firmboot, "app_main") and callable(firmboot.app_main):
            firmboot.app_main(boot_nvs)

        logs.print_warning("boot", "firm returned")

    except BaseException as ie:
        logs.print_error("boot", "fatal exception encountered; printing backtrace")
        sys.print_exception(ie)

    finally:
        # Remove patcher
        builtins.__import__ = _ORIG_IMPORT
        del builtins

        from bootrom import reboot_to_recovery

        # Application error (should never return)
        _fatal_error_led(pubkey, boot_nvs, 5, 1, reboot=reboot_to_recovery)
