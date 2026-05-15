from ucrypto.ufastrsa.rsa import RSA
from __nvs_perms import ReadOnlyNVS
from micropython import const
import logs
import time

_PRODUCT_ID = const("esp32_alarm_clock")
_PID_HEADER = const("RALC")
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
# TODO: Write code for generating and embedding the shared key (shared key seed provided
#   by provisioning tools/full shared key)
#
def format_boot_nvs(pubkey: RSA, boot_nvs: ReadOnlyNVS):
    # NVS provided by bootrom; not required here.
    logs.print_info("nvs-init", "setting up boot nvs")

    # Product ID and serial are only written ONCE
    if key_exists("prod_id", boot_nvs.get_str):
        logs.print_info("nvs-init", "prod_id already written; skipping")

        dev_prod_id = boot_nvs.get_str("prod_id")

        if dev_prod_id != _PRODUCT_ID:
            logs.print_error("nvs-init", "prod id mismatch; aborting")
            return
        
    else:
        boot_nvs.set_str("prod_id", _PRODUCT_ID)

    if not key_exists("serial", boot_nvs.get_str):
        unit_id = int(input("enter device unit id (MUST BE UNIQUE): "))
        boot_nvs.set_str("serial", _gen_sn(_PID_HEADER, unit_id))

    # NVS LOCK
    if key_exists("nvs_lock", boot_nvs.get_i32):
        nvs_lockout = boot_nvs.get_i32("nvs_lock")

        if nvs_lockout != 0:
            logs.print_error("nvs-init", "nvs lock configured; aborting")
            return
        
    if not key_exists("dbx", boot_nvs.get_blobn):
        boot_nvs.set_blobn("dbx", _DBX)
        
    logs.print_info("nvs-init", f"firm\t\t -> {_FIRMWARE_PATH}")
    logs.print_info("nvs-init", f"dbx\t\t -> {_DBX}")
    logs.print_info("nvs-init", f"nvs_lock\t -> {_NVS_LOCKOUT}")
    logs.print_info("nvs-init", f"en_sd_boot\t -> {_ENABLE_SD_BOOT}")
    logs.print_info("nvs-init", f"dis_sigs\t -> {_ALLOW_INSECURE_BOOT}")
    logs.print_info("nvs-init", f"boot_mpy\t -> {_BOOT_MPY}")

    boot_nvs.set_blobn("shared_key", _SHARED_KEY_BIN)
    boot_nvs.set_str("firm", _FIRMWARE_PATH)
    boot_nvs.set_i32("nvs_lock", _NVS_LOCKOUT)
    boot_nvs.set_i32("en_sd_boot", _ENABLE_SD_BOOT)
    boot_nvs.set_i32("dis_sig_verif", _ALLOW_INSECURE_BOOT)
    boot_nvs.set_i32("boot_mpy", _BOOT_MPY)

    if key_exists("version", boot_nvs.get_i32):
        written_version = boot_nvs.get_i32("version")

        if written_version < _VERSION:
            logs.print_info("nvs-init", f"version\t -> {_VERSION}")
            boot_nvs.set_i32("version", _VERSION)
        # else don't touch it- anti-downgrade.

    else:
        logs.print_info("nvs-init", f"version\t -> {_VERSION}")
        boot_nvs.set_i32("version", _VERSION)

    boot_nvs.commit()

    logs.print_info("nvs-init", "boot nvs initialized")

def key_exists(key: str, key_read_fun) -> bool:
    try:
        key_read_fun(key)
        return True
    except OSError:
        return False

# Generate a serial number from an input 12-digit unit number.
# This uses Nintendo's algorithm for the switch. Reference:
# https://switchbrew.org/wiki/Product_Information#Check%20Digit
def _gen_sn(prefix: str, uid: int) -> str:
    s_uid = f"{uid:012d}"

    odd_sum = _sum_cols(s_uid, 0)
    even_sum = _sum_cols(s_uid, 1) * 3

    check_digit = (even_sum + odd_sum) % 10

    if check_digit != 0:
        check_digit = 10 - check_digit

    id_str = f"{prefix}{s_uid}{check_digit}"
    return id_str

# Serial checksum generation
def _sum_cols(nums: str, offset: int) -> int:
    sum = 0
    for i in range(offset, len(nums), 2):
        sum += int(nums[i])

    return sum

def firm_entry(pubkey, nvs):
    logs.print_warning("nvs-init", "FLASHING NVS")
    format_boot_nvs(pubkey, nvs)

    logs.print_warning("nvs-init", "payload done. external reset required")

    while True:
        pass