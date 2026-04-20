from pathlib import Path
import os

def create_fs_img_recovery(input_dir: str, out_f: str, img_size: int) -> bool:
    return os.system(" ".join([
        "python", f"{Path(__file__).parent}/fatfs/fatfsgen.py", # Command
        "--output_file", os.path.abspath(out_f),
        "--partition_size", f"{img_size}",
        "--sector_size", "512",
        "--long_name_support",
        "--root_entry_count", "32",
        "--fat_count", "1",
        input_dir # Where to start generating from.
    ])) == 0