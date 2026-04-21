import os

def file_exists(path: str) -> bool:
    """
    Determine whether the provided file exists on the storage device.
    """

    try:
        os.stat(path)
        return True
    except OSError:
        return False
    

def install_new_firmware_local(postfix: str=".new"):
    """
    Install a firmware package with the given postfix (located in the root directory) 
    over the currently installed firmware package (if any).
    """

    # Delete old firmware package
    if file_exists("/firmware.img.sig"):
        os.unlink("/firmware.img.sig")
    if file_exists("/firmware.img"):
        os.unlink("/firmware.img")

    # Install new firmware package
    os.rename(f"/firmware.img.sig{postfix}", "/firmware.img.sig")
    os.rename(f"/firmware.img{postfix}", "/firmware.img")