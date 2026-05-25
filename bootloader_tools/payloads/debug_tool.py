from machine import DAC, SDCard, Pin
from esp32 import Partition
import micropython
import time
import vfs
import sys
import os
import gc

print("code exec pre entry")
gc.collect()

# initrd size (not supported on current bootrom):
#f_bsize, _, f_blocks, f_bfree, _, _, _, _, _, _ = os.statvfs("/initrd")

#print(f"initrd free/size: {f_bsize * f_bfree}/{f_bsize * f_blocks} B")

def dac_toggle(dac: DAC, level: int, interval: int, cnt: int):
    for i in range(cnt):
        dac.write(level)
        time.sleep_us(interval)
        dac.write(0)
        time.sleep_us(interval)

dac = DAC(25)

def test_alarm_noise(level: int, interval: int, duration: int, cycles: int):

    for i in range(cycles):
        dac_toggle(dac, level, interval, duration//interval)
        time.sleep_ms(100)
        dac_toggle(dac, level, interval, duration//interval)
        time.sleep_ms(725)

# ALARM NOISE: test_alarm_noise(255, 333, 50000, 5)

_SD_BUS_SLOT = const(3)
_SD_BUS_FREQ = const(20_000_000)
_SD_BUS_SCK = const(14)
_SD_BUS_MISO = const(12)
_SD_BUS_MOSI = const(13)
_SD_BUS_CS = const(15)

def mount_sd(mount_pt: str) -> bool:
    sd = None

    try:
        sd = SDCard(
            slot=_SD_BUS_SLOT,
            freq=_SD_BUS_FREQ,
            sck=Pin(_SD_BUS_SCK, Pin.OUT),
            miso=Pin(_SD_BUS_MISO, Pin.OUT), 
            mosi=Pin(_SD_BUS_MOSI, Pin.OUT), 
            cs=Pin(_SD_BUS_CS, Pin.OUT)
        )
    except OSError:
        print("sd card unreadable/not present")
        return False

    try:
        vfs.mount(sd, mount_pt)
    except OSError:
        print("sd card unmountable/corrupt")
        return False

    return True

def stub_import(*args):
    print(f"got import args {args}")

_ORIG_IMPORT = __import__

_PATCH_LISTS = {
    "main": {
    },
    "ucrypto.hmac": {
        "compare_digest": stub_import
    }
}

def patched_import(name: str, globals: dict | None, locals: dict | None, fromlist: tuple, level: int):
    print(f"importing path {name}")

    if name in sys.modules:
        print("already imported; skipping")
        return sys.modules[name]

    print(f"\nglobals {globals}")
    print(f"\nlocals {locals}")
    print(f"\nfromlist: {fromlist}")
    print(f"import level {level}")

    in_module = _ORIG_IMPORT(name, globals, locals, fromlist, level)

    if name in _PATCH_LISTS:
        patch_def = _PATCH_LISTS[name]
        print("module has patch definitions")

        for attr in patch_def:
            if hasattr(in_module, attr):
                print(f"patching attr {attr}")
                setattr(in_module, attr, patch_def[attr])
            else:
                print(f"warning: missing attribute {attr}")
        
    else:
        print("no patch def found")

    return in_module

def firm_entry(pubkey, nvs):
    print("have code exec post firm_entry")

    micropython.mem_info(1)
    gc.collect()
    gc.collect()
    micropython.mem_info(1)

    print(f"dir {dir()}")

    print(f"globals {globals()}\n")
    print(f"locals {locals()}\n")
    print(f"path {sys.path}\n")
    print(f"modules {sys.modules}\n")
    print()

    for name, module in sys.modules.items():
        print(f"{name} dir {dir(module)}")

    print(f"current root {os.listdir()}")

    # mount flash for more debugging
    print("attempting nor flash mount")

    data_partitions = Partition.find(Partition.TYPE_DATA, label="vfs")

    if len(data_partitions) == 0:
        # Partition unmountable (since it cannot be found)
        print("cannot locate data partition")

    try: 
        vfs.mount(data_partitions[0], "/")
    except OSError:
        print("data partition corrupt/unmountable")

    # NOR mount done

    if mount_sd("/sd"):
        print("sd mounted")

    print("done testing; entering fake repl")

    # Inject patcher
    import builtins
    builtins.__import__ = patched_import
    print("import patcher injected")

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