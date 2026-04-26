from hal import peripherals as dev
from hal import osk
import xglcd_font
import time

def main():
    big_font = xglcd_font.XglcdFont("/firm/res/fonts/Bitstream_Vera35x32.c", 35, 32, 48, 11)
    dev.DISPLAY.draw_text(0, 15, "12:30", big_font)
    dev.DISPLAY.present()
    time.sleep(50)


    osk.prompt_ok("Hello!", ["testing osk print", "does ok work", "yes or no", "hehe"])
    osk.prompt_yn("Hello!", ["testing osk print", "does ok work", "yes or no", "hehe"])

    osk.prompt_text(osk.LAYOUT_KEYBOARD, 50, False)