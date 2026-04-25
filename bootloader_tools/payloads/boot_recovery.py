import bootrom

def firm_entry(_, _2):
    bootrom.reboot_to_recovery()