from __nvs_perms import ReadOnlyNVS
import machine
import time
import logs
import sys
import os

# Set up app environment
sys.path.append("/firm/bin")

import recovery_utils
from hal import osk

# Clean up/fix the main firmware package after a failed update.
# Update failure will likely come from a power outage while installing
# either the update package or update signature.
#
# Post-update firmware switchout occurs in the following order:
#   <firmware>.img.sig -> <firmware>.img.sig.old
#   <firmware>.img -> <firmware>.img.old
#   <firmware>-update.img.sig -> <firmware>.img.sig
#   <firmware>-update.img -> <firmware>.img
#
# There are a couple modes of failure that will require different fixes:
#   Case 1: Missing sig: OLD FIRMWARE is still installed (try install new)
#   Case 2: No firm/sig: NO FIRMWARE INSTALLED (try install new)
#   Case 3: Missing firm; sig present: NEW FIRMWARE PARTLY INSTALLED (try 
#       to finish install; at worst roll back to old firmware)
# 
# If any of these attempted fixes cannot repair the damage, internet
# recovery is required.
#
def _fixup_bad_update_secure() -> bool:
    # Files from a partially finished upgrade
    old_sig_present = recovery_utils.file_exists("/clock_firm.img.sig.old")
    old_firm_present = recovery_utils.file_exists("/clock_firm.img.old")

    # Actively installed firm/sig (Likely partially installed)
    active_sig_present = recovery_utils.file_exists("/clock_firm.img.sig")
    active_firm_present = recovery_utils.file_exists("/clock_firm.img")

    # Newly downloaded update files
    new_sig_present = recovery_utils.file_exists("/clock_firm.img.sig.new")
    new_firm_present = recovery_utils.file_exists("/clock_firm.img.new")

    # EDGE CASE (active firm fully installed) -> FIX: firm corrupt; install new copy
    if active_firm_present and active_sig_present:
        # Try to bail out of this one (super unlikely but worth a shot)
        if new_sig_present and new_firm_present:
            logs.print_info("recovery", "trying local update install")
            recovery_utils.install_new_firmware_local()
            return True

        logs.print_warning("recovery", "stg1 fail: installed firm corrupt")

    # Case 1 (sig missing) -> FIX: attempt to install local firmware update.
    elif active_firm_present:
        if not new_sig_present or not new_firm_present:
            logs.print_warning("recovery", "stg1 fail: no active sig/firm present")
            return False
        
        recovery_utils.install_new_firmware_local()
        return True

    # Case 3 (firm missing) -> FIX: attempt to finish local firmware update.
    elif active_sig_present:
        # Easy fix: only need to install the new firm
        if new_firm_present:
            os.rename("/clock_firm.img.new", "/clock_firm.img")
            return True
        
        # Missing new firm; try to roll back to old firmware
        if old_sig_present and old_firm_present:
            recovery_utils.install_new_firmware_local(".old")
            return True
        
        # New firmware isn't present and neither is old firmware?
        logs.print_warning("recovery", "stg1 fail: no firms present")

    # Case 2 (nothing's there) -> FIX: attempt to install local firmware update.
    else:
        # Install new firm first (ideally)
        if new_firm_present and new_sig_present:
            recovery_utils.install_new_firmware_local()
            return True
        
        # Maybe old firm is still present?
        if old_firm_present and old_sig_present:
            recovery_utils.install_new_firmware_local(".old")
            return True
        
        logs.print_warning("recovery", "stg1 fail: no intact firms")

    return False


# Insecure variant (TODO: later)
def _fixup_bad_update() -> bool:
    logs.print_warning("recovery", "stg1 fail: mode not supported")
    return False


# Recovery firmware has two big jobs (the first one to execute correctly
# returns and the system reboots):
# 
# - Clean up after an update if the device wasn't shut down cleanly (think
#       new firmware downloaded and written but keys/image weren't moved
#       into the boot path)
#
# - Enter internet recovery mode and download a fresh copy of the firmware
#       to be installed. Hashes are checked but signature validation is not
#       performed by the recovery code.
#
# If neither of these two processes can repair the system or if recovery.img
# itself is damaged, the device must be reimaged/repaired with a UART recovery
# payload.
def app_main(nvs: ReadOnlyNVS):
    logs.print_warning("recovery", "booted recovery firm")

    # firmfs size:
    f_bsize, _, f_blocks, f_bfree, _, _, _, _, _, _ = os.statvfs("/firm")
    print(f"firmfs free/size: {f_bsize * f_bfree}/{f_bsize * f_blocks} B")

    # prod id check (to avoid cross-installing firmwares)
    prod_id = nvs.get_str("prod_id")

    if prod_id != "esp32_alarm_clock":
        logs.print_error("recovery", f"bad prod_id: {prod_id}")
        raise OSError("EINVAL")
    
    # TODO: Abort if we're booting from SD.

    # Perform stage one recovery. Secure boot recovery is significantly more difficult
    # than recovering with signature checks disabled.
    stage_one_successful = False
    
    if nvs.get_i32("dis_sig_verif") != 0:
        stage_one_successful = _fixup_bad_update()
    else:
        stage_one_successful = _fixup_bad_update_secure()

    if stage_one_successful:
        logs.print_info("recovery", "NOR backup installed")
        machine.reset()

    # Perform stage 2 recovery. To actually develop this will require a lot of time
    # and development effort (and working hardware to test on)
    from hal import peripherals
    from hal.peripherals import FBCON
    FBCON.write_line("i: booted recovery firm (c) 2026")
    FBCON.write_line("W: ATTEMPTING TO RECOVER DEVICE!")
    peripherals.init()

    try:
        from internet_recovery import main
        main.main()

        # System exit SHOULD be called in normal operation.

    except Exception as ie:
        logs.print_error("recovery", "fatal exception in firm")
        FBCON.set_hidden(False)
        FBCON.write_line("f: panic in recovery mode")
        sys.print_exception(ie)
        time.sleep(5)

    except SystemExit as exit:

        if exit.value == 0:  # type: ignore
            logs.print_info("recovery", "installed internet firm")
            osk.prompt_ok("Recovery", ["Recovery", "successful!", "Reboot?"])

            machine.reset()
    
        FBCON.set_hidden(False)
        FBCON.write_line("w: recovery failed")
        logs.print_error("recovery", "stg2 fail. UART boot req'd")
        time.sleep(10)

    machine.reset()