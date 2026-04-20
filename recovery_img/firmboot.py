from esp32 import NVS

# Recovery firmware has two big jobs (the first one to execute correctly
# returns and the system reboots):
# 
# - Clean up after an update if the device wasn't shut down cleanly (think
#       new firmware downloaded and written but keys/image weren't moved
#       into the boot path)
#
# - Enter internet recovery mode and download a fresh copy of the firmware
#       to be installed. Hashes are checked but signature validation is not
#       performed by the recovery code.
#
# If neither of these two processes can repair the system or if recovery.img
# itself is damaged, the device must be reimaged/repaired with a UART recovery
# payload.
def app_main(nvs: NVS):
    print("WE HAVE BOOTED AN APPLICATION WOOHOOOOO!")

    while True:
        pass