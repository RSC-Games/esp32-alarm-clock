# osk API: Gets user input on screen.
# Code original copyright 2022; relicensed under MIT with minimal changes.
from hal import peripherals as dev
from micropython import const

_OSK_WIDTH = const(128)

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
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],  # Number Row
            ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],  # Charset row 1
            ["A", "S", "D", "F", "G", "H", "J", "K", "L"],       # Charset row 2
            ["Z", "X", "C", "V", "B", "N", "M"],                 # Charset row 3
            ("SPACE", " ", None, None)                           # SPACE ROW!
        ],
        "LOWER": [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],  # Number Row
            ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"],  # Charset row 1
            ["a", "s", "d", "f", "g", "h", "j", "k", "l"],       # Charset row 2
            ["z", "x", "c", "v", "b", "n", "m"],                 # Charset row 3
            ("SPACE", " ", None, None)                           # SPACE ROW!
        ],
        "SYM": [
            ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],  # Number Row
            ["!", "@", "#", "$", "%", "^", "&", "*", "(", ")"],  # Charset row 1
            ["+", "-", "{", "}", "[", "]", "|", "\\", ":", ";"], # Charset row 2
            ["\"", "'", "<", ">", ",", ".", "?", "/", "=", "~"], # Charset row 3
            ("_", "_", None, None)                               # SPACE ROW!
        ]
    }
    
    # Numpad has a similar layout to the keyboard above
    numpad_key_set = {
        "NUM": [
            ["7", "8", "9"],  # Number Row 1
            ["4", "5", "6"],  # Number Row 2
            ["1", "2", "3"],  # Number Row 3
            ["-", "0", "."],  # Number Row 4
			("_", "_", None, None) # No space character.
		]
    }
    
    # Erase the display.
    dev.DISPLAY.clear_buffers()
    
    # Now begin querying the user for input, based on the key set.
    if key_layout == 0:
        return _do_osk_input(["UPPER", "LOWER", "SYM"], qwerty_key_set, max_chars, hide_text)       
        
    # Use the numpad in this keyboard layout.
    elif key_layout == 1:
        return _do_osk_input(["NUM"], numpad_key_set, max_chars, hide_text)
        
    else:
        raise ValueError("invalid layout")


# Display an OSK with the provided keyboard layout and arguments supplied by the prompt_text
# wrapper.
def _do_osk_input(subcharsets: list[str], key_set: dict[str, list], max_chars: int, hide_text: bool) -> str:
    subcharset = subcharsets[0]  # Default keyboard
    char_string = []  # Typed data
    starting_offset = 23  # 
    pos_x = 0
    pos_y = 0
    
    # Stores coordinates and character aliases in a series of lists.
    # Values stored:
    # Index: Value
    #  Name: (x, y) for coordinate value on the "char grid."
    #     0: Alias
    #     1: Char (May be the same as the alias).
    #     2: (x, y, w, h) for storing on display location and size of rect.
    # Compile the subcharset charset (subcharset).
    char_coords_aliases = _compile_charset(key_set[subcharset], starting_offset)
    
    while True:
        # Wait for user input.
        # A_BTN HANDLER: ENTER A CHARACTER.
        if dev.get_button_wait(dev.BTN_CONFIRM):                
            # Recompile the alias list if the selected keyboard changed.
            cur_char = char_coords_aliases[(pos_x, pos_y)]
            
            # Load different menus if an option.
            if cur_char[1] == "RET":
                # Return the list of characters after making it a string.
                dev.wait_buttons_all_released()
                return "".join(char_string)
            
            elif cur_char[1] == "SHFT":
                # Check the case. If in the symbols case, ignore.
                if subcharset == subcharsets[0]:
                    subcharset = subcharsets[1]
                elif subcharset == subcharsets[1]:
                    subcharset = subcharsets[0]
                    
                # Now we want to recompile the charset to correspond with the new characters.
                char_coords_aliases = _compile_charset(key_set[subcharset], starting_offset)
                dev.wait_buttons_all_released()
                continue
                
            elif cur_char[1] == "SYM":
                # Switch the charset to symbols if it is not, otherwise set to lowercase.
                if subcharset == subcharsets[2]:
                    subcharset = subcharsets[1]
                else:
                    subcharset = subcharsets[2]
                
                # Now we want to recompile the charset to correspond with the new characters.
                char_coords_aliases = _compile_charset(key_set[subcharset], starting_offset)
                dev.wait_buttons_all_released()
                continue

            else:
                # Ensure max length has not been exceeded.
                if len(char_string) == max_chars:
                    pass
                else:
                    # Append the character to the string.
                    char_string.append(cur_char[1])

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
            prev_len = len(key_set[subcharset][pos_y]) - 1
            pos_y -= 1
            
            if pos_y >= len(key_set[subcharset]):
               pos_y = 0
            elif pos_y < 0:
               pos_y = len(key_set[subcharset]) - 1
            
            # Adjust cursor to the new row.
            pos_x = _remap(pos_x, 0, prev_len, 0, len(key_set[subcharset][pos_y]) - 1)
            
        # DN_BTN HANDLER: MOVE THE CURSOR DOWN.
        elif dev.get_button_wait(dev.BTN_DIR_DOWN):
            prev_len = len(key_set[subcharset][pos_y]) - 1
            pos_y += 1
            
            if pos_y >= len(key_set[subcharset]):
               pos_y = 0
            elif pos_y < 0:
               pos_y = len(key_set[subcharset]) - 1
            
            # Adjust cursor to the new row
            pos_x = _remap(pos_x, 0, prev_len, 0, len(key_set[subcharset][pos_y]) - 1)
            
        # RT_BTN HANDLER: MOVE THE CURSOR RIGHT.
        elif dev.get_button_wait(dev.BTN_DIR_RIGHT):
            pos_x += 1
            
            if pos_x >= len(key_set[subcharset][pos_y]):
               pos_x = 0
            elif pos_x < 0:
               pos_x = len(key_set[subcharset][pos_y]) - 1
            
        # LT_BTN HANDLER: MOVE THE CURSOR LEFT.
        elif dev.get_button_wait(dev.BTN_DIR_LEFT):
            pos_x -= 1
            
            if pos_x >= len(key_set[subcharset][pos_y]):
               pos_x = 0
            elif pos_x < 0:
               pos_x = len(key_set[subcharset][pos_y]) - 1
            
        dev.DISPLAY.clear_buffers()
        
        # Draw the border.
        # TODO: reshape the border for more efficient space usage.
        dev.DISPLAY.draw_rectangle(0, 0, 127, 63)
        dev.DISPLAY.draw_hline(0, 21, 127)
        
        # Draw keyboard on screen
        y = 0
        try:
            while True:
                # Test access to this row.
                _ = char_coords_aliases[(0, y)]
                
                # Now iterate over the x coordinate.
                try:
                    x = 0
                    while True:
                        # TODO: Draw osk with 5x7 font (rather than the 8x8)
                        char = char_coords_aliases[(x, y)]
                        dev.DISPLAY.draw_text8x8(char[2][0], char[2][1], char[0])
                        x += 1
                except KeyError:
                    pass
                
                y += 1
        except KeyError:
            pass
        
        # Highlight the selected item.
        cur_char = char_coords_aliases[(pos_x, pos_y)]
        char_rect = cur_char[2]
        dev.DISPLAY.fill_rectangle(char_rect[0], char_rect[1], char_rect[2], char_rect[3], 1)
        dev.DISPLAY.draw_text8x8(char_rect[0], char_rect[1], cur_char[0], 0)
        
        # Print the written text at the top of the display.
        x_ind = 4
        start_len = 0 if len(char_string) < 15 else len(char_string) - 15
        i = 0
        end_index = len(char_string) - start_len

        for char in char_string[start_len:]:
            if not hide_text:
                dev.DISPLAY.draw_text8x8(x_ind, 2, char)

            elif i == end_index - 1:
                dev.DISPLAY.draw_text8x8(x_ind, 2, char)

            else:
                dev.DISPLAY.draw_text8x8(x_ind, 2, "*")                
            
            x_ind += 8
            i += 1
            
        # User string length
        # TODO: Show this with the 3x5 smaller font
        length_str = f"{len(char_string)}/{max_chars}"
        dev.DISPLAY.draw_text8x8(126 - (len(length_str) * 8), 13, length_str)
        dev.DISPLAY.present()

# Convert the character set into a usable form by the osk
def _compile_charset(charset: list[list[str]], starting_offset: int) -> dict[tuple, tuple]:
    charset_dict = {}
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
            # TODO: Add a top row backspace entry?
            enter_key = ("->", "RET")
            shift_key = ("AB", "SHFT")
            symbols   = ("&", "SYM")
            
            # Shift key entry.
            charset_dict[(x, y)] = [shift_key[0], shift_key[1], (ox, oy, (len(shift_key[0]) * 8), 8)]
            
            # Symbols key entry.
            x += 1
            ox += len(shift_key[0] * 8) + 8
            charset_dict[(x, y)] = [symbols[0], symbols[1], (ox, oy, (len(symbols[0]) * 8), 8)]
            
            # Space bar entry.
            x += 1
            ox = starting_location
            charset_dict[(x, y)] = [space_row[0], space_row[1], (ox, oy, (len(space_row[0]) * 8), 8)]
            
            # Enter key entry.
            x += 1
            ox = 110
            charset_dict[(x, y)] = [enter_key[0], enter_key[1], (ox, oy, (len(enter_key[0]) * 8), 8)]
        else:
            x = 0
            ox = starting_location
            for char in row:
                # char entry in this row
                charset_dict[(x, y)] = [char, char, (ox, oy, (len(char) * 8), 8)]
                
                x += 1
                ox += 8
        
        y += 1
        oy += 8
        
    # Compilation done      
    return charset_dict


# Prompt the user for a yes/no answer.
# Prompt provided must be in list format.
def prompt_yn(label: str, prompt: list[str]) -> bool:
    # Check that the prompt is not longer than 4 lines.
    if len(prompt) > 4:
        raise ValueError("Prompt message box longer than 4 lines.")
    
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

        # TODO: no status bar
        #run_status_bar()
        
        # Header
        x_offset = (128 - (len(label) * 8)) // 2
        dev.DISPLAY.draw_text8x8(x_offset, 8, label)
        
        # Message
        y = 16
        for line in prompt:
            dev.DISPLAY.draw_text8x8(0, y, line)
            y += 8

        # Selected line is drawn with inverted colors.
        draw_color = 0 if item_selected else 1
        
        if item_selected:
            dev.DISPLAY.fill_rectangle(0, 48, 127, 8, 1)
        elif not item_selected:
            dev.DISPLAY.fill_rectangle(0, 56, 127, 8, 1)

        dev.DISPLAY.draw_text8x8(52, 48, "Yes", draw_color)
        dev.DISPLAY.draw_text8x8(56, 56, "No", 1 - draw_color)
        
        dev.DISPLAY.present()


# Prompt the user.
# Prompt provided must be in list format.
def prompt_ok(label: str, prompt: list[str]) -> bool:
    # Check that the prompt is not longer than 4 lines.
    if len(prompt) > 4:
        raise ValueError("Prompt message box longer than 4 lines.")
    
    # Loop until an answer is provided.
    while True:
        # Button Handlers
        
        # A_BTN: Confirms the response.
        if dev.get_button_wait(dev.BTN_CONFIRM):
            dev.wait_buttons_all_released()
            return True
            
        dev.DISPLAY.clear_buffers()
        #run_status_bar()
        
        # Header
        x_offset = (128 - (len(label) * 8)) // 2
        dev.DISPLAY.draw_text8x8(x_offset, 8, label, 1)
        
        # Message
        y = 16
        for line in prompt:
            dev.DISPLAY.draw_text8x8(0, y, line)
            y += 8
        
        dev.DISPLAY.fill_rectangle(0, 56, 127, 8, 1)
        dev.DISPLAY.draw_text8x8(48, 56, "Okay", 0)
        dev.DISPLAY.present()

def _remap(x: int, in_min: int, in_max: int, out_min: int, out_max: int) -> int:
    """
    Take a value x within the range [in_min, in_max] and remap it to
    the output range [out_min, out_max] (rounded).
    """
    return max(out_min, min(out_max, (x - in_min) * round((out_max - out_min) / (in_max - in_min)) + out_min))