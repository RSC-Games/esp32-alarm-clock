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
    Install a clock_firm package with the given postfix (located in the root directory) 
    over the currently installed clock_firm package (if any).
    """

    # Delete old clock_firm package
    if file_exists("/clock_firm.img.sig"):
        os.unlink("/clock_firm.img.sig")
    if file_exists("/clock_firm.img"):
        os.unlink("/clock_firm.img")

    # Install new clock_firm package
    os.rename(f"/clock_firm.img.sig{postfix}", "/clock_firm.img.sig")
    os.rename(f"/clock_firm.img{postfix}", "/clock_firm.img")

def install_insecure_firmware_local(postfix: str=".new"):
    """
    Install a clock_firm package with the given postfix (located in the root directory) 
    over the currently installed clock_firm package (if any).
    """

    # Delete old clock_firm package
    if file_exists("/clock_firm.img"):
        os.unlink("/clock_firm.img")

    # Install new clock_firm package
    os.rename(f"/clock_firm.img{postfix}", "/clock_firm.img")