from machine import Pin, ADC, DAC, I2C, SDCard, freq
from hal.drivers import wifi, ssd1309
from micropython import const
from time import sleep_ms
from vfs import mount
from hal import fbcon
import logs

_DEBOUNCE_INT_MS = const(90)

# HW PIN DEFS
_PIN_DIR_UP = const(27)
_PIN_DIR_LEFT = const(21)  # NOTE: CHANGE ON BLUEPRINT
_PIN_DIR_DOWN = const(33)
_PIN_DIR_RIGHT = const(32)
_PIN_CONFIRM = const(23)
_PIN_BACK = const(22)
_PIN_SNOOZE = const(5)

_PIN_VSENSE = const(36)

_SD_BUS_SLOT = const(3)
_SD_BUS_FREQ = const(24_000_000)
_PIN_SD_MOSI = const(13)
_PIN_SD_MISO = const(12)
_PIN_SD_CLK = const(14)
_PIN_SD_CS = const(15)

_OLED_I2C_BUS_ID = const(0)
_OLED_I2C_FREQ = const(400_000)

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

DISPLAY = ssd1309.Display(I2C(_OLED_I2C_BUS_ID, freq=_OLED_I2C_FREQ), flip=True)

SPEAKER = DAC(Pin(_PIN_SPKR_OUT, Pin.OUT))

# Software devices
NIC = wifi.WiFiManager()
FBCON = fbcon.GLOBAL_FBCON


def init():
    """
    Fully initialize all peripheral hardware. Most of the hardware has already been
    partially initialized, but network/display/pwr_sense require a bit more.
    """

    # Kick up the CPU clock (currently powersave not required)
    freq(240_000_000)

    # TODO: Make less ANNOYINGLY NOISY (set vcom_desel/precharge/clock div)
    # see https://www.hpinfotech.ro/SSD1309.pdf
    # TODO: Background thread
    #NIC.bring_up()

    # XXX: Don't use in production (brightness should be configurable!)
    # TODO: Relocate to SSD1309 driver
    DISPLAY.contrast(0)
    DISPLAY.set_precharge(1, 1)
    DISPLAY.set_vcomdesel(0)

    # XXX: fbcon auto show not supported
    FBCON.set_hidden(True)

    # TODO: start pwr_sense monitoring driver to detect power loss events and prevent
    # the device from wasting CMOS battery energy

    if not _mount_sd("/sd"):
        logs.print_warning("hal", "/sd node not accessible")

def _mount_sd(mount_pt: str) -> bool:
    sd = None

    try:
        sd = SDCard(
            slot=_SD_BUS_SLOT,
            freq=_SD_BUS_FREQ,
            sck=Pin(_PIN_SD_CLK, Pin.OUT),
            miso=Pin(_PIN_SD_MISO, Pin.OUT), 
            mosi=Pin(_PIN_SD_MOSI, Pin.OUT), 
            cs=Pin(_PIN_SD_CS, Pin.OUT)
        )
    except OSError:
        logs.print_error("hal", "sd card not present/responding")
        return False

    try:
        mount(sd, mount_pt)
    except OSError:
        logs.print_error("hal", "sd card unmountable/corrupt")
        return False

    return True


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

def get_snooze() -> bool:
    """
    Get the current snooze bar state.
    """
    return get_button(BTN_SNOOZE)