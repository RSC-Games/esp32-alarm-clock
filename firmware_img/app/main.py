from hal import peripherals as dev

from ui.clock import Clock, Alarm  # TODO: alarm should not be used here
import config
import time
import logs

# Hellooo clock firm! This firm runs the entire clock operating system
# and supplies its many features. Here's what needs to be done:
#
# TODO: Panic handler (collects system state and reports errors)
#   File logging can be done with dupterm()
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
    clock.alarms.append(Alarm((8, 45, -1, -1), (0, 1, 2, 3, 4)))

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