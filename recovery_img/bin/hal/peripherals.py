from hal.drivers import ssd1309_legacy, wifi, fbcon
from machine import Pin, ADC, I2C
from micropython import const

# HW PIN DEFS
_PIN_DIR_UP = const(27)
_PIN_DIR_LEFT = const(26)
_PIN_DIR_DOWN = const(33)
_PIN_DIR_RIGHT = const(32)
_PIN_CONFIRM = const(23)
_PIN_BACK = const(22)
_PIN_SNOOZE = const(5)

_PIN_VSENSE = const(36)

_PIN_SD_MOSI = const(13)
_PIN_SD_MISO = const(12)
_PIN_SD_CLK = const(14)
_PIN_SD_CS = const(15)

_OLED_I2C_BUS_ID = const(0)
_OLED_I2C_FREQ = const(1_000_000)
_PIN_OLED_SCL = const(18)
_PIN_OLED_SDA = const(19)

# TODO: Determine if using D25/26 improves speaker driving
_PIN_SPKR_OUT = const(25)

# PIN DRIVES
BTN_DIR_UP = Pin(_PIN_DIR_UP, Pin.IN, Pin.PULL_UP)
BTN_DIR_LEFT = Pin(_PIN_DIR_LEFT, Pin.IN, Pin.PULL_UP)
BTN_DIR_DOWN = Pin(_PIN_DIR_DOWN, Pin.IN, Pin.PULL_UP)
BTN_DIR_RIGHT = Pin(_PIN_DIR_RIGHT, Pin.IN, Pin.PULL_UP)

BTN_CONFIRM = Pin(_PIN_CONFIRM, Pin.IN, Pin.PULL_UP)
BTN_BACK = Pin(_PIN_BACK, Pin.IN, Pin.PULL_UP)
BTN_SNOOZE = Pin(_PIN_SNOOZE, Pin.IN, Pin.PULL_UP)

POWER_SENSE = ADC(Pin(_PIN_VSENSE, Pin.IN), atten=ADC.ATTN_11DB)

# SD: Unused in recovery firmware (not mounted with NOR boot; SD boot unsupported)

DISPLAY = ssd1309_legacy.Display(I2C(_OLED_I2C_BUS_ID, freq=_OLED_I2C_FREQ), flip=True)

# Speaker: Not required in recovery firmware

# Software devices
NIC = wifi.WiFiManager()
FBCON = fbcon.GLOBAL_FBCON


def init():
    """
    Fully initialize all peripheral hardware. Most of the hardware has already been
    partially initialized, but network/display/pwr_sense require a bit more.
    """
    
    # TODO: Make less ANNOYINGLY NOISY (set vcom_desel/precharge/clock div)
    # see https://www.hpinfotech.ro/SSD1309.pdf
    NIC.bring_up()

    # TODO: start pwr_sense monitoring driver to detect power loss events and prevent
    # the device from wasting CMOS battery energy

    # init done
    DISPLAY.present()
