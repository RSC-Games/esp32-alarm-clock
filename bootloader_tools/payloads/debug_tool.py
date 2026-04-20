import micropython
import sys
import os
import gc

print("code exec pre entry")
gc.collect()

def firm_entry(pubkey, nvs):
    print("have code exec post firm_entry")

    micropython.mem_info(1)
    gc.collect()
    gc.collect()
    micropython.mem_info(1)

    print(f"dir {dir()}")

    print(f"globals {globals()}")
    print(f"locals {locals()}")
    print(f"path {sys.path}")
    print(f"modules {sys.modules}")
    print()

    for name, module in sys.modules.items():
        print(f"{name} dir {dir(module)}")

    print(f"current root {os.listdir()}")

    print("done testing; entering fake repl")

    print(f"pubkey {pubkey}")
    print(f"nvs {nvs}")

    while True:
        print(sys.ps1, end="")
        in_text = sys.stdin.readline()

        try:
            out = eval(in_text, globals().update({'pubkey':pubkey, 'nvs':nvs}), locals())

            if out is not None:
                print(out)
        except:
            try:
                exec(in_text, globals().update({'pubkey':pubkey, 'nvs':nvs}), locals())
            except BaseException as ie:
                sys.print_exception(ie)