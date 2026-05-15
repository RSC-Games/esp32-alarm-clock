from hal import peripherals as dev
from hal import audio_sampled
from hal import osk
import xglcd_font
import time

# Hellooo clock firm! This firm runs the entire clock operating system
# and supplies its many features. Here's what needs to be done:
#
# TODO: Online update support (DON'T UPDATE RECOVERY AND CLOCK_FIRM AT THE
#   SAME TIME!!!)
# TODO: Clean animations/scrolling for menus (with custom fonts)
# TODO: see clock.py
# TODO: Dimmable brightness (with snooze bar)
# TODO: Play music/beeps when alarm expires (ULP DAC DMA driver required; written)
# TODO: Power loss driver (shut off peripheral hardware on power loss)
# TODO: NTP time sync once every day + daylight savings time (Need separate 
#   thread with pm driver)
# TODO: Menu with MANY MANY OPTIONS (and button hints):
#       - Time -> (TZ: <timezone>; Set Timezone / Auto DST Adjust)
#       - Alarms -> (Alarms: <alarm_cnt>; Manage Alarms / Add Alarm (set time/date + set alarm type))
#       - Network -> (Active: <yes>/NET: <ssid>; WiFi Enabled / Manage Networks / Register New)
#       - Advanced -> (NVS: <unlocked>; Secure Boot / Allow SD Boot / Boot MPY/BIN / Lock NVS)
#       - System Info -> (SN: <serial>/prod: <prod_id>/ver: <version>)
#       - Licenses -> (Show licensing info for MicroPython, ucrypto, display driver, xglcd)
def main():
    #audio_sampled.play_oneshot("/sd/other/02 - One Step Closer-slowed.wav")

    #time.sleep(100)

    # WTF: The screen even being ACTIVE is causing us to miss deadlines ???
    clk_time = "12:30"
    big_font = xglcd_font.XglcdFont("/firm/res/fonts/Bitstream_Vera35x32.c", 35, 32, 48, 11)
    clock_width = big_font.measure_text(clk_time)
    dev.DISPLAY.draw_text((128 - clock_width) // 2, 12, clk_time, big_font)
    dev.DISPLAY.present()

    time.sleep(100)

    # NOTE: Showing advanced stuff on screen doesn't play nice with the buffer refill ISR
    # we can only play music for alarms because of this (without a more advanced driver)
    # may be worth increasing the file read speed....
    osk.prompt_ok("Hello!", ["testing osk print", "does ok work", "yes or no", "hehe"])
    osk.prompt_yn("Hello!", ["testing osk print", "does ok work", "yes or no", "hehe"])

    osk.prompt_text(osk.LAYOUT_KEYBOARD, 50, False)