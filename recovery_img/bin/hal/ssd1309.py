"""MicroPython SSD1309 OLED monochrom display driver."""
# Modified version of the driver found here: https://github.com/rdagger/micropython-ssd1309/tree/master
# NOTE: Recovery bootloader needs a super slimmed down version to meet space constraints.
from machine import I2C
from micropython import const
from framebuf import FrameBuffer, MONO_VLSB

# Command constants from display datasheet
_CONTRAST_CONTROL = const(0x81)
_ENTIRE_DISPLAY_ON = const(0xA4)
#_ALL_PIXELS_ON = const(0XA5)
_INVERSION_OFF = const(0xA6)
#_INVERSION_ON = const(0XA7)
_DISPLAY_OFF = const(0xAE)
_DISPLAY_ON = const(0XAF)
#_NOP = const(0xE3)
#_COMMAND_LOCK = const(0xFD)
_CHARGE_PUMP = const(0x8D)

# Scrolling commands
# SCROLL_HORIZONTAL_RIGHT = const(0x26)
# SCROLL_HORIZONTAL_LEFT = const(0x27)
# SCROLL_VERTICAL_RIGHT = const(0x29)
# SCROLL_VERTICAL_LEFT = const(0x2A)
# SCROLL_BY_ONE_RIGHT = const(0x2C)
# SCROLL_BY_ONE_LEFT = const(0x2D)
# SCROLL_SETUP_VERTICAL_AREA = const(0xA3)
# SCROLL_DEACTIVATE = const(0x2E)
# SCROLL_ACTIVATE = const(0x2F)

# Addressing commands
#_LOW_CSA_IN_PAM = const(0x00)
#_HIGH_CSA_IN_PAM = const(0x10)
_MEMORY_ADDRESSING_MODE = const(0x20)
_COLUMN_ADDRESS = const(0x21)
_PAGE_ADDRESS = const(0x22)
#_PSA_IN_PAM = const(0xB0)
_DISPLAY_START_LINE = const(0x40)
_SEGMENT_MAP_REMAP = const(0xA0)
_SEGMENT_MAP_FLIP = const(0xA1)
_MUX_RATIO = const(0xA8)
_COM_OUTPUT_NORMAL = const(0xC0)
_COM_OUTPUT_FLIP = const(0xC8)
_DISPLAY_OFFSET = const(0xD3)
_COM_PINS_HW_CFG = const(0xDA)
#_GPIO = const(0xDC)

# Timing and driving scheme commands
_DISPLAY_CLOCK_DIV = const(0xd5)
_PRECHARGE_PERIOD = const(0xd9)
_VCOM_DESELECT_LEVEL = const(0xdb)


class Display(object):
    """Serial and I2C interface for SD1309 monochrome OLED display.

    Note:  All coordinates are zero based.
    """

    def __init__(self, i2c: I2C | None=None, address=0x3C, width=128, height=64, flip=False):
        """Constructor for Display.

        Args:
            i2c (Optional Class I2C):  I2C interface for display
            address (Optional int): I2C address
            width (Optional int): Screen width (default 128)
            height (Optional int): Screen height (default 64)
            flip (bool):True=Rotate 180 degrees, False=0 degrees (default)
        """
        if i2c is not None:
            self.address = address
            self.i2c = i2c
            self.write_cmd = self.write_cmd_i2c
            self.write_data = self.write_data_i2c
        else:
            raise RuntimeError('An I2C interface is required.')
        
        self.width = width
        self.height = height
        self.pages = self.height // 8
        self.byte_width = -(-width // 8)  # Ceiling division
        self.buffer_length = self.byte_width * height

        # Buffer
        self.mono_image = bytearray(self.buffer_length)

        # Frame Buffer
        self.monoFB = FrameBuffer(self.mono_image, width, height, MONO_VLSB)
        self.clear_buffers()

        # Send initialization commands
        for cmd in (
                    _DISPLAY_OFF,
                    _DISPLAY_CLOCK_DIV, 0x80,
                    _MUX_RATIO, self.height - 1,
                    _DISPLAY_OFFSET, 0x00,
                    _DISPLAY_START_LINE,
                    _CHARGE_PUMP, 0x14,
                    _MEMORY_ADDRESSING_MODE, 0x00,
                    _SEGMENT_MAP_FLIP if flip else _SEGMENT_MAP_REMAP,
                    _COM_OUTPUT_FLIP if flip else _COM_OUTPUT_NORMAL,
                    _COM_PINS_HW_CFG, 0x02 if (self.height == 32 or
                                               self.height == 16) and
                                               (self.width != 64)
                    else 0x12,
                    _CONTRAST_CONTROL, 0xFF,
                    _PRECHARGE_PERIOD, 0xF1,
                    _VCOM_DESELECT_LEVEL, 0x40,
                    _ENTIRE_DISPLAY_ON,  # output follows RAM contents
                    _INVERSION_OFF,  # not inverted
                    _DISPLAY_ON):  # on
            self.write_cmd(cmd)

        self.clear_buffers()
        self.present()

    def clear_buffers(self):
        """Clear buffer.
        """
        self.monoFB.fill(0x00)

    def draw_hline(self, x, y, w, invert=False):
        """Draw a horizontal line.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            w (int): Width of line.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        if self.is_off_grid(x, y, x + w - 1, y):
            return
        self.monoFB.hline(x, y, w, int(invert ^ 1))

    def draw_letter(self, x, y, letter: str, font, invert=False, rotate: int|bool=False):
        """Draw a letter.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            letter (string): Letter to draw.
            font (XglcdFont object): Font.
            invert (bool): Invert color
            rotate (int): Rotation of letter
        """
        fbuf, w, h = font.get_letter(letter, invert=invert, rotate=rotate)

        # Check for errors
        if fbuf is None:
            return w, h
        
        # Offset y for 270 degrees and x for 180 degrees
        if rotate == 180:
            x -= w
        elif rotate == 270:
            y -= h

        self.monoFB.blit(fbuf, x, y)
        return w, h

    def draw_line(self, x1, y1, x2, y2, invert=False):
        """Draw a line using Bresenham's algorithm.

        Args:
            x1, y1 (int): Starting coordinates of the line
            x2, y2 (int): Ending coordinates of the line
            invert (bool): True = clear line, False (Default) = draw line.
        """
        # Check for horizontal line
        if y1 == y2:
            if x1 > x2:
                x1, x2 = x2, x1
            self.draw_hline(x1, y1, x2 - x1 + 1, invert)
            return
        # Check for vertical line
        if x1 == x2:
            if y1 > y2:
                y1, y2 = y2, y1
            self.draw_vline(x1, y1, y2 - y1 + 1, invert)
            return
        # Confirm coordinates in boundary
        if self.is_off_grid(min(x1, x2), min(y1, y2),
                            max(x1, x2), max(y1, y2)):
            return
        self.monoFB.line(x1, y1, x2, y2, invert ^ 1)

    def draw_lines(self, coords, invert=False):
        """Draw multiple lines.

        Args:
            coords ([[int, int],...]): Line coordinate X, Y pairs
            invert (bool): True = clear line, False (Default) = draw line.
        """
        # Starting point
        x1, y1 = coords[0]
        # Iterate through coordinates
        for i in range(1, len(coords)):
            x2, y2 = coords[i]
            self.draw_line(x1, y1, x2, y2, invert)
            x1, y1 = x2, y2

    def draw_pixel(self, x, y, invert=False):
        """Draw a single pixel.

        Args:
            x (int): X position.
            y (int): Y position.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        if self.is_off_grid(x, y, x, y):
            return
        
        self.monoFB.pixel(x, y, int(invert ^ 1))

    def draw_rectangle(self, x, y, w, h, invert=False):
        """Draw a rectangle.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            w (int): Width of rectangle.
            h (int): Height of rectangle.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        self.monoFB.rect(x, y, w, h, int(invert ^ 1))

    def draw_text(self, x: int, y: int, text: str, font, invert=False,
                  rotate=0, spacing=1):
        """Draw text.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            text (string): Text to draw.
            font (XglcdFont object): Font.
            invert (bool): Invert color
            rotate (int): Rotation of letter
            spacing (int): Pixels between letters (default: 1)
        """
        for letter in text:
            # Get letter array and letter dimensions
            w, h = self.draw_letter(x, y, letter, font, invert, rotate)

            # Stop on error
            if w == 0 or h == 0:
                return
            
            if rotate == 0:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x + w, y, spacing, h, invert ^ 1)
                    
                # Position x for next letter
                x += (w + spacing)

            elif rotate == 90:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x, y + h, w, spacing, invert ^ 1)
                # Position y for next letter
                y += (h + spacing)
            elif rotate == 180:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x - w - spacing, y, spacing,
                                        h, invert ^ 1)
                # Position x for next letter
                x -= (w + spacing)
            elif rotate == 270:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x, y - h - spacing, w, spacing,
                                        invert ^ 1)
                # Position y for next letter
                y -= (h + spacing)
            else:
                print("Invalid rotation.")
                return

    def draw_text8x8(self, x, y, text, color=1):
        """Draw text using built-in MicroPython 8x8 bit font.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            text (string): Text to draw.
        """
        # Confirm coordinates in boundary
        if self.is_off_grid(x, y, x + 8, y + 8):
            return
        self.monoFB.text(text, x, y, color)

    def draw_vline(self, x, y, h, invert=False):
        """Draw a vertical line.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            h (int): Height of line.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        # Confirm coordinates in boundary
        if self.is_off_grid(x, y, x, y + h):
            return
        self.monoFB.vline(x, y, h, int(invert ^ 1))

    def fill_rectangle(self, x, y, w, h, invert: int|bool=False):
        """Draw a filled rectangle.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            w (int): Width of rectangle.
            h (int): Height of rectangle.
            visble (bool): True (Default) = draw line, False = clear line.
        """
        if self.is_off_grid(x, y, x + w - 1, y + h - 1):
            return
        self.monoFB.fill_rect(x, y, w, h, int(invert ^ 1))

    def is_off_grid(self, xmin, ymin, xmax, ymax):
        """Check if coordinates extend past display boundaries.

        Args:
            xmin (int): Minimum horizontal pixel.
            ymin (int): Minimum vertical pixel.
            xmax (int): Maximum horizontal pixel.
            ymax (int): Maximum vertical pixel.
        Returns:
            boolean: False = Coordinates OK, True = Error.
        """
        if xmin < 0:
            print(f'warn-x: {xmin} < 0')
            return True
        if ymin < 0:
            print(f'warn-y: {ymin} < 0')
            return True
        if xmax >= self.width:
            print(f'warn-x: {xmax} > {self.width-1}')
            return True
        if ymax >= self.height:
            print(f'warn-y: {ymax} > {self.height-1}')
            return True
        return False

    def present(self):
        """Present image to display.
        """
        x0 = 0
        x1 = self.width - 1
        if self.width == 64:
            # displays with width of 64 pixels are shifted by 32
            x0 += 32
            x1 += 32
        self.write_cmd(_COLUMN_ADDRESS)
        self.write_cmd(x0)
        self.write_cmd(x1)
        self.write_cmd(_PAGE_ADDRESS)
        self.write_cmd(0)
        self.write_cmd(self.pages - 1)
        self.write_data(self.mono_image)

    def contrast(self, contrast: int):
        """Change the current display contrast (brightness)."""
        self.write_cmd(_CONTRAST_CONTROL)
        self.write_cmd(contrast)

    def sleep(self):
        """Put display to sleep."""
        self.write_cmd(_DISPLAY_OFF)

    def wake(self):
        """Wake display from sleep."""
        self.write_cmd(_DISPLAY_ON)

    def write_cmd_i2c(self, command, *args):
        """Write command to display using I2C.

        Args:
            command (byte): Display command code.
            *args (optional bytes): Data to transmit.
        """
        # 0x80 -> Co=1, D/C#=0
        self.i2c.writeto_mem(self.address, 0x80, bytearray([command]))
        if args:
            #  0x40 -> Co=0, D/C#=1
            self.i2c.writeto_mem(self.address, 0x40, bytearray(args))

    def write_data_i2c(self, data):
        """Write data to display.

        Args:
            data (bytes): Data to transmit.
        """
        #  0x40 -> Co=0, D/C#=1
        self.i2c.writeto_mem(self.address, 0x40, data)