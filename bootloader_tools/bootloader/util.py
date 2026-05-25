import platform
import os

def get_port_path() -> str:
    if not platform.system() == "Linux":
        print(f"warning: unsupported platform: {platform.system()}")
        return ""

    res = [entry for entry in os.listdir("/dev") if entry.startswith("ttyUSB")]
    return f"/dev/{res[0]}"
