from bootloader import uart_rcm, output
import traceback
import time
import sys
import os

def compile_payload(payload: str) -> int:
    payload_source = f"{os.path.splitext(payload)[0]}.py"

    if os.path.exists(payload_source):
        # Precompile payload
        ret = os.system(f"mpy-cross -march=xtensawin {payload_source}")

        if ret != 0:
            output.print_tool("precompile payload failed; aborting upload!")
            return -1

    else:
        output.print_tool("payload source missing; injecting bin")
        
    return 0

def main(payload: str):
    output.print_tool("attempting to open device...")

    try:
        rcm = uart_rcm.open_device("/dev/ttyUSB0")

        t_start_ms = time.monotonic_ns() / 1_000_000
        uart_rcm.boot_payload(rcm, payload)
        t_end_ms = time.monotonic_ns() / 1_000_000
        
        output.print_tool(f"payload injected; took {(t_end_ms - t_start_ms):.2f} ms")
        uart_rcm.run_user_connection_tool(rcm)
    except OSError as ie:
        output.print_tool(f"error: unable to read from device")
        traceback.print_exception(ie)


if __name__ == "__main__":
    payload = sys.argv[1]
    if compile_payload(payload) == 0:
        main(payload)