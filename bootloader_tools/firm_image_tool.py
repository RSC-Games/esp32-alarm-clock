from bootloader import uart_rcm, uart_imager, output
import traceback
import time
import sys
import os

def main(firm_name: str):
    output.print_tool("attempting to open device...")

    try:
        rcm = uart_rcm.open_device("/dev/ttyUSB1")

        t_start_ms = time.monotonic_ns() / 1_000_000
        uart_rcm.boot_payload(rcm, "../gen_imager.mpy")
        t_end_ms = time.monotonic_ns() / 1_000_000
        
        output.print_tool(f"payload injected; took {(t_end_ms - t_start_ms):.2f} ms")
        output.print_tool(f"connecting to imager console....")

        if not uart_imager.connect(rcm):
            output.print_tool("error: unable to connect to device")
            return
        
        t_start_ms = time.monotonic_ns() / 1_000_000
        upload_success = uart_imager.upload_firm(rcm, firm_name)
        t_end_ms = time.monotonic_ns() / 1_000_000

        output.print_tool(f"firm uploaded; took {(t_end_ms - t_start_ms):.2f} ms")

        if not upload_success:
            output.print_tool("error: upload failed")
            uart_rcm.run_user_connection_tool(rcm)
            return
        
        uart_imager.reboot(rcm)
        uart_rcm.run_user_connection_tool(rcm)

    except OSError as ie:
        traceback.print_exception(ie)
        output.print_tool(f"error: unable to read from device")


if __name__ == "__main__":
    firm_name = sys.argv[1]
    main(firm_name)