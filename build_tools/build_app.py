import build_cmdlets
import pathlib
import sys
import os

# Windows-specific; port to linux later
MPY_CROSS_PATH = "mpy-cross"#f"{pathlib.Path(__file__).parent}/mpy-cross.exe"
MPY_CROSS_FLAGS = "-O2"
MAX_FIRM_IMG_SIZE = int(52*1024)  # Not space constrained

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

    if not build_cmdlets.trim_fonts(build_dir):
        sys.exit(-1)

    if not build_cmdlets.make_bootable_image(out_img, build_dir, MAX_FIRM_IMG_SIZE):
        print(" -- failed to create firm fs img")
        sys.exit(-1)

    # DONE!
    print(" ** build app image complete")

main(sys.argv[1], sys.argv[2])