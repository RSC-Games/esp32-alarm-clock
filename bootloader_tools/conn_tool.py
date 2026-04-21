from bootloader import uart_rcm
import threading


print("attempting to open device...")
rcm = uart_rcm.open_device("/dev/ttyUSB0")

if not uart_rcm.bootrom_is_ready(rcm):
    raise OSError("bootrom didn't accept handshake")

print("connection succeeded; device waiting for commands...")

uart_rcm.boot_payload(rcm, "./payloads/boot_nvs_imager.mpy")

# ATTEMPT NOR BOOT
#uart_rcm.boot_payload(rcm, "./payloads/workaround_nor_boot.mpy")

# UPDATE ROM:
#uart_rcm.boot_payload(rcm, "../gen_imager.mpy")
uart_rcm.run_user_connection_tool(rcm)