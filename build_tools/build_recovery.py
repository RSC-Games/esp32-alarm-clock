import binascii
import pathlib
import hashlib
import mkfsimg
import shutil
import sys
import os

# Windows-specific; port to linux later
MPY_CROSS_PATH = f"{pathlib.Path(__file__).parent}/mpy-cross.exe"
RECOVERY_IMAGER_PATH = f"{pathlib.Path(__file__).parent}/payloads/factory_imager_base.py"
MAX_RECOVERY_IMG_SIZE = 13*1024

def _create_build_dir(in_tree: str, build_tree: str):
    if os.path.exists(build_tree):
        print(" -- build tree exists; removing")
        shutil.rmtree(build_tree)

    # Separate build directory to operate in.
    print(" -- generating build directory")
    shutil.copytree(in_tree, build_tree)

def _compile_code(build_tree: str) -> bool:
    env_path = os.getcwd()
    os.chdir(build_tree)

    # Recursively compile all .mpy files inside
    for folder, _, files in os.walk("."):
        print(f"in folder {folder}")

        for file in files:
            print(f"found file {file}")
            ret = os.system(f"{MPY_CROSS_PATH} {folder}/{file}")

            if ret != 0:
                print(f" -- error while compiling {file}")
                return False
            
            # Avoid leaving stale source files in the final image
            os.unlink(f"{folder}/{file}")

    os.chdir(env_path) 
    return True

def _make_bootable_image(out_img: str, build_tree: str) -> bool:
    print(" -- building recovery rom filesystem")
    return mkfsimg.create_fs_img_recovery(build_tree, out_img, MAX_RECOVERY_IMG_SIZE)


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

    _create_build_dir(in_tree, build_dir)

    if not _compile_code(build_dir):
        sys.exit(-1)

    if not _make_bootable_image(out_img, build_dir):
        print(" -- failed to create fs img")
        sys.exit(-1)

    if not _generate_factory_imager(out_img):
        print(" -- failed to generate factory imager")
        sys.exit(-1)

    # DONE!
    print(" ** build recovery image complete")

main(sys.argv[1], sys.argv[2])