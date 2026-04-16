from micropython import const
from time import ticks_ms

_COLOR_RED = const("\033[31m")
_COLOR_YELLOW = const("\033[33m")
_COLOR_GREEN = const("\033[32m")
_COLOR_RESET = const("\033[0m")

_LOG_ERROR = const(2)
_LOG_WARNING = const(1)
_LOG_INFO = const(0)
_LOG_LEVEL = const(_LOG_INFO)

# TODO: Should add a log to file element (for firmwares, not bootrom)
def print_info(unit: str, msg: str) -> None:
    if _LOG_LEVEL <= _LOG_INFO:
        print(f"{_COLOR_GREEN}I ({ticks_ms()}) {unit}: {msg}{_COLOR_RESET}")

def print_warning(unit: str, msg: str) -> None:
    if _LOG_LEVEL <= _LOG_WARNING:
        print(f"{_COLOR_YELLOW}W ({ticks_ms()}) {unit}: {msg}{_COLOR_RESET}")

def print_error(unit: str, msg: str) -> None:
    if _LOG_LEVEL <= _LOG_ERROR:
        print(f"{_COLOR_RED}E ({ticks_ms()}) {unit}: {msg}{_COLOR_RESET}")