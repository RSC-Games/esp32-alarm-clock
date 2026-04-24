from micropython import const
from hal import peripherals
import xglcd_font

GLOBAL_FBCON = None

_LCD_VERTICAL = const(64)
_LINE_HEIGHT_PX = const(6)
_CONSOLE_MAX_LINES = const(_LCD_VERTICAL // _LINE_HEIGHT_PX + 1)

class FBConsole:
    """
    Named after the Linux frame buffer console. Shows log messages on screen
    during the recovery process. The console can be hidden if GUI elements
    are being drawn on screen.
    """

    def __init__(self, hidden: bool):
        global GLOBAL_FBCON

        if GLOBAL_FBCON is not None:
            raise OSError("EEXISTS")

        self.font = xglcd_font.XglcdFont("/firm/res/fonts/Tiny3x5.c", 3, 5)
        self.lines = []
        self.hidden = hidden
        self.total_lines = 0
        GLOBAL_FBCON = self

    def set_hidden(self, hidden: bool):
        self.hidden = hidden

    def write_line(self, line: str):
        lines = line.split("\n")

        for n_line in lines:
            self.lines.append(n_line)
            self.total_lines += 1

        if len(self.lines) > _CONSOLE_MAX_LINES:
            self.lines.pop(0)

        if not self.hidden:
            self.redraw_console()

    def write(self, c: str):
        if "\n" in c:
            self.lines.append("")

            if len(self.lines) > _CONSOLE_MAX_LINES:
                self.lines.pop(0)

        self.lines[-1] += c

    def redraw_console(self):
        peripherals.DISPLAY.clear_buffers()

        line_offset = -3 if len(self.lines) == _CONSOLE_MAX_LINES else 0

        # Only write as many lines as exist to the framebuffer
        for i in range(min(len(self.lines), _CONSOLE_MAX_LINES)):
            peripherals.DISPLAY.draw_text(2, i * _LINE_HEIGHT_PX + line_offset, self.lines[i], self.font)

        peripherals.DISPLAY.draw_line(127, 63, 127, _LCD_VERTICAL * (len(self.lines) // self.total_lines))
        peripherals.DISPLAY.present()


GLOBAL_FBCON = FBConsole(False)