from __nvs_perms import ReadOnlyNVS
import bootrom
import time
import logs
import sys
import os

sys.path.append("/firm/bin")
sys.path.append("/firm/app")

from hal.audio_sampled import kill_ulp
from hal import peripherals
import main

def app_main(nvs: ReadOnlyNVS):
    try:
        with open("/firm/version") as f:
            logs.print_info("app", f"appver {f.read().strip()}")

        peripherals.init()

        # TODO: TEST THE UPDATED OSK.
        main.main()
    
    except BaseException as ie:
        sys.print_exception(ie)
        kill_ulp() # prevent irritating noises
        time.sleep(5)
        bootrom.reboot_to_recovery()

