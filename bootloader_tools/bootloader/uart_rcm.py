from . import output

import threading
import binascii
import hashlib
import struct
import serial
import time

# USB/UART recovery bootloader (data link layer)
_UART_RCM_CONN_RETRIES = 10
_UART_RCM_CONN_MAX_BYTES_TO_TIMEOUT = 1024
_UART_RCM_BANNER = b"\x55BOOT_RCM_RSC\xAA"
_UART_RCM_CONN_ESTABLISHED = b"\xAARSC_RCM_BOOT\x55"

# Header contains 8b header prefix then 4 byte length field
# Meant to be used with struct.pack(). crc32 is calculated over the entire
# packet minus the last 4 bytes (left as zeroes)
# RCM packet has:
# - 4 byte header
# - 2 byte flags field 0b(ready)XXXXX(invalid)(badcrc)
# - 2 byte length field (payload size + 4 bytes crc32)
# - n - 4 bytes data payload
# - 4 bytes crc32
_UART_RCM_HEADER = "<4sHH"
_UART_RCM_HEADER_LEN = struct.calcsize(_UART_RCM_HEADER)
_UART_RCM_PACKET = "<8s{}sI"
_UART_RCM_HEADER_PREFIX = b"\x64RCM"
_UART_RCM_FLAG_READY = 0x80
_UART_RCM_FLAG_OK = 0x70
_UART_RCM_FLAG_COMMAND_ERROR = 0x4
_UART_RCM_FLAG_INVALID_PACKET = 0x2
_UART_RCM_FLAG_CORRUPT_PACKET = 0x1

# RCM (transport layer)
# - 2 byte command, 
# - n - 2 bytes payload
_UART_RCM_DATA_PACKET = "<H{}s"

# BOOT command payload has
# - 512 bytes signature
# - n - 512 bytes data
_UART_RCM_CMD_BOOT = 2


def _establish_connection(uart: serial.Serial) -> bool:
    """
    Attempt connection to the device 10 times. After those 10 times,
    if a valid header is not found, give up.

    :param uart: Created serial object representing this device.
    :return: Whether the device could be connected to.
    """

    for i in range(_UART_RCM_CONN_RETRIES):
        # Seek forward in the input stream until a start byte is found.
        found_end_byte = False

        for _ in range(_UART_RCM_CONN_MAX_BYTES_TO_TIMEOUT):
            c = uart.read(1)
            print(c.decode(errors="replace"), end="", flush=True)

            if c == _UART_RCM_BANNER[-1].to_bytes(1):
                found_end_byte = True
                break

        if not found_end_byte:
            output.print_tool(f"no found start byte; retrying ({i+1}/{_UART_RCM_CONN_RETRIES})")
            time.sleep(0.1)
            continue
            
        # Wait for the full header (header will be sent right after a newline)
        while uart.in_waiting < len(_UART_RCM_BANNER):
            pass

        if (uart.read(len(_UART_RCM_BANNER)) == _UART_RCM_BANNER):
            print()
            output.print_tool("got header; sending connection request...")
            uart.write(_UART_RCM_CONN_ESTABLISHED)
            uart.flush()
            return True
        
        output.print_tool(f"connection attempt failed; retrying ({i+1}/{_UART_RCM_CONN_RETRIES})")
        
    return False


def _build_datalink_packet(flags: int, payload: bytes) -> bytearray:
    """
    Build a UART packet to send to the bootrom with the provided flags and payload.
    """

    payload_sz = len(payload)
    header = struct.pack(_UART_RCM_HEADER, _UART_RCM_HEADER_PREFIX, flags, payload_sz + 4)
    data_packet = bytearray(_UART_RCM_HEADER_LEN + payload_sz + 4)

    struct.pack_into(_UART_RCM_PACKET.format(payload_sz), data_packet, 0, header, payload, 0)
    struct.pack_into("<I", data_packet, _UART_RCM_HEADER_LEN + payload_sz, binascii.crc32(data_packet))
    return data_packet


def _get_datalink_packet(uart: serial.Serial) -> tuple[int, bytes] | None:
    """
    Get a full packet from the device and return its undecoded contents and flags.

    :param uart: The device port
    :return: Packet flags and the raw payload bytes
    """

    # Wait for the header to be available.
    header = uart.read(_UART_RCM_HEADER_LEN)
    header_magic, flags, size = struct.unpack(_UART_RCM_HEADER, header)

    # Ensure valid header (can't really read anything with an illegal header)
    # NOTE: This will spam packets to the host until the payload is fully transferred
    # unless transmission is cut off early.
    if header_magic != _UART_RCM_HEADER_PREFIX:
        raise OSError(f"got illegal header magic {header_magic}")

    # NOTE: Flags are a DONT CARE (ignore them)
    # Read the rest of the packet payload.
    packet = bytearray(_UART_RCM_HEADER_LEN + size)
    payload_section = memoryview(packet)[_UART_RCM_HEADER_LEN:-4]

    struct.pack_into(_UART_RCM_HEADER, packet, 0, header_magic, flags, size)

    # Ensure CRC section is zeroed
    uart.readinto(payload_section)
    recv_crc = int.from_bytes(uart.read(4), "little")

    packet_crc = binascii.crc32(packet)

    # Ensure packet hasn't been corrupted during transfer.
    if packet_crc != recv_crc:
        print(f"warning: packet corrupt: got crc {packet_crc} recv'd {recv_crc}")
        print(f"packet contents {packet}")
        return None
    
    return int(flags), bytes(payload_section)


def endpoint_reset(uart: serial.Serial) -> None:
    """
    Reset the device. EN is active low. Prevent the device from resetting into ESP-IDF
    download boot mode.
    """
    uart.dtr = False
    uart.rts = True
    time.sleep(0.1)
    uart.rts = False


def strobe_bootsel(uart: serial.Serial) -> None:
    """
    Strobe the boot selector pin. GPIO0 is active low.
    """
    uart.dtr = True


def open_device(port: str) -> serial.Serial:
    """
    Get a device on the given serial port and open a connection
    to it. Baudrate is hardcoded to 115200 due to current micropython
    limitations.

    The returned device will be fully initialized and in UART boot mode.

    :param port: Serial port to use (COMx on windows, /dev/ttyUSBx on linux)
    :return: Serial port instance.

    :throws OSError: When the serial port could not be connected to.
    """

    serial_port = serial.Serial(port, 115200, timeout=0.25)

    # Reset the device, then enter UART recovery mode (if possible)
    endpoint_reset(serial_port)
    serial_port.read_until()
    time.sleep(0.5)
    strobe_bootsel(serial_port)

    if not _establish_connection(serial_port):
        raise OSError("connection attempt failed")
    
    if not bootrom_is_ready(serial_port):
        raise OSError("bootrom refused handshake")
    
    output.print_tool("connection succeeded; ready for commands")

    serial_port.dtr = False
    return serial_port


def bootrom_is_ready(uart: serial.Serial) -> bool:
    """
    Determine if the bootrom is waiting for another command.

    :return: If the bootrom is waiting for command issuance.
    """

    res = _get_datalink_packet(uart)

    if res is None:
        output.print_tool("response: bad crc")
        return False
    
    flags, payload = res

    output.print_tool(f"response: flags {flags} payload {payload}")

    return flags & (_UART_RCM_FLAG_READY | _UART_RCM_FLAG_OK) != 0


def boot_payload(uart: serial.Serial, payload_path: str) -> bool:
    firm_payload = open(payload_path, "rb")
    firm_bytes = firm_payload.read()

    firm_array = bytearray(len(firm_bytes) + 512)
    firm_array[:2] = int.to_bytes(2, 2, "little")
    firm_array[2 + 512:] = firm_bytes

    output.print_tool(f"injecting payload sha256 {hashlib.sha256(firm_bytes).hexdigest()} len {len(firm_array[2+512:])} B")

    packet = _build_datalink_packet(0, firm_array)
    uart.write(packet)

    if not bootrom_is_ready(uart):
        raise OSError("payload injection failed")
    
    return False


def run_user_connection_tool(rcm: serial.Serial):
    """
    Allow the user to directly send bytes from the keyboard to the connected
    device. Useful for using a REPL or serial port after booting a payload.

    :param rcm: Device to connect to.
    """

    output.print_tool("uart boot exited; starting user i/o pipe")

    def do_write_pipe():
        try:
            while True:
                in_text = input()
                rcm.write(in_text.encode() + b"\n")
        except EOFError:
            return

    thread = threading.Thread(target=do_write_pipe, daemon=True)
    thread.start()

    try:
        while True:
            print(rcm.read(1).decode(errors="replace"), end='', flush=True)
            
    except KeyboardInterrupt:
        print()
        output.print_tool("connection terminated")