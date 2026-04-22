from ucrypto.ufastrsa.rsa import RSA
from __nvs_perms import ReadOnlyNVS
from vfs import mount, VfsLfs2
from micropython import const
from binascii import hexlify
from esp32 import Partition
from hashlib import sha256
import time
import logs
import sys

#################################### CONFIGURATION ######################################

# Most devices with the secure bootrom share the same UART boot public key. Only
# allow the below product type to run this signed copy of the payload.
_PRODUCT_ID = const("esp32_alarm_clock")

# Debugging flag. Not recommended for production.
_SKIP_FORMAT_NOR = const(True)

# Do not perform a filesystem format and do not reinject recovery to the filesystem.
# Instead, the tool only writes the received <app_name>.img to NOR, then reboots.
_FAST_APP_REIMAGE = const(False)

# Skip running the command parser after recovery injection. Useful for only formatting
# the filesystem and reinstalling recovery.img. Speeds up device recovery but requires
# an internet connection to install the main device firmware image.
_SKIP_COMMAND_PARSER = const(True)

################################## END CONFIGURATION ####################################

# Full recovery filesystem image (must be small to stay under the bootrom limit)
RECOVERY_IMG = bytes()

# Recovery hash is pre-computed (to prevent injecting a bad image)
RECOVERY_IMG_SHA256 = bytes()


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

    logs.print_warning("imager", "installing fresh recovery.img")

    # Verify recovery image hash (avoid writing a corrupt recovery image even
    # though in theory these payloads are signed).
    recovery_hash = sha256(RECOVERY_IMG).digest()

    if recovery_hash != RECOVERY_IMG_SHA256:
        logs.print_error("imager", f"frozen recovery.img corrupt; got {hexlify(recovery_hash)}")
        return False
    
    with open("recovery.img", "wb") as recovery_f:
        recovery_f.write(RECOVERY_IMG)

    return True


def do_command_parser():
    # TODO: Steal from the bootrom command parser (with more commands)
    logs.print_warning("imager", "entering binary command parser")
    
    while True:
        pass


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
        logs.print_error("imager", f"wrong product id. aborting")
        return

    if not _FAST_APP_REIMAGE:
        # internal fs format required/recovery.img injection
        if not mount_internal_fs():
            time.sleep(5)
            return
        
        if not write_recovery_img():
            time.sleep(5)
            return

    if not _SKIP_COMMAND_PARSER:
        # command parser time (for installing firmware files)
        do_command_parser()

    logs.print_info("imager", "imager firm DONE; all required files installed")