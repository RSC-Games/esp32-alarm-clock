"""MicroPython SSD1309 OLED monochrom display driver."""
# Modified version of the public driver from this repo: https://github.com/rdagger/micropython-ssd1309/tree/master
from machine import I2C
from math import cos, sin, pi, radians
from micropython import const  # type: ignore
from framebuf import FrameBuffer, GS8, MONO_HMSB, MONO_VLSB  # type: ignore

# Command constants from display datasheet
_CONTRAST_CONTROL = const(0x81)
_ENTIRE_DISPLAY_ON = const(0xA4)
_ALL_PIXELS_ON = const(0XA5)
_INVERSION_OFF = const(0xA6)
_INVERSION_ON = const(0XA7)
_DISPLAY_OFF = const(0xAE)
_DISPLAY_ON = const(0XAF)
_NOP = const(0xE3)
_COMMAND_LOCK = const(0xFD)
_CHARGE_PUMP = const(0x8D)

# Scrolling commands
_SCROLL_HORIZONTAL_RIGHT = const(0x26)
_SCROLL_HORIZONTAL_LEFT = const(0x27)
_SCROLL_VERTICAL_RIGHT = const(0x29)
_SCROLL_VERTICAL_LEFT = const(0x2A)
_SCROLL_BY_ONE_RIGHT = const(0x2C)
_SCROLL_BY_ONE_LEFT = const(0x2D)
_SCROLL_SETUP_VERTICAL_AREA = const(0xA3)
_SCROLL_DEACTIVATE = const(0x2E)
_SCROLL_ACTIVATE = const(0x2F)

# Addressing commands
_LOW_CSA_IN_PAM = const(0x00)
_HIGH_CSA_IN_PAM = const(0x10)
_MEMORY_ADDRESSING_MODE = const(0x20)
_COLUMN_ADDRESS = const(0x21)
_PAGE_ADDRESS = const(0x22)
_PSA_IN_PAM = const(0xB0)
_DISPLAY_START_LINE = const(0x40)
_SEGMENT_MAP_REMAP = const(0xA0)
_SEGMENT_MAP_FLIP = const(0xA1)
_MUX_RATIO = const(0xA8)
_COM_OUTPUT_NORMAL = const(0xC0)
_COM_OUTPUT_FLIP = const(0xC8)
_DISPLAY_OFFSET = const(0xD3)
_COM_PINS_HW_CFG = const(0xDA)
_GPIO = const(0xDC)

# Timing and driving scheme commands
_DISPLAY_CLOCK_DIV = const(0xd5)
_PRECHARGE_PERIOD = const(0xd9)
_VCOM_DESELECT_LEVEL = const(0xdb)

class Display(object):
    """
    I2C interface for SD1309 monochrome OLED display.

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

    def clear_buffers(self) -> None:
        """Clear buffer.
        """
        self.monoFB.fill(0x00)

    def draw_bitmap(self, path: str, x: int, y: int, w: int, h: int, invert=False, rotate=0) -> None:
        """Load MONO_HMSB bitmap from disc and draw to screen.

        Args:
            path (string): Image file path.
            x (int): x-coord of image.
            y (int): y-coord of image.
            w (int): Width of image.
            h (int): Height of image.
            invert (bool): True = invert image, False (Default) = normal image.
            rotate(int): 0, 90, 180, 270
        Notes:
            w x h cannot exceed 2048
        """
        array_size = w * h
        with open(path, "rb") as f:
            buf = bytearray(f.read(array_size))
            fb = FrameBuffer(buf, w, h, MONO_HMSB)

            if rotate == 0 and invert is True:  # 0 degrees
                fb2 = FrameBuffer(bytearray(array_size), w, h, MONO_HMSB)
                for y1 in range(h):
                    for x1 in range(w):
                        fb2.pixel(x1, y1, fb.pixel(x1, y1) ^ 0x01)
                fb = fb2

            elif rotate == 90:  # 90 degrees
                fb2 = FrameBuffer(bytearray(array_size), h, w, MONO_HMSB)
                for y1 in range(h):
                    for x1 in range(w):
                        if invert is True:
                            fb2.pixel(y1, x1,
                                      fb.pixel(x1, (h - 1) - y1) ^ 0x01)
                        else:
                            fb2.pixel(y1, x1, fb.pixel(x1, (h - 1) - y1))
                fb = fb2

            elif rotate == 180:  # 180 degrees
                fb2 = FrameBuffer(bytearray(array_size), w, h, MONO_HMSB)
                for y1 in range(h):
                    for x1 in range(w):
                        if invert is True:
                            fb2.pixel(x1, y1, fb.pixel((w - 1) - x1,
                                                       (h - 1) - y1) ^ 0x01)
                        else:
                            fb2.pixel(x1, y1,
                                      fb.pixel((w - 1) - x1, (h - 1) - y1))
                fb = fb2

            elif rotate == 270:  # 270 degrees
                fb2 = FrameBuffer(bytearray(array_size), h, w, MONO_HMSB)
                for y1 in range(h):
                    for x1 in range(w):
                        if invert is True:
                            fb2.pixel(y1, x1,
                                      fb.pixel((w - 1) - x1, y1) ^ 0x01)
                        else:
                            fb2.pixel(y1, x1, fb.pixel((w - 1) - x1, y1))
                fb = fb2

            self.monoFB.blit(fb, x, y)

    def draw_bitmap_raw(self, path: str, x: int, y: int, w: int, h: int, invert=False, rotate=0) -> None:
        """Load raw bitmap from disc and draw to screen.

        Args:
            path (string): Image file path.
            x (int): x-coord of image.
            y (int): y-coord of image.
            w (int): Width of image.
            h (int): Height of image.
            invert (bool): True = invert image, False (Default) = normal image.
            rotate(int): 0, 90, 180, 270
        Notes:
            w x h cannot exceed 2048
        """
        if rotate == 90 or rotate == 270:
            w, h = h, w  # Swap width & height if landscape

        buf_size = w * h

        with open(path, "rb") as f:
            if rotate == 0:
                buf = bytearray(f.read(buf_size))

            elif rotate == 90:
                buf = bytearray(buf_size)

                for x1 in range(w - 1, -1, -1):
                    for y1 in range(h):
                        index = (w * y1) + x1
                        buf[index] = f.read(1)[0]

            elif rotate == 180:
                buf = bytearray(buf_size)
                for index in range(buf_size - 1, -1, -1):
                    buf[index] = f.read(1)[0]

            elif rotate == 270:
                buf = bytearray(buf_size)
                for x1 in range(1, w + 1):
                    for y1 in range(h - 1, -1, -1):
                        index = (w * y1) + x1 - 1
                        buf[index] = f.read(1)[0]

            else: # Should never get here
                buf = bytearray()

            if invert:
                for i, _ in enumerate(buf):
                    buf[i] ^= 0xFF

            fbuf = FrameBuffer(buf, w, h, GS8)
            self.monoFB.blit(fbuf, x, y)

    def draw_circle(self, x0: int, y0: int, r: int, invert=False) -> None:
        """Draw a circle.

        Args:
            x0 (int): X coordinate of center point.
            y0 (int): Y coordinate of center point.
            r (int): Radius.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        f = 1 - r
        dx = 1
        dy = -r - r
        x = 0
        y = r
        self.draw_pixel(x0, y0 + r, invert)
        self.draw_pixel(x0, y0 - r, invert)
        self.draw_pixel(x0 + r, y0, invert)
        self.draw_pixel(x0 - r, y0, invert)
        while x < y:
            if f >= 0:
                y -= 1
                dy += 2
                f += dy
            x += 1
            dx += 2
            f += dx
            self.draw_pixel(x0 + x, y0 + y, invert)
            self.draw_pixel(x0 - x, y0 + y, invert)
            self.draw_pixel(x0 + x, y0 - y, invert)
            self.draw_pixel(x0 - x, y0 - y, invert)
            self.draw_pixel(x0 + y, y0 + x, invert)
            self.draw_pixel(x0 - y, y0 + x, invert)
            self.draw_pixel(x0 + y, y0 - x, invert)
            self.draw_pixel(x0 - y, y0 - x, invert)

    def draw_ellipse(self, x0: int, y0: int, a: int, b: int, invert=False) -> None:
        """Draw an ellipse.

        Args:
            x0, y0 (int): Coordinates of center point.
            a (int): Semi axis horizontal.
            b (int): Semi axis vertical.
            invert (bool): True = clear line, False (Default) = draw line.
        Note:
            The center point is the center of the x0,y0 pixel.
            Since pixels are not divisible, the axes are integer rounded
            up to complete on a full pixel.  Therefore the major and
            minor axes are increased by 1.
        """
        a2 = a * a
        b2 = b * b
        twoa2 = a2 + a2
        twob2 = b2 + b2
        x = 0
        y = b
        px = 0
        py = twoa2 * y
        # Plot initial points
        self.draw_pixel(x0 + x, y0 + y, invert)
        self.draw_pixel(x0 - x, y0 + y, invert)
        self.draw_pixel(x0 + x, y0 - y, invert)
        self.draw_pixel(x0 - x, y0 - y, invert)
        # Region 1
        p = round(b2 - (a2 * b) + (0.25 * a2))
        while px < py:
            x += 1
            px += twob2
            if p < 0:
                p += b2 + px
            else:
                y -= 1
                py -= twoa2
                p += b2 + px - py
            self.draw_pixel(x0 + x, y0 + y, invert)
            self.draw_pixel(x0 - x, y0 + y, invert)
            self.draw_pixel(x0 + x, y0 - y, invert)
            self.draw_pixel(x0 - x, y0 - y, invert)
        # Region 2
        p = round(b2 * (x + 0.5) * (x + 0.5) +
                  a2 * (y - 1) * (y - 1) - a2 * b2)
        while y > 0:
            y -= 1
            py -= twoa2
            if p > 0:
                p += a2 - py
            else:
                x += 1
                px += twob2
                p += a2 - py + px
            self.draw_pixel(x0 + x, y0 + y, invert)
            self.draw_pixel(x0 - x, y0 + y, invert)
            self.draw_pixel(x0 + x, y0 - y, invert)
            self.draw_pixel(x0 - x, y0 - y, invert)

    def draw_hline(self, x: int, y: int, w: int, invert=False) -> None:
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

    def draw_letter(self, x: int, y: int, letter: str, font, c=1, rotate: int|bool=False) -> tuple[int, int]:
        """Draw a letter.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            letter (string): Letter to draw.
            font (XglcdFont object): Font.
            invert (bool): Invert color
            rotate (int): Rotation of letter
        """
        fbuf, w, h = font.get_letter(letter, invert=c == 0, rotate=rotate)

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

    def draw_line(self, x1: int, y1: int, x2: int, y2: int, invert=False) -> None:
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

    def draw_lines(self, coords: list[list[int]], invert=False) -> None:
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

    def draw_pixel(self, x: int, y: int, invert=False) -> None:
        """Draw a single pixel.

        Args:
            x (int): X position.
            y (int): Y position.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        if self.is_off_grid(x, y, x, y):
            return
        
        self.monoFB.pixel(x, y, int(invert ^ 1))

    def draw_polygon(self, sides: int, x0: int, y0: int, r: int, invert=False, rotate=0) -> None:
        """Draw an n-sided regular polygon.

        Args:
            sides (int): Number of polygon sides.
            x0, y0 (int): Coordinates of center point.
            r (int): Radius.
            invert (bool): True = clear line, False (Default) = draw line.
            rotate (Optional float): Rotation in degrees relative to origin.
        Note:
            The center point is the center of the x0,y0 pixel.
            Since pixels are not divisible, the radius is integer rounded
            up to complete on a full pixel.  Therefore diameter = 2 x r + 1.
        """
        coords = []
        theta = radians(rotate)
        n = sides + 1
        for s in range(n):
            t = 2.0 * pi * s / sides + theta
            coords.append([int(r * cos(t) + x0), int(r * sin(t) + y0)])

        # Cast to python float first to fix rounding errors
        self.draw_lines(coords, invert)

    def draw_rectangle(self, x: int, y: int, w: int, h: int, invert=False) -> None:
        """Draw a rectangle.

        Args:
            x (int): Starting X position.
            y (int): Starting Y position.
            w (int): Width of rectangle.
            h (int): Height of rectangle.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        self.monoFB.rect(x, y, w, h, int(invert ^ 1))

    def draw_sprite(self, fbuf: FrameBuffer, x: int, y: int, w: int, h: int) -> None:
        """Draw a sprite.
        Args:
            fbuf (FrameBuffer): Buffer to draw.
            x (int): Starting X position.
            y (int): Starting Y position.
            w (int): Width of drawing.
            h (int): Height of drawing.
        """
        x2 = x + w - 1
        y2 = y + h - 1

        if self.is_off_grid(x, y, x2, y2):
            return
        
        self.monoFB.blit(fbuf, x, y)

    def draw_text(self, x: int, y: int, text: str, font, c: int=1, rotate=0, spacing=1) -> None:
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
            w, h = self.draw_letter(x, y, letter, font, c, rotate)

            # Stop on error
            if w == 0 or h == 0:
                return
            
            if rotate == 0:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x + w, y, spacing, h, c)
                    
                # Position x for next letter
                x += (w + spacing)

            elif rotate == 90:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x, y + h, w, spacing, c)
                # Position y for next letter
                y += (h + spacing)
            elif rotate == 180:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x - w - spacing, y, spacing,
                                        h, c)
                # Position x for next letter
                x -= (w + spacing)
            elif rotate == 270:
                # Fill in spacing
                if spacing:
                    self.fill_rectangle(x, y - h - spacing, w, spacing,
                                        c)
                # Position y for next letter
                y -= (h + spacing)
            else:
                print("Invalid rotation.")
                return

    def draw_text8x8(self, x: int, y: int, text: str, color=1) -> None:
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

    def draw_vline(self, x: int, y: int, h: int, invert=False) -> None:
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

    def fill_circle(self, x0: int, y0: int, r: int, invert=False) -> None:
        """Draw a filled circle.

        Args:
            x0 (int): X coordinate of center point.
            y0 (int): Y coordinate of center point.
            r (int): Radius.
            invert (bool): True = clear line, False (Default) = draw line.
        """
        f = 1 - r
        dx = 1
        dy = -r - r
        x = 0
        y = r
        self.draw_vline(x0, y0 - r, 2 * r + 1, invert)
        while x < y:
            if f >= 0:
                y -= 1
                dy += 2
                f += dy
            x += 1
            dx += 2
            f += dx
            self.draw_vline(x0 + x, y0 - y, 2 * y + 1, invert)
            self.draw_vline(x0 - x, y0 - y, 2 * y + 1, invert)
            self.draw_vline(x0 - y, y0 - x, 2 * x + 1, invert)
            self.draw_vline(x0 + y, y0 - x, 2 * x + 1, invert)

    def fill_ellipse(self, x0: int, y0: int, a: int, b: int, invert=False) -> None:
        """Draw a filled ellipse.

        Args:
            x0, y0 (int): Coordinates of center point.
            a (int): Semi axis horizontal.
            b (int): Semi axis vertical.
            invert (bool): True = clear line, False (Default) = draw line.
        Note:
            The center point is the center of the x0,y0 pixel.
            Since pixels are not divisible, the axes are integer rounded
            up to complete on a full pixel.  Therefore the major and
            minor axes are increased by 1.
        """
        a2 = a * a
        b2 = b * b
        twoa2 = a2 + a2
        twob2 = b2 + b2
        x = 0
        y = b
        px = 0
        py = twoa2 * y
        # Plot initial points
        self.draw_line(x0, y0 - y, x0, y0 + y, invert)
        # Region 1
        p = round(b2 - (a2 * b) + (0.25 * a2))
        while px < py:
            x += 1
            px += twob2
            if p < 0:
                p += b2 + px
            else:
                y -= 1
                py -= twoa2
                p += b2 + px - py
            self.draw_line(x0 + x, y0 - y, x0 + x, y0 + y, invert)
            self.draw_line(x0 - x, y0 - y, x0 - x, y0 + y, invert)
        # Region 2
        p = round(b2 * (x + 0.5) * (x + 0.5) +
                  a2 * (y - 1) * (y - 1) - a2 * b2)
        while y > 0:
            y -= 1
            py -= twoa2
            if p > 0:
                p += a2 - py
            else:
                x += 1
                px += twob2
                p += a2 - py + px
            self.draw_line(x0 + x, y0 - y, x0 + x, y0 + y, invert)
            self.draw_line(x0 - x, y0 - y, x0 - x, y0 + y, invert)

    def fill_rectangle(self, x: int, y: int, w: int, h: int, invert: int|bool=False) -> None:
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

    def fill_polygon(self, sides: int, x0: int, y0: int, r: int, invert=False, rotate=0) -> None:
        """Draw a filled n-sided regular polygon.

        Args:
            sides (int): Number of polygon sides.
            x0, y0 (int): Coordinates of center point.
            r (int): Radius.
            visble (bool): True (Default) = draw line, False = clear line.
            rotate (Optional float): Rotation in degrees relative to origin.
        Note:
            The center point is the center of the x0,y0 pixel.
            Since pixels are not divisible, the radius is integer rounded
            up to complete on a full pixel.  Therefore diameter = 2 x r + 1.
        """
        # Determine side coordinates
        coords = []
        theta = radians(rotate)
        n = sides + 1
        for s in range(n):
            t = 2.0 * pi * s / sides + theta
            coords.append([int(r * cos(t) + x0), int(r * sin(t) + y0)])
        # Starting point
        x1, y1 = coords[0]
        # Minimum Maximum X dict
        xdict = {y1: [x1, x1]}
        # Iterate through coordinates
        for row in coords[1:]:
            x2, y2 = row
            xprev, yprev = x2, y2
            # Calculate perimeter
            # Check for horizontal side
            if y1 == y2:
                if x1 > x2:
                    x1, x2 = x2, x1
                if y1 in xdict:
                    xdict[y1] = [min(x1, xdict[y1][0]), max(x2, xdict[y1][1])]
                else:
                    xdict[y1] = [x1, x2]
                x1, y1 = xprev, yprev
                continue
            # Non horizontal side
            # Changes in x, y
            dx = x2 - x1
            dy = y2 - y1
            # Determine how steep the line is
            is_steep = abs(dy) > abs(dx)
            # Rotate line
            if is_steep:
                x1, y1 = y1, x1
                x2, y2 = y2, x2
            # Swap start and end points if necessary
            if x1 > x2:
                x1, x2 = x2, x1
                y1, y2 = y2, y1
            # Recalculate differentials
            dx = x2 - x1
            dy = y2 - y1
            # Calculate error
            error = dx >> 1
            ystep = 1 if y1 < y2 else -1
            y = y1
            # Calcualte minimum and maximum x values
            for x in range(x1, x2 + 1):
                if is_steep:
                    if x in xdict:
                        xdict[x] = [min(y, xdict[x][0]), max(y, xdict[x][1])]
                    else:
                        xdict[x] = [y, y]
                else:
                    if y in xdict:
                        xdict[y] = [min(x, xdict[y][0]), max(x, xdict[y][1])]
                    else:
                        xdict[y] = [x, x]
                error -= abs(dy)
                if error < 0:
                    y += ystep
                    error += dx
            x1, y1 = xprev, yprev
        # Fill polygon
        for y, x in xdict.items():
            self.draw_hline(x[0], y, x[1] - x[0] + 2, invert)

    def flip(self, flip=True) -> None:
        """Set's the display orientation to either 0 or 180 degrees.

        Args:
            flip(bool): True=180 degrees, False=0 degrees
        Note:
            Anything currently displayed won't flip until present is called
        """
        if flip:
            self.write_cmd(_SEGMENT_MAP_FLIP)  # Set segment remap
            self.write_cmd(_COM_OUTPUT_FLIP)  # Set COM output scan dir
        else:
            self.write_cmd(_SEGMENT_MAP_REMAP)  # Set segment remap
            self.write_cmd(_COM_OUTPUT_NORMAL)  # Set COM output scan dir

    def is_off_grid(self, xmin: int, ymin: int, xmax: int, ymax: int) -> bool:
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
        if xmax > self.width:
            print(f'warn-x: {xmax} > {self.width}')
            return True
        if ymax > self.height:
            print(f'warn-y: {ymax} > {self.height}')
            return True
        return False

    def load_sprite(self, path: str, w: int, h: int, invert=False, rotate=0) -> FrameBuffer:
        """Load MONO_HMSB bitmap from disc to sprite.

        Args:
            path (string): Image file path.
            w (int): Width of image.
            h (int): Height of image.
            invert (bool): True = invert image, False (Default) = normal image.
            rotate(int): 0, 90, 180, 270
        Notes:
            w x h cannot exceed 2048
        """
        array_size = w * h
        with open(path, "rb") as f:
            buf = bytearray(f.read(array_size))
            fb = FrameBuffer(buf, w, h, MONO_HMSB)

            if rotate == 0 and invert is True:  # 0 degrees
                fb2 = FrameBuffer(bytearray(array_size), w, h, MONO_HMSB)
                for y1 in range(h):
                    for x1 in range(w):
                        fb2.pixel(x1, y1, fb.pixel(x1, y1) ^ 0x01)
                fb = fb2
            elif rotate == 90:  # 90 degrees
                byte_width = (w - 1) // 8 + 1
                adj_size = h * byte_width
                fb2 = FrameBuffer(bytearray(adj_size), h, w, MONO_HMSB)
                for y1 in range(h):
                    for x1 in range(w):
                        if invert is True:
                            fb2.pixel(y1, x1,
                                      fb.pixel(x1, (h - 1) - y1) ^ 0x01)
                        else:
                            fb2.pixel(y1, x1, fb.pixel(x1, (h - 1) - y1))
                fb = fb2
            elif rotate == 180:  # 180 degrees
                fb2 = FrameBuffer(bytearray(array_size), w, h, MONO_HMSB)
                for y1 in range(h):
                    for x1 in range(w):
                        if invert is True:
                            fb2.pixel(x1, y1, fb.pixel((w - 1) - x1,
                                                       (h - 1) - y1) ^ 0x01)
                        else:
                            fb2.pixel(x1, y1,
                                      fb.pixel((w - 1) - x1, (h - 1) - y1))
                fb = fb2
            elif rotate == 270:  # 270 degrees
                byte_width = (w - 1) // 8 + 1
                adj_size = h * byte_width
                fb2 = FrameBuffer(bytearray(adj_size), h, w, MONO_HMSB)
                for y1 in range(h):
                    for x1 in range(w):
                        if invert is True:
                            fb2.pixel(y1, x1,
                                      fb.pixel((w - 1) - x1, y1) ^ 0x01)
                        else:
                            fb2.pixel(y1, x1, fb.pixel((w - 1) - x1, y1))
                fb = fb2

            return fb

    def present(self) -> None:
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

    def contrast(self, contrast: int) -> None:
        """
        Change the current display contrast (brightness).
        """
        self.write_cmd(_CONTRAST_CONTROL)
        self.write_cmd(contrast)

    def set_vcomdesel(self, arg: int) -> None:
        """
        Set the V_com deselect level (0-7)
        """
        self.write_cmd(_VCOM_DESELECT_LEVEL)
        self.write_cmd(arg << 4)

    def set_precharge(self, p1: int, p2: int) -> None:
        """
        Set the precharge interval for the display matrix. Augments contrast setting.
        """
        self.write_cmd(_PRECHARGE_PERIOD)
        self.write_cmd((p2 << 4) | p1)

    def sleep(self) -> None:
        """Put display to sleep."""
        self.write_cmd(_DISPLAY_OFF)

    def scroll_start(self) -> None:
        """Activates scrolling after setup."""
        self.write_cmd(_SCROLL_ACTIVATE)

    def scroll_stop(self) -> None:
        """Stops any scrolling effect."""
        self.write_cmd(_SCROLL_DEACTIVATE)

    def scroll_horizontal_manual(self, direction="right", start_page=0,
                                 end_page=7, start_column=0, end_column=127) -> None:
        """Manual horizontal scrolling.

        Args:
            direction (string): scroll 'left' or 'right' (default: 'right')
            start_page (int): first horizontal band to scroll 0-7 (default: 0)
            end_page (int): last horizontal band to scroll 0-7 (default: 7)
            start_column (int): first column (default: 0)
            end_column (int): last column (default: 127)
        Note:
            A time delay of 2/Frame Frequency required for consecutive calls.
            The time delay should be placed immediately after the scroll.
            Any existing scrolling should be stopped before first call.
        """
        if direction == "right":
            cmd = _SCROLL_BY_ONE_RIGHT
        else:
            cmd = _SCROLL_BY_ONE_LEFT
        self.write_cmd(cmd)  # Left or right command
        self.write_cmd(0x00)  # Dummy byte - column scroll offset (no effect)
        self.write_cmd(start_page)  # Start page address
        self.write_cmd(0x00)  # Dummy byte - interval set by user (no effect)
        self.write_cmd(end_page)  # End page address
        self.write_cmd(0x00)  # Dummy byte - vertical scroll offset (no effect)
        self.write_cmd(start_column)  # Start column
        self.write_cmd(end_column)  # End column

    def scroll_horizontal_setup(self, direction="right", start_page=0,
                                end_page=7, interval=0, start_column=0,
                                end_column=127) -> None:
        """Configures horizontal only scrolling.

        Args:
            direction (string): scroll 'left' or 'right' (default: 'right')
            start_page (int): first horizontal band to scroll 0-7 (default: 0)
            end_page (int): last horizontal band to scroll 0-7 (default: 7)
            interval (int): time interval between each scroll step (default: 0)
                (0=5 frames, 1=64 frames, 2=128 frames, 3=256 frames, 4=2
                 frames, 5=3 frames, 6=4 frames, 7=1 frame)
            start_column (int): first column (default: 0)
            end_column (int): last column (default: 127)
        """
        self.scroll_stop()  # Any scrolling should be stopped
        if direction == "right":
            cmd = _SCROLL_HORIZONTAL_RIGHT
        else:
            cmd = _SCROLL_HORIZONTAL_LEFT
        self.write_cmd(cmd)  # Left or right command
        self.write_cmd(0x00)  # Dummy byte - column scroll offset (no effect)
        self.write_cmd(start_page)  # Start page address
        self.write_cmd(interval)  # Time interval between each scroll steps
        self.write_cmd(end_page)  # End page address
        self.write_cmd(0x00)  # Dummy byte - vertical scroll offset (no effect)
        self.write_cmd(start_column)  # Start column
        self.write_cmd(end_column)  # End column

    def scroll_setup(self, direction=["up"], start_page=0,
                     end_page=7, first_row=0, total_rows=64,
                     interval=0, start_column=0, end_column=127,
                     vertical_speed=1) -> None:
        """Configures advanced scrolling setup.

        Args:
            direction ([string]): 'up', 'down', 'left', 'right' (default: 'up')
            start_page (int): first horizontal band to scroll 0-7 (default: 0)
            end_page (int): last horizontal band to scroll 0-7 (default: 7)
            first_row (int): first horizontal row to scroll (default: 0)
            total_rows (int): number of rows to scroll (default: 64)
            interval (int): time interval between each scroll step (default: 0)
                (0=5 frames, 1=64 frames, 2=128 frames, 3=256 frames, 4=2
                 frames, 5=3 frames, 6=4 frames, 7=1 frame)
            start_column (int): first column (default: 0)
            end_column (int): last column (default: 127)
            vertical_speed (int): amount of scroll 1-32 (default: 1)
        """
        assert 0 <= vertical_speed <= 31, "Vertical speed must be 0 - 31."
        assert not ({"up", "down"} <= set(direction)
                    ), '"up" & "down" cannot both be in the direction list.'
        assert not ({"left", "right"} <= set(direction)
                    ), '"left" & "right" cannot both be in the direction list.'
        
        self.scroll_stop()  # Any scrolling should be stopped
        self.write_cmd(_SCROLL_SETUP_VERTICAL_AREA)  # Vertical scroll area
        self.write_cmd(first_row)  # First row of scroll region
        self.write_cmd(total_rows)  # Number of  rows to scroll
        horizontal = 0  # No horizontal movement
        cmd = _SCROLL_VERTICAL_LEFT  # Left or no horizontal

        if "right" in direction:
            cmd = _SCROLL_VERTICAL_RIGHT  # Right horizontal scroll
            horizontal = 1  # Horizontal movement
        elif "left" in direction:
            horizontal = 1  # Horizontal movement

        self.write_cmd(cmd)  # Vertical scroll left or right
        self.write_cmd(horizontal)  # Horizontal scroll
        self.write_cmd(start_page)  # Start page address
        self.write_cmd(interval)  # Time interval between each scroll steps
        self.write_cmd(end_page)  # End page address

        if "down" in direction:
            vertical_speed = 64 - vertical_speed  # Invert for down
        elif "up" not in direction:
            vertical_speed = 0  # Disable vertical if not up or down
        self.write_cmd(vertical_speed)  # 0 to 31 up / 63 to 32 down
        self.write_cmd(start_column)  # Start column
        self.write_cmd(end_column)  # End column

    def wake(self) -> None:
        """Wake display from sleep."""
        self.write_cmd(_DISPLAY_ON)

    def write_cmd_i2c(self, command: int, *args) -> None:
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

    def write_data_i2c(self, data: bytes) -> None:
        """Write data to display.

        Args:
            data (bytes): Data to transmit.
        """
        #  0x40 -> Co=0, D/C#=1
        self.i2c.writeto_mem(self.address, 0x40, data)