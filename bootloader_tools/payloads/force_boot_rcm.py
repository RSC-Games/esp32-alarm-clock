import bootrom

def firm_entry(_, _2) -> None:
    print("requested recovery mode reboot")
    bootrom.reboot_to_recovery()