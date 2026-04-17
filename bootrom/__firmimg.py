# NOTE! NEEDS TO BE MOVED INTO THE ROM CODE ALONG WITH THE 
# RAMDISK!
from micropython import const
from random import getrandbits
from cryptolib import aes
from os import stat


# Encryption modes:
_MODE_ECB = const(1)
_MODE_CBC = const(2)

# Disk emulation via a file. Note: does not contain MBR or
# VBR.
class FirmwareImage:

    def __init__(self, exe_f, exe_path: str, key: bytes | None, iv: bytes | None, block_size=4096):
        # Reuse previous file pointer (for security hardening)
        self.block_size = block_size
        self._df = exe_f
        self.blocks = stat(exe_path)[6] // self.block_size

        # Fake encryption/decryption driver (in case aes isn't
        # available/disabled)
        class _emuaes():

            def __init__(self):
                pass

            def decrypt(self, in_buf, out_buf=None):
                if out_buf:
                    out_buf = in_buf
                    return
                return in_buf

            def encrypt(self, in_buf, out_buf=None):
                if out_buf:
                    out_buf = in_buf
                    return
                return in_buf
        
        # Start the decryption service.
        if key == None:
            self._dec = _emuaes()
            self._enc = self._dec
        else:
            self._dec = aes(key, _MODE_ECB, iv)
            self._enc = aes(key, _MODE_ECB, iv)


    def readblocks(self, block_num: int, buf: bytearray) -> None:
        # Note! On the fly decryption may be needed.
        self._df.seek(self.block_size * block_num)
        self._df.readinto(buf)
        self._dec.decrypt(buf, buf)


    def writeblocks(self, block_num: int, buf: bytearray) -> None:
        # Write blocks will not be implemented!
        raise OSError("Executable disks are read-only!")  # Enabled in production.
        self._df.seek(self.block_size * block_num)
        self._enc.encrypt(buf, buf)
        self._df.write(buf)


    def ioctl(self, op: int, _):
        if op == 2:  # shut down device.
            self._df.close()
        if op == 4:  # get number of blocks
            return self.blocks
        if op == 5:  # get block size
            return self.block_size


# NOTE! Disabled in production!
# def mk_exedisk(path, block_sz, blocks, key, iv):

#     if os.path.exists(path):
#         overwrite_disk = input("overwrite disk? (y or n): ")
#     else:
#         overwrite_disk = "y"

#     if overwrite_disk.lower().startswith("y"):
#         f = open(path, "wb")

#         print("building block")
#         block_contents = b"\xFF" * block_sz

#         print("building disk")
#         for block in range(0, blocks):
#             f.write(block_contents)
 
#         f.close()

#         print("disk build complete")

#     # Initialize the disk.
#     disk = ExecutableDisk(path, key, iv, block_sz)
#     os.VfsFat.mkfs(disk)
#     print("initialized disk")

#     # Read the disk.
#     vfs = os.VfsFat(disk)
#     print("loaded disk vfs")
    
#     return vfs


# def genkeys(key_len, iv_len):
#     key = b""

#     for i in range(0, key_len // 32):
#         key = key + int.to_bytes(getrandbits(32), 4, "little")

#     iv = b""
#     for i in range(0, iv_len // 32):
#         iv = iv + int.to_bytes(getrandbits(32), 4, "little")

#     return key, iv
        