
from ucrypto.ufastrsa.rsa import RSA 
from __nvs_perms import ReadOnlyNVS
from typing import NoReturn, Any
import micropython
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

_SD_BOOT_BUTTON = micropython.const(0)

_SD_BUS_SLOT = micropython.const(3)
_SD_BUS_FREQ = micropython.const(20_000_000)
_SD_BUS_SCK = micropython.const(14)
_SD_BUS_MISO = micropython.const(12)
_SD_BUS_MOSI = micropython.const(13)
_SD_BUS_CS = micropython.const(15)

def _fatal_error_led(_, _2, led_long, led_short, reboot=False) -> NoReturn:
    logs.print_error("firm", f"fatal: flash code triggered: {led_long}, {led_short}")

    while True:
        pass

# PayloadFS wrapper (to allow executing arbitrary code without a true filesystem
# to load it from).
#
# NOTE: Pointer erased at boot lockout.
# NOTE: Stolen straight from __boot2
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
                raise OSError("ro fs cannot be mounted rw")

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
def _boot_mount_root(pubkey: RSA, nvs: ReadOnlyNVS, boot_from_sd: bool) -> None:
    from machine import Pin
    from vfs import mount

    if boot_from_sd:
        from machine import SDCard

        # SD boot mode
        logs.print_info("firm", "attempting sd boot")

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
            logs.print_error("firm", "sd card unreadable/not present")
            _fatal_error_led(pubkey, nvs, 1, 4)

        try:
            mount(sd, "/")
        except OSError:
            logs.print_error("firm", "sd card unmountable/corrupt")
            _fatal_error_led(pubkey, nvs, 1, 5)

        # SD mount done

    else:
        from esp32 import Partition

        # NOR boot mode
        logs.print_info("firm", "attempting nor flash boot")

        data_partitions = Partition.find(Partition.TYPE_DATA, label="vfs")

        if len(data_partitions) == 0:
            # Partition unmountable (since it cannot be found)
            logs.print_error("firm", "cannot locate data partition")
            _fatal_error_led(pubkey, nvs, 1, 3)

        try: 
            mount(data_partitions[0], "/")
        except OSError:
            logs.print_error("firm", "data partition corrupt/unmountable")
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
def _boot_validate_firmware(pubkey: RSA, nvs: ReadOnlyNVS, firm_name: str, sd_boot: bool) -> tuple[int, int] | None:
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
        logs.print_warning("firm", "signature checking disabled! allowing insecure payloads")

    firm_sig = f"{firm_name}.sig"
    logs.print_info("firm", f"loading firmware image {firm_name}")

    # Look for our firm
    if not exists(firm_name):
        logs.print_error("firm", "missing firmware image")
        return flashes, 1

    # Find the signature
    if not disable_sig_checks and not exists(firm_sig):
        logs.print_error("firm", "missing firmware signature")
        return flashes, 2

    firm_f = open(firm_name, "rb")

    # Signature validation stage (other checks are performed but not here)
    if not disable_sig_checks:
        from hashlib import sha256

        logs.print_info("firm", "verifying firmware signature")

        sig_f = open(firm_sig, "rb")
        sig = sig_f.read()
        sig_f.close()

        # 4096 bit signature = 512 bytes (also can be bad pkcs#1 sig but we'll get there
        # later)
        if len(sig) != 512:
            logs.print_error("firm", "corrupt/malformed signature")
            return flashes, 2

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
            logs.print_error("firm", "invalid pkcs#1 signature")
            return flashes, 2

        if not hashes_equal:
            logs.print_error("firm", "signature validation failed")
            return flashes, 2

    # Mount firm (sig checks probably passed)
    # NOTE: Reusing buffer to avoid possible TOCTOU vulnerability
    try:
        firm_bdev = FirmwareImage(firm_f, firm_name, None, None, block_size=512)
        mount(firm_bdev, "/firm", readonly=True)
    except OSError:
        logs.print_error("firm", "failed to mount firmware")
        return flashes, 5

    # Anti-downgrade firmware check.
    # NOTE: /firm/version is a single-line file with only a 4 byte number contained inside.
    if not disable_sig_checks:
        last_booted_ver = nvs.get_i32("version")

        if not exists("/firm/version"):
            logs.print_error("firm", "no version info found")
            umount("/firm")
            return flashes, 3

        firm_ver_f = open("/firm/version", "r")
        firm_version = int(firm_ver_f.read().strip())
        firm_ver_f.close()

        # Firmware is older than what was last booted.
        if firm_version < last_booted_ver:
            logs.print_error("firm", "found firmware older than installed")
            umount("/firm")
            return flashes, 3

        # Ensure nvs version is up to date (especially after a firmware update)
        if firm_version > last_booted_ver:
            nvs.set_i32("version", firm_version)

        logs.print_info("firm", f"found firmware version {firm_version}")

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
        logs.print_error("firm", "unable to launch firmware")
        _fatal_error_led(pubkey, nvs, 2, 6)

    return firm_bin


# Stub out all potentially dangerous functionality to prevent
# external code from calling back into the bootloader.
#
# NOTE: This function stubs itself too.
def _boot_lockout(nvs: ReadOnlyNVS, nvs_lockout=True) -> None:
    global _boot_mount_payload_fs
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
    _boot_mount_payload_fs = _boot_func_stub
    _boot_mount_root = _boot_func_stub
    _boot_validate_firmware = _boot_func_stub
    _boot_read_firm_file = _boot_func_stub
    _boot_lockout = _boot_func_stub
    boot_main = _boot_func_stub

    # Force NVS read-only to all payloads.
    if nvs_lockout and (_FORCE_NVS_LOCKOUT or nvs.get_i32("nvs_lock")):
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
# - Mount firmware.img read-only at (/firm), and locate firmboot.bin
# - Boot lockout (erase pointers, clear up everything dangerous)
# - Execute firmboot.bin (does not return)
#
# TODO: Better manage bootloader memory (to reduce fragmentation)
# NOTE: Pointer erased at boot lockout.
def firm_entry(pubkey: RSA, boot_nvs: ReadOnlyNVS) -> None:
    from machine import Pin
    from vfs import umount

    logs.print_info("firm", "faking secure bootloader (firm launch)")

    # Determine boot mode (NOR or UART/SD)
    boot_pressed = Pin(_SD_BOOT_BUTTON, Pin.IN, Pin.PULL_UP).value() == 0

    # Determine boot mode, and only allow SD boot if the BOOT button is pressed.
    sd_boot_enabled = boot_nvs.get_i32("en_sd_boot") == 1
    sd_boot = sd_boot_enabled and boot_pressed

    _boot_mount_root(pubkey, boot_nvs, sd_boot)

    # Load firmware package
    err_code = _boot_validate_firmware(pubkey, boot_nvs, f"{boot_nvs.get_str("firm")}.img", sd_boot)

    # Load recovery module
    if err_code is not None:
        if _boot_validate_firmware(pubkey, boot_nvs, "recovery.img", sd_boot) is not None:
            _fatal_error_led(pubkey, boot_nvs, err_code[0], err_code[1])

        logs.print_info("firm", "loading recovery firmware package")

    # Load firmboot.bin and execute it.
    firm_bin = _boot_read_firm_file(pubkey, boot_nvs)

    # Isolate secure bootloader scope.
    _boot_mount_payload_fs("/initrd", "firmboot.mpy", memoryview(firm_bin))
    _boot_lockout(boot_nvs)
    del firm_bin

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

    except Exception as ie:
        logs.print_error("firm", "fatal exception encountered; printing backtrace")
        sys.print_exception(ie)

    finally:
        # Application error (should never return)
        _fatal_error_led(pubkey, boot_nvs, 5, 1, reboot=True)

    # TODO: Missing recovery.img boot