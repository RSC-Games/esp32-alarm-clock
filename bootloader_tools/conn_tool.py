from bootloader import uart_rcm, output
import time
import sys
import os

def compile_payload(payload: str) -> None:
    payload_source = f"{os.path.splitext(payload)[0]}.py"

    if os.path.exists(payload_source):
        # Precompile payload
        ret = os.system(f"mpy-cross {payload_source}")

        if ret != 0:
            output.print_tool("precompile payload failed; injecting old version")

    else:
        output.print_tool("payload source missing; injecting bin")

def main(payload: str):
    output.print_tool("attempting to open device...")

    try:
        rcm = uart_rcm.open_device("/dev/ttyUSB1")

        t_start_ms = time.monotonic_ns() / 1_000_000
        uart_rcm.boot_payload(rcm, payload)
        t_end_ms = time.monotonic_ns() / 1_000_000
        
        output.print_tool(f"payload injected; took {(t_end_ms - t_start_ms):.2f} ms")
        uart_rcm.run_user_connection_tool(rcm)
    except OSError:
        output.print_tool(f"error: unable to read from device")


if __name__ == "__main__":
    payload = sys.argv[1]
    compile_payload(payload)
    main(payload)