from ucrypto.ufastrsa.rsa import RSA
from __nvs_perms import ReadOnlyNVS
from micropython import const
import logs
import time

_PRODUCT_ID = const("esp32_alarm_clock")
_SERIAL_NUM = const("RALC0000000000001")
_SHARED_KEY_BIN = const(b"")
_FIRMWARE_PATH = const("clock_firm")
_VERSION = const(0) # Doesn't change
_DBX = const(b"")
_NVS_LOCKOUT = const(0)
_ENABLE_SD_BOOT = const(0)#const(1)
_ALLOW_INSECURE_BOOT = const(1)#const(0)
_BOOT_MPY = const(1)   # Booting a .bin sounds cooler but .mpy is easier to test.

# Load the boot nvs. Key is the device unique id XOR the public key modulus.
# The boot NVS has the following REQUIRED keys:
# X "prod_id" (blob): product name/id (identical for all devices of a given product line)
# X "lprod_id" (int): length of the product id
# - "serial" (blob): contains the device serial (randomly generated at provisioning)
# - "lserial" (int): contains the length of the device serial
# X "shared_key" (blob): contains the device shared key + sig (signed by root key)
# X "lshared_key" (int): length of the shared key
# - "firm" (blob): contains the name of the NOR firmware.img app to load
# - "lfirm" (int): length of the name of the NOR image
# - "version" (int): version id of the firmware image to load
# X "dbx" (blob): contains blacklisted hashes (not currently used)
# X "ldbx" (int): length of the dbx entry
# - "nvs_lock" (int): disallow writes to the fields in this NVS
# - "en_sd_boot" (int): allow booting from an SD card
# - "dis_sig_verif" (int): disable signature validation and allow booting any payload
# - "boot_mpy" (int): look for firmboot.mpy rather than firmboot.bin when loading 
#
# TODO: Write code for generating and embedding the shared key
#
# TODO: Only write permanent fields once (like prod id and serial) and refuse to update
# those on a rerun. Allow updating other fields unless nvs_lock is configured.
#
# TODO: also increase nvs namespace entropy and generate the serial from random digits
# and the unique id (so predictable str + randnum ^ unique id + a check sum or something)
#
def format_boot_nvs(pubkey: RSA, boot_nvs: ReadOnlyNVS):
    # NVS provided by bootrom; not required here.
    logs.print_warning("nvs-init", "setting up boot nvs")

    try:
        boot_nvs.get_str("prod_id")
        logs.print_warning("nvs-init", "nvs already flashed; aborting")
        return
    
    except OSError:
        # NVS isn't imaged; rewrite crucial fields
        pass

    boot_nvs.set_str("prod_id", _PRODUCT_ID)
    boot_nvs.set_str("serial", _SERIAL_NUM)
    boot_nvs.set_blobn("shared_key", _SHARED_KEY_BIN)
    boot_nvs.set_str("firm", _FIRMWARE_PATH)
    boot_nvs.set_i32("version", _VERSION)
    boot_nvs.set_blobn("dbx", _DBX)
    boot_nvs.set_i32("nvs_lock", _NVS_LOCKOUT)
    boot_nvs.set_i32("en_sd_boot", _ENABLE_SD_BOOT)
    boot_nvs.set_i32("dis_sig_verif", _ALLOW_INSECURE_BOOT)
    boot_nvs.set_i32("boot_mpy", _BOOT_MPY)
    boot_nvs.commit()

    logs.print_warning("nvs-init", "boot nvs initialized")
    time.sleep(1)

def firm_entry(pubkey, nvs):
    logs.print_warning("nvs-init", "FLASHING NVS")
    format_boot_nvs(pubkey, nvs)