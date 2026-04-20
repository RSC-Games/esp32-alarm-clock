from ucrypto.ufastrsa.rsa import RSA
from micropython import const
from machine import unique_id
from binascii import hexlify
from esp32 import NVS
import logs
import time

_PRODUCT_ID = const(b"esp32_alarm_clock")
_SERIAL_NUM = const(b"RALC0000000000001")
_FIRMWARE_PATH = const(b"recovery")#const(b"clock_firm")
_VERSION = const(0) # Doesn't change
_DBX = const(b"")
_NVS_LOCKOUT = const(0)
_ENABLE_SD_BOOT = const(0)#const(1)
_ALLOW_INSECURE_BOOT = const(1)#const(0)
_BOOT_MPY = const(1)   # Booting a .bin sounds cooler but .mpy is easier to test.

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
# - "dis_sig_verif" (int): disable signature validation and allow booting any payload
# - "boot_mpy" (int): look for firm_boot.mpy rather than firm_boot.bin when loading 
#
# NOTE: Pointer erased at boot lockout.
# THIS FUNCTION IS NOT USEFUL AS LONG AS A PUBLIC KEY DOES NOT EXIST!!!
def format_boot_nvs(pubkey: RSA, nvs: NVS):
    # TODO: public key not known; nvs pointer will be incorrect
    nvs_uid = pubkey.n ^ int.from_bytes(unique_id(), "little") & 0x00FFFFFFFFFFFFFF
    nvs_name = b"k" + hexlify(int.to_bytes(nvs_uid, 7, "little"))

    boot_nvs = NVS(nvs_name.decode())
    logs.print_warning("nvs-init", "setting up boot nvs")

    boot_nvs.set_blob("prod_id", _PRODUCT_ID)
    boot_nvs.set_i32("prod_id_len", len(_PRODUCT_ID))
    boot_nvs.set_blob("serial", _SERIAL_NUM)
    boot_nvs.set_i32("serial_len", len(_SERIAL_NUM))
    boot_nvs.set_blob("firm", _FIRMWARE_PATH)
    boot_nvs.set_i32("firm_len", len(_FIRMWARE_PATH))
    boot_nvs.set_i32("version", _VERSION)
    boot_nvs.set_blob("dbx", _DBX)
    boot_nvs.set_i32("dbx_len", len(_DBX))
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