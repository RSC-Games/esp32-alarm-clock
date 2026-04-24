from hal import peripherals as dev
from hal import osk

# Wifi menu's got quite a bit of a job here.
# It needs to scan network access points, list them in a menu
# that's easily readable, and then request a password to connect
# to the access point. It has to do all of this and still remain
# as small as possible to fit into the 30 kB image limit.
def run() -> bool:
    dev.FBCON.set_hidden(True)

    # Get consent to add a new network entry.
    if not osk.prompt_yn("NO NETWORK", ["Set up a new", "connection?"]):
        osk.prompt_ok("Network", ["Declined.", "Reboot?"])
        return False

    while True:
        ap = None

        while ap is None:
            dev.DISPLAY.clear_buffers()
            dev.DISPLAY.draw_text8x8(0, 0, "wifi scan...")
            dev.DISPLAY.present()

            scan_results = dev.NIC.rescan()
            ap = do_select_menu("Scan Results", scan_results)

        if ap[2] != dev.NIC.wlan.SEC_OPEN:
            osk.prompt_ok(ap[0], ["Please enter", "wifi password", "to continue"])
            psk = osk.prompt_text(osk.LAYOUT_KEYBOARD, 50, hide_text=True)
        else:
            psk = ""

        dev.DISPLAY.clear_buffers()
        dev.DISPLAY.draw_text8x8(0, 0, "connecting...")
        dev.DISPLAY.present()

        if dev.NIC.assoc_new((ap[0], ap[2], psk)):
            osk.prompt_ok(ap[0], ["Connected", "successfully!"])
            dev.FBCON.set_hidden(False)
            return True
        
        # Connection failed; loop back to the beginning and rescan.
        osk.prompt_ok(ap[0], ["Connection", "failed (code):", dev.NIC.decode_status()])
    

def do_select_menu(menu_name: str, ap_list: list[tuple[bytes, bytes, int, int, int, int]]) -> tuple[str, int, int] | None:
    """
    Get a network from the provided scan list. Returns a tuple of the ssid, RSSI,
    and authentication mode of the selected network.
    """
    dev.wait_buttons_all_released()

    # Current menu position.
    index = 0
    offset = 0

    while True:          
        # Desired network (may crash)
        if dev.get_button_wait(dev.BTN_CONFIRM):
            ap = ap_list[offset]
            dev.wait_buttons_all_released()
            return ap[0].decode(errors="replace"), ap[3], ap[4]
            
        # Triggers rescan
        elif dev.get_button_wait(dev.BTN_BACK):
            dev.wait_buttons_all_released()
            return None

        elif dev.get_button_wait(dev.BTN_DIR_UP):
            index -= 1
            if index % 6 == 5 and index > 0:
                offset -= 6

        elif dev.get_button_wait(dev.BTN_DIR_DOWN):
            index += 1
            if index % 6 == 0 and index > 0:
                offset += 6

        # Wrap index.
        if index == len(ap_list):
            index = 0
            offset = 0
        elif index == -1:
            index = len(ap_list) - 1
            offset = (index // 6) * 6

        # Print the menu items.
        start_loc = 8
        dev.DISPLAY.clear_buffers()

        for i in range(0, min(len(ap_list) - offset, 6)):
            ap_name = ap_list[offset + i][0].decode(errors="replace")

            if offset + i == index:
                dev.DISPLAY.fill_rectangle(0, start_loc, 128, 8)
                dev.DISPLAY.draw_text8x8(ap_name, 0, start_loc, 0)

            else:
                dev.DISPLAY.draw_text8x8(ap_name, 0, start_loc)

            start_loc += 8

        # Menu printed, print header.
        width = (128 - (len(menu_name) * 8)) // 2
        dev.DISPLAY.draw_text8x8(menu_name, width, 0)
        dev.DISPLAY.present()