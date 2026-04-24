from hal import osk

def main():
    osk.prompt_ok("Hello!", ["testing osk print", "does ok work", "yes or no", "hehe"])
    osk.prompt_yn("Hello!", ["testing osk print", "does ok work", "yes or no", "hehe"])

    osk.prompt_text(osk.LAYOUT_KEYBOARD, 50, False)