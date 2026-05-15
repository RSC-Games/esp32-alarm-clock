from hal import peripherals as dev
from hal import audio_sampled
from hal import osk
import xglcd_font
import time

def main():
    audio_sampled.play_oneshot("/sd/other/02 - One Step Closer-normal.wav")

    big_font = xglcd_font.XglcdFont("/firm/res/fonts/Bitstream_Vera35x32.c", 35, 32, 48, 11)
    dev.DISPLAY.draw_text(0, 15, "12:30", big_font)
    dev.DISPLAY.present()
    time.sleep(5)

    # NOTE: Showing advanced stuff on screen doesn't play nice with the buffer refill ISR
    # we can only play music for alarms because of this (without a more advanced driver)
    # may be worth increasing the file read speed
    osk.prompt_ok("Hello!", ["testing osk print", "does ok work", "yes or no", "hehe"])
    osk.prompt_yn("Hello!", ["testing osk print", "does ok work", "yes or no", "hehe"])

    osk.prompt_text(osk.LAYOUT_KEYBOARD, 50, False)