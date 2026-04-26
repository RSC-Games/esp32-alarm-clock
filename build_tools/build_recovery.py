import build_cmdlets
import binascii
import pathlib
import hashlib
import sys
import os

# Windows-specific; port to linux later
MPY_CROSS_PATH = "mpy-cross"#f"{pathlib.Path(__file__).parent}/mpy-cross.exe"
MPY_CROSS_FLAGS = "-O2"
RECOVERY_IMAGER_PATH = f"{pathlib.Path(__file__).parent}/payloads/factory_imager_base.py"
MAX_RECOVERY_IMG_SIZE = int(28*1024)  # 2 kB FREE IN IMAGE (4 sectors)

def _generate_factory_imager(out_img_path: str) -> bool:
    print(" -- generating recovery uart payload")

    out_img = open(out_img_path, "rb")
    img_bytes = out_img.read()
    out_img.close()

    img_sha = hashlib.sha256(img_bytes).digest()

    # Replace RECOVERY_IMG = bytes() (actual image data)
    imager = open(RECOVERY_IMAGER_PATH, "r")
    gen_imager_out = open("gen_imager.py", "w")
    
    for line in imager.readlines():
        line_strip = line.strip()

        # Write recovery image to the payload source
        if line_strip == "RECOVERY_IMG = bytes()":
            print(f" -- writing recovery img len {len(img_bytes)}")
            gen_imager_out.write(f"RECOVERY_IMG = {img_bytes}\n")
        elif line_strip == "RECOVERY_IMG_SHA256 = bytes()":
            print(f" -- writing recovery img sha {binascii.hexlify(img_sha)}")
            gen_imager_out.write(f"RECOVERY_IMG_SHA256 = {img_sha}\n")
        else:
            gen_imager_out.write(line)

    imager.close()
    gen_imager_out.close()

    # Compile payload
    print(" -- compiling payload")
    ret = os.system(f"{MPY_CROSS_PATH} gen_imager.py")

    if ret != 0:
        return False
    
    os.unlink("gen_imager.py")

    print(" -- recovery uart payload built")
    return True

# Compile stages (recovery builder)
# - Create build directory.
# - Compile all code in the directory
# - Build the fatfs image
# - Eliminate the build directory (Not hugely important)
# - build_factory_imager
# - Done!
#
def main(out_img: str, in_tree: str):
    os.chdir(pathlib.Path(in_tree).parent)
    build_dir = f"{in_tree}_build"

    build_cmdlets.create_build_dir(in_tree, build_dir)

    if not build_cmdlets.compile_code(MPY_CROSS_PATH, MPY_CROSS_FLAGS, build_dir):
        sys.exit(-1)

    if not build_cmdlets.make_bootable_image(out_img, build_dir, MAX_RECOVERY_IMG_SIZE):
        print(" -- failed to create recovery fs")
        sys.exit(-1)

    if not _generate_factory_imager(out_img):
        print(" -- failed to generate factory imager")
        sys.exit(-1)

    # DONE!
    print(" ** build recovery image complete")

main(sys.argv[1], sys.argv[2])