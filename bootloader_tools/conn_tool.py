from bootloader import uart_rcm
import threading


print("attempting to open device")
rcm = uart_rcm.open_device("COM3")
print("connection succeeded; device waiting for commands...")

if not uart_rcm.bootrom_is_ready(rcm):
    raise OSError("bootrom didn't accept handshake!")

uart_rcm.boot_payload(rcm, "./payloads/fakefs.mpy")

def do_write_pipe():
    try:
        while True:
            in_text = input()
            rcm.write(in_text.encode() + b"\n")
    except EOFError:
        return

thread = threading.Thread(target=do_write_pipe)
thread.daemon = True
thread.start()

try:
    while True:
        print(rcm.read(1).decode(errors="replace"), end='', flush=True)
except KeyboardInterrupt:
    print("connection terminated")