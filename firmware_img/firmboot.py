from __nvs_perms import ReadOnlyNVS
import bootrom
import time
import logs
import sys
import os

sys.path.append("/firm/bin")
sys.path.append("/firm/app")

from hal import peripherals
import main

# Hellooo clock firm! This firm runs the entire clock operating system
# and supplies its many features. Here's what needs to be done:
#
# TODO: Online update support (DON'T UPDATE RECOVERY AND CLOCK_FIRM AT THE
#   SAME TIME!!!)
# TODO: Clean animations/scrolling for menus (with custom fonts)
# TODO: Main clock screen (shows time in BIG LETTERS with date underneath) 
#   (with TIME / ALARM / SETTINGS row)
# TODO: Dimmable brightness (with snooze bar)
# TODO: Play music/beeps when alarm expires (ULP DAC DMA driver required)
# TODO: Power loss driver (shut off peripheral hardware on power loss)
# TODO: NTP time sync once every day + daylight savings time (Need separate 
#   thread with pm driver)
# TODO: Menu with MANY MANY OPTIONS (and button hints):
#       - Time -> (TZ: <timezone>; Set Timezone / Auto DST Adjust)
#       - Alarms -> (Alarms: <alarm_cnt>; Manage Alarms / Add Alarm (set time/date + set alarm type))
#       - Network -> (Active: <yes>/NET: <ssid>; WiFi Enabled / Manage Networks / Register New)
#       - Advanced -> (NVS: <unlocked>; Secure Boot / Allow SD Boot / Boot MPY/BIN / Lock NVS)
#       - System Info -> (SN: <serial>/prod: <prod_id>/ver: <version>)
#       - Licenses -> (Show licensing info for MicroPython, ucrypto, display driver)
def app_main(nvs: ReadOnlyNVS):
    try:
        # firmfs size:
        f_bsize, _, f_blocks, f_bfree, _, _, _, _, _, _ = os.statvfs("/firm")
        print(f"firmfs free/size: {f_bsize * f_bfree}/{f_bsize * f_blocks} B")

        with open("/firm/version") as f:
            logs.print_info("app", f"got version {f.read().strip()}")

        peripherals.init()

        # TODO: TEST THE UPDATED OSK.
        main.main()
    
    except BaseException as ie:
        sys.print_exception(ie)
        time.sleep(5)
        bootrom.reboot_to_recovery()

