import mkfsimg
import shutil
import os

_BLOCK_SIZE = 512
_BLOCKS_RESERVED = 2

def create_build_dir(in_tree: str, build_tree: str):
    if os.path.exists(build_tree):
        print(" -- build tree exists; removing")
        shutil.rmtree(build_tree)

    # Separate build directory to operate in.
    print(" -- generating build directory")
    shutil.copytree(in_tree, build_tree)

def compile_code(mpy_cross: str, args: str, build_tree: str) -> bool:
    env_path = os.getcwd()
    os.chdir(build_tree)

    # Recursively compile all .mpy files inside
    for folder, _, files in os.walk("."):
        #print(f"in folder {folder}")

        for file in files:
            if os.path.splitext(file)[1] != ".py":
                continue

            print(f" .. mpy {file}")
            ret = os.system(f"{mpy_cross} {args} {folder}/{file}")

            if ret != 0:
                print(f" -- error while compiling {file}")
                return False
            
            # Avoid leaving stale source files in the final image
            os.unlink(f"{folder}/{file}")

    os.chdir(env_path) 
    return True

def trim_fonts(build_tree: str) -> bool:
    env_path = os.getcwd()
    os.chdir(build_tree)

    # Recursively compile all .mpy files inside
    for folder, _, files in os.walk("."):
        #print(f"in folder {folder}")

        for file in files:
            if os.path.splitext(file)[1] != ".c":
                continue

            print(f" .. TRIM {file}")
            fpath = os.path.join(folder, file)
            out_lines = []

            # Strip comments, newlines, and all whitespace
            with open(fpath, "r", errors="replace") as font:
                for line in font.readlines():
                    line = line.strip()

                    comment_index = line.find("//")
                    if comment_index != -1:
                        line = line[:comment_index].strip()

                    if line == "":
                        continue

                    out_lines.append(line + "\n")

            with open(fpath, "w") as font:
                font.writelines(out_lines)

    os.chdir(env_path) 
    return True

# TODO: CLI flag to show image sizes
def make_bootable_image(out_img: str, build_tree: str, max_size: int) -> bool:
    print(" -- building firm filesystem")
    res = mkfsimg.create_fs_img(build_tree, out_img, max_size)

    do_fs_space_analysis(build_tree, max_size, True)#not res)

    return res


def do_fs_space_analysis(build_tree: str, max_size: int, show_file_sizes: bool) -> None:
    img_sz_total = _BLOCKS_RESERVED * _BLOCK_SIZE  # bytes

    if show_file_sizes:
        print(" -- image space analysis (by file):")

    for folder, _, files in os.walk(build_tree):
        img_sz_total += _BLOCK_SIZE

        for file in files:
            f_size = os.path.getsize(f"{folder}/{file}")
            blocks, rem = divmod(f_size, _BLOCK_SIZE)

            f_blocks = blocks + min(rem, 1)

            if show_file_sizes:
                print(f"     - {file}: {f_blocks} blocks; {f_size} B, unused {_BLOCK_SIZE - rem} B")

            img_sz_total += (f_blocks * _BLOCK_SIZE)

    if img_sz_total > max_size:
        print(f" -- fs size overflow; {img_sz_total} > {max_size}")
    else:
        print(f" -- image size: {img_sz_total}/{max_size} B ({(max_size-img_sz_total)/max_size * 100:.2f} % free)")