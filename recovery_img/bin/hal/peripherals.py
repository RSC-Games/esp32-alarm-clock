from hal import wifi, fbcon, ssd1309
from machine import Pin, ADC, I2C
from micropython import const
from time import sleep_ms

_DEBOUNCE_INT_MS = const(150)

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

DISPLAY = ssd1309.Display(I2C(_OLED_I2C_BUS_ID, freq=_OLED_I2C_FREQ), flip=True)

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


# Return button state if pressed, after waiting on the state to change.
def get_button_wait(button: Pin, wait_release=False) -> bool:
    """
    Determine the current button state. If it's pressed, wait for it to be released
    (if wait_release is set). Acts as a rudimentary debouncer.
    """
    if not get_button(button):
        return False
    
    sleep_ms(_DEBOUNCE_INT_MS)

    while wait_release and not get_button(button):
        sleep_ms(5)

    return True

# Wait until all buttons have been released.
def wait_buttons_all_released():
    """
    Wait until all buttons have been released (prevent other menus from erroneously
    registering inputs)
    """
    buttons = [BTN_DIR_UP, BTN_DIR_DOWN, BTN_DIR_RIGHT, BTN_DIR_LEFT, BTN_CONFIRM, 
               BTN_BACK, BTN_SNOOZE]

    while True:
        button_states = [button for button in buttons if get_button(button)]

        if len(button_states) == 0:
            break

def get_button(button: Pin) -> bool:
    """
    Immediately determine button state without waiting for a release.
    """
    return not button.value()