from esp32_ulp import src_to_binary
import sys

def main(asm_file: str) -> None:
    name = asm_file.rsplit(".")[0]
    out_py_name = f"{name}.py"

    with open(asm_file) as f:
        src = f.read()

    bin_img, addrs_syms = src_to_binary(src, "esp32")

    if len(bin_img) > 5888: # max section size I have available
        raise ValueError(f"rtc mem overflow: binary is {len(bin_img)}/5888 B")
    else:
        print(f"out binary size: {len(bin_img)}/5888 B")

    with open(out_py_name, "w") as f:
        f.write('# SYMBOLS:\tADDR\tWORD\tNAME\n')
        for addr_words, sym in addrs_syms:
            addr_bytes = addr_words * 4
            f.write('# \t\t\t0x%04x \t0x%04x \t%s\n' % (addr_bytes, addr_words, sym))

        f.write("ULP_BASE = const(0x50000000)\n")
        f.write(f"ULP_LEN = const({hex(len(bin_img))})\n")

        for addr_words, sym in addrs_syms:
            f.write('ULP_%s = const(0x%04x)\n' % (sym.upper(), addr_words * 4))

        f.write(f"\nulp_firmware = {bin_img}\n")

    with open(f"{name}.bin", "wb") as f:
        f.write(bin_img)

if __name__ == "__main__":
    main(sys.argv[1])