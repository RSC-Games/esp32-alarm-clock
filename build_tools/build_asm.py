import pathlib
import sys
import os

DRIVER_PATH = f"{pathlib.Path(__file__).parent}/esp32_ulp_driver.py"

if __name__ == "__main__":
    in_path = sys.argv[1]

    print(f"assembling file {in_path}")
    os.system(f"micropython {DRIVER_PATH} {in_path}")