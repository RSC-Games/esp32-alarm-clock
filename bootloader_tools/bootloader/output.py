_ANSI_ORANGE = "\033[38;5;208m"
_ANSI_RESET = "\033[0m"

def print_tool(print_str: str, **kwargs):
    """
    Print text from the serial tool (not bootrom) in orange to easier distinguish
    the log messages.
    """
    print(f"{_ANSI_ORANGE}[rcm-tool] {print_str}{_ANSI_RESET}", **kwargs)