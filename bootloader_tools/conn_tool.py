from bootloader import uart_rcm
from binascii import crc32
import struct


print("attempting to open device")
rcm = uart_rcm.open_device("/dev/ttyUSB0")
print("connection succeeded; device waiting for commands...")

if not uart_rcm.bootrom_is_ready(rcm):
    raise OSError("bootrom didn't accept handshake!")

uart_rcm.boot_payload(rcm, "./payloads/boot_nvs_imager.mpy")

while True:
    print(rcm.read(1).decode(errors="replace"), end='', flush=True)