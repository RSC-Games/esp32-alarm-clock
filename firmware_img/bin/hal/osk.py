# osk API: Gets user input on screen.
# Code original copyright 2022; relicensed under MIT with minimal changes.
# NOTE: This layout is VERY different from the recovery image OSK.
from hal import peripherals as dev
from micropython import const
import xglcd_font

_OSK_WIDTH = const(112)
_OSK_CHARSET_PX_OFFSET = const(18)
_OSK_KBD_PX_ALIGN = const(1)
_OSK_OUTLINE_WIDTH = const(7) 
_OSK_5x7_FONT_PATH = const("/firm/res/fonts/Neato5x7.c")
_OSK_5x8_FONT_PATH = const("/firm/res/fonts/FixedFont5x8.c")
_OSK_3x5_FONT_PATH = const("/firm/res/fonts/Tiny3x5.c")

LAYOUT_KEYBOARD = const(0)
LAYOUT_NUMPAD = const(1)

# Might've stolen the osk code from the SP but it's not unmodified.
def prompt_text(key_layout: int, max_chars: int, hide_text=False) -> str:
    """
    Display an on screen keyboard and allow the user to enter text/numbers.
    Parameters:
        key_layout: Must be keyboard or numpad. Keyboard: QWERTY keyboard with caps and 
            lowercase. Numpad is unsurprisingly a numpad.
        max_chars: The maximum amount of characters allowed in the string.
        hide_text: Redact input characters while typing.

    Returns:
        str: Returns a text string containing the value entered.
    """
    
    # Displayed keyboard sets (qwerty/QWERTY/symbols)
    qwerty_key_set = {
        "UPPER": [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", ""],  # Number Row ("BKSP")
            ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],  # Charset row 1
            ["A", "S", "D", "F", "G", "H", "J", "K", "L"],       # Charset row 2
            ["Z", "X", "C", "V", "B", "N", "M"],                 # Charset row 3
            ("SPACE", " ", None, None)                           # SPACE ROW!
        ],
        "LOWER": [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", ""],  # Number Row ("BKSP")
            ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],  # Charset row 1
            ["a", "s", "d", "f", "g", "h", "j", "k", "l"],       # Charset row 2
            ["z", "x", "c", "v", "b", "n", "m"],                 # Charset row 3
            ("SPACE", " ", None, None)                           # SPACE ROW!
        ],
        "SYM": [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", ""],  # Number Row (BKSP)
            ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"],  # Charset row 1
            ["+", "-", "{", "}", "[", "]", "|", "\\", ":", ";"], # Charset row 2
            ["\"", "'", "<", ">", ",", ".", "?", "/", "=", "~"], # Charset row 3
            ("_", "_", None, None)                               # SPACE ROW!
        ]
    }
    
    # Numpad has a similar layout to the keyboard above
    numpad_key_set = {
        "NUM": [
            ["7", "8", "9", ""],  # Number Row 1 (BKSP)
            ["4", "5", "6"],  # Number Row 2
            ["1", "2", "3"],  # Number Row 3
            ["-", "0", "."],  # Number Row 4
			("_", "_", None, None) # No space character.
		]
    }
    
    dev.DISPLAY.clear_buffers()

    keymaps = ["UPPER", "LOWER", "SYM"] if key_layout == LAYOUT_KEYBOARD else ["NUM"]
    keyset = qwerty_key_set if key_layout == LAYOUT_KEYBOARD else numpad_key_set

    if key_layout not in (LAYOUT_KEYBOARD, LAYOUT_NUMPAD):
        raise ValueError(f"invalid layout: {key_layout}")
    
    return _do_osk_input(keymaps, keyset, max_chars, hide_text)

# Display an OSK with the provided keyboard layout and arguments supplied by the prompt_text
# wrapper.
def _do_osk_input(keymaps: list[str], key_set: dict[str, list], max_chars: int, hide_text: bool) -> str:
    font_5x7 = xglcd_font.XglcdFont(_OSK_5x7_FONT_PATH, 5, 7)
    font_5x8 = xglcd_font.XglcdFont(_OSK_5x8_FONT_PATH, 5, 8)
    font_3x5 = xglcd_font.XglcdFont(_OSK_3x5_FONT_PATH, 3, 5)

    keymap = keymaps[0]  # Default keyboard
    caps = True  # Currently capitals
    char_string = []  # User entered data
    col = 0
    row = 0
    
    # Stores coordinates and character aliases in a series of lists.
    # Values stored:
    # Index: Value
    #  Name: (x, y) for coordinate value on the "char grid"
    #     0: Key name (shown on screen)
    #     1: Key Value (May be the same as the alias).
    #     2: (x, y, w, h) for draw location and size of draw rect.
    # Compile the active keymap charset.
    char_coords_aliases = _compile_charset(key_set[keymap], _OSK_CHARSET_PX_OFFSET)

    # TODO: Cool lerp animations for the caret and text
    
    while True:
        # A_BTN HANDLER: ENTER A CHARACTER.
        if dev.get_button_wait(dev.BTN_CONFIRM):
            cur_char = char_coords_aliases[(col, row)]
            
            # Special key (RETURN) (enter)
            if cur_char[1] == "RET":
                # Return the list of characters after making it a string.
                dev.wait_buttons_all_released()
                return "".join(char_string)
            
            # Special key (SHIFT)
            elif cur_char[1] == "SHFT":
                # Switch to upper/lowercase
                if keymap == keymaps[0]:  # UPPER
                    keymap = keymaps[1]
                    caps = False
                else:  # LOWER
                    keymap = keymaps[0]
                    caps = True
                    
                # Keymap changed; generate new one
                char_coords_aliases = _compile_charset(key_set[keymap], _OSK_CHARSET_PX_OFFSET)
                dev.wait_buttons_all_released()
                continue
                
            # Special key (SYMBOLS)
            elif cur_char[1] == "SYM":
                # Switch between lowercase or symbols
                keymap = keymaps[1] if keymap == keymaps[2] else keymaps[2]
                
                # Keymap change
                char_coords_aliases = _compile_charset(key_set[keymap], _OSK_CHARSET_PX_OFFSET)
                dev.wait_buttons_all_released()
                continue

            # Special key (BACKSPACE)
            elif cur_char[1] == "BKSP":
                if len(char_string) != 0:
                    char_string.pop()
            
            # Normal key pressed
            else:
                if len(char_string) < max_chars:
                    char_string.append(cur_char[1])

                # Zero length = auto caps
                if len(char_string) == 0:
                    caps = True
                    keymap = keymaps[0]
                    char_coords_aliases = _compile_charset(key_set[keymap], _OSK_CHARSET_PX_OFFSET)

                # Auto lowercase
                elif caps:
                    caps = False
                    keymap = keymaps[1]
                    char_coords_aliases = _compile_charset(key_set[keymap], _OSK_CHARSET_PX_OFFSET)

                dev.wait_buttons_all_released()
        
        # B_BTN HANDLER: ERASE A CHARACTER.
        elif dev.get_button_wait(dev.BTN_BACK):
            # Text entry exited
            if len(char_string) == 0:
                dev.wait_buttons_all_released()
                return ""
            
            char_string.pop()
        
        # UP_BTN HANDLER: MOVE THE CURSOR UP.
        elif dev.get_button_wait(dev.BTN_DIR_UP):
            prev_len = len(key_set[keymap][row]) - 1
            row -= 1
            
            if row >= len(key_set[keymap]):
               row = 0
            elif row < 0:
               row = len(key_set[keymap]) - 1
            
            # Adjust cursor to the new row.
            col = _remap(col, 0, prev_len, 0, len(key_set[keymap][row]) - 1)
            
        # DN_BTN HANDLER: MOVE THE CURSOR DOWN.
        elif dev.get_button_wait(dev.BTN_DIR_DOWN):
            prev_len = len(key_set[keymap][row]) - 1
            row += 1
            
            if row >= len(key_set[keymap]):
               row = 0
            elif row < 0:
               row = len(key_set[keymap]) - 1
            
            # Adjust cursor to the new row
            col = _remap(col, 0, prev_len, 0, len(key_set[keymap][row]) - 1)
            
        # RT_BTN HANDLER: MOVE THE CURSOR RIGHT.
        elif dev.get_button_wait(dev.BTN_DIR_RIGHT):
            col += 1
            
            if col >= len(key_set[keymap][row]):
               col = 0
            elif col < 0:
               col = len(key_set[keymap][row]) - 1
            
        # LT_BTN HANDLER: MOVE THE CURSOR LEFT.
        elif dev.get_button_wait(dev.BTN_DIR_LEFT):
            col -= 1
            
            if col >= len(key_set[keymap][row]):
               col = 0
            elif col < 0:
               col = len(key_set[keymap][row]) - 1
            
        # OSK frame
        # TODO: reshape the border for more efficient space usage.
        dev.DISPLAY.clear_buffers()
        dev.DISPLAY.draw_rectangle(0, 0, 128, 63)
        dev.DISPLAY.draw_hline(0, 16, 128)
        
        # Draw keyboard on screen
        # y = 0

        # for y in range(len(key_set[keymap][row])):
        #     # Column geometry, unlike row geometry, is not guaranteed to be the same 
        #     # as in the keymap before compilation. 
        #     x = 0

        #     while (x, y) in char_coords_aliases:
        #         # TODO: Draw osk with 5x7 font (rather than the 8x8)
        #         char = char_coords_aliases[(x, y)]
        #         dev.DISPLAY.draw_text(char[2][0] + _OSK_KBD_PX_ALIGN, char[2][1], char[0], font_5x7)
        #         x += 1
            
        #     y += 1

        # Draw keyboard on screen
        # BUG: Old drawing code works but new code doesn't??
        y = 0
        try:
            while True:
                # Test access to this row.
                _ = char_coords_aliases[(0, y)]
                
                # Now iterate over the x coordinate.
                try:
                    x = 0
                    while True:
                        char = char_coords_aliases[(x, y)]
                        dev.DISPLAY.draw_text(char[2][0] + _OSK_KBD_PX_ALIGN, char[2][1], char[0], font_5x7)
                        x += 1
                except KeyError:
                    pass
                
                y += 1
        except KeyError:
            pass
        
        # Highlight selected character
        cur_char = char_coords_aliases[(col, row)]
        char_rect = cur_char[2]
        dev.DISPLAY.fill_rectangle(char_rect[0], char_rect[1], char_rect[2], char_rect[3])
        dev.DISPLAY.draw_text(char_rect[0] + _OSK_KBD_PX_ALIGN, char_rect[1], cur_char[0], font_5x7, 0)
        
        char_string_draw = char_string.copy()
        char_string_draw.append("_")

        # Drawing user entered text
        x_ind = 4
        start_len = 0 if len(char_string_draw) < 20 else len(char_string_draw) - 20
        end_index = len(char_string_draw) - start_len
        i = 0

        for char in char_string_draw[start_len:]:
            if not hide_text:
                dev.DISPLAY.draw_text(x_ind, 2, char, font_5x8)

            elif i == end_index - 1:
                dev.DISPLAY.draw_text(x_ind, 2, char, font_5x8)

            else:
                dev.DISPLAY.draw_text(x_ind, 2, "*", font_5x8)
            
            x_ind += 6
            i += 1
            
        # User string length
        length_str = f"{len(char_string)}/{max_chars}"
        dev.DISPLAY.draw_text(127 - (len(length_str) * 4), 10, length_str, font_3x5)
        dev.DISPLAY.present()

# Convert the character set into a usable form by the osk
def _compile_charset(charset: list[list[str]], starting_offset: int) \
                     -> dict[tuple[int, int], tuple[str, str, tuple[int, int, int, int]]]:
    """
    Convert a jagged 2D input character set (with the given output x offset) into an output
    dictionary with:
      key: (x, y)
      value: (key name, key value, (x, y, w, h))
    """
    gen_char_dict = {}
    y = 0
    oy = starting_offset

    for row in charset:
        print_str = ""

        space_row_flag = False
        space_row = ["", ""]
          
        # Space row
        if type(row) != list:
            space_char = row[0]
            print_str = space_char
            space_row_flag = True
            space_row = row
        else:
            # Keys row
            for char in row:
                print_str += char
            
        # X axis left align (to center keyboard)
        starting_location = (_OSK_WIDTH - (len(print_str) * 8)) // 2
        
        if space_row_flag:
            x = 0
            ox = 2
            
            # Extra implicit bottom row entries
            backspace_key = ("<-", "BKSP")
            enter_key = ("ENTER", "RET")
            shift_key = ("AB", "SHFT")
            symbols   = ("&", "SYM")
            
            # Shift key entry.
            gen_char_dict[(x, y)] = [shift_key[0], shift_key[1], (ox, oy, (len(shift_key[0]) * _OSK_OUTLINE_WIDTH), 8)]
            
            # Symbols key entry.
            x += 1
            ox += len(shift_key[0] * 8) + 4
            gen_char_dict[(x, y)] = [symbols[0], symbols[1], (ox, oy, (len(symbols[0]) * _OSK_OUTLINE_WIDTH), 8)]
            
            # Space bar entry.
            x += 1
            ox = starting_location
            gen_char_dict[(x, y)] = [space_row[0], space_row[1], (ox, oy, (len(space_row[0]) * _OSK_OUTLINE_WIDTH), 8)]
            
            # Enter key entry.
            x += 1
            ox = 94
            gen_char_dict[(x, y)] = [enter_key[0], enter_key[1], (ox, oy, (len(enter_key[0]) * _OSK_OUTLINE_WIDTH), 8)]

            # Backspace key entry.
            x = len(charset[0]) - 1
            y = 0
            ox = 110
            oy = starting_offset
            gen_char_dict[(x, y)] = [backspace_key[0], backspace_key[1], (ox, oy, (len(backspace_key[0]) * _OSK_OUTLINE_WIDTH), 8)]
        else:
            x = 0
            ox = starting_location
            for char in row:
                gen_char_dict[(x, y)] = [char, char, (ox, oy, (len(char) * _OSK_OUTLINE_WIDTH), 8)]
                
                x += 1
                ox += 8
        
        y += 1
        oy += 9
        
    # Compilation done      
    return gen_char_dict

# Prompt the user for a yes/no answer.
# Prompt provided must be in list format.
def prompt_yn(label: str, prompt: list[str]) -> bool:
    # Check that the prompt is not longer than 4 lines.
    if len(prompt) > 4:
        raise ValueError("Prompt message box longer than 4 lines.")
    
    font_5x7 = xglcd_font.XglcdFont(_OSK_5x8_FONT_PATH, 5, 8)
    font_h = font_5x7.height + 1
    font_w = font_5x7.width + 1
    
    item_selected = False  # False means no, True means yes.
    
    # Loop until an answer is provided.
    while True:
        # Button Handlers
        
        # A_BTN: Confirms the response.
        if dev.get_button_wait(dev.BTN_CONFIRM):
            dev.wait_buttons_all_released()
            return item_selected

        # B_BTN: Return false no matter what.
        elif dev.get_button_wait(dev.BTN_BACK):
            dev.wait_buttons_all_released()
            return False
        
        # UP_BTN: Inverts the state
        elif dev.get_button_wait(dev.BTN_DIR_UP) or \
            dev.get_button_wait(dev.BTN_DIR_DOWN):
            item_selected = not item_selected
            
        dev.DISPLAY.clear_buffers()
        
        # Header
        x_offset = (128 - (len(label) * font_w)) // 2
        dev.DISPLAY.draw_text(x_offset, 0, label, font_5x7)
        
        # Message
        y = font_h
        for line in prompt:
            dev.DISPLAY.draw_text(0, y, line, font_5x7)
            y += font_h

        # Selected line is drawn with inverted colors.
        draw_color = 0 if item_selected else 1
        
        if item_selected:
            dev.DISPLAY.fill_rectangle(0, 48, 127, 8)
        elif not item_selected:
            dev.DISPLAY.fill_rectangle(0, 56, 127, 8)

        dev.DISPLAY.draw_text(56, 48, "Yes", font_5x7, draw_color)
        dev.DISPLAY.draw_text(59, 56, "No", font_5x7, 1 - draw_color)
        
        dev.DISPLAY.present()

# Prompt the user.
# Prompt provided must be in list format.
def prompt_ok(label: str, prompt: list[str]) -> bool:
    # Check that the prompt is not longer than 4 lines.
    if len(prompt) > 4:
        raise ValueError("Prompt message box longer than 4 lines.")
    
    font_5x7 = xglcd_font.XglcdFont(_OSK_5x8_FONT_PATH, 5, 8)
    font_h = font_5x7.height + 1
    font_w = font_5x7.width + 1
    
    # Loop until an answer is provided.
    while True:
        # Button Handlers
        
        # A_BTN: Confirms the response.
        if dev.get_button_wait(dev.BTN_CONFIRM):
            dev.wait_buttons_all_released()
            return True
            
        dev.DISPLAY.clear_buffers()
        
        # Header
        x_offset = (128 - (len(label) * font_w)) // 2
        dev.DISPLAY.draw_text(x_offset, 0, label, font_5x7)
        
        # Message
        y = font_h
        for line in prompt:
            dev.DISPLAY.draw_text(0, y, line, font_5x7)
            y += font_h
        
        dev.DISPLAY.fill_rectangle(0, 56, 127, 8)
        dev.DISPLAY.draw_text(52, 56, "Okay", font_5x7, 0)
        dev.DISPLAY.present()

def _remap(x: int, in_min: int, in_max: int, out_min: int, out_max: int) -> int:
    """
    Take a value x within the range [in_min, in_max] and remap it to
    the output range [out_min, out_max] (rounded).
    """
    return max(out_min, min(out_max, (x - in_min) * round((out_max - out_min) / (in_max - in_min)) + out_min))