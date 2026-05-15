################################################### ULP DRIVER #################################################
# ULP is quite a stupid device >.<
# SYMBOLS:	ADDR	WORD	NAME
# 			0x0000 	0x0000 	entry
# 			0x0004 	0x0001 	sample_array0
# 			0x0b6c 	0x02db 	code_load_addr_1
# 			0x0b78 	0x02de 	sample_array1
# 			0x16e0 	0x05b8 	code_load_addr_2
# 			0x16f0 	0x05bc 	active_array
ULP_BASE = const(0x50000000)
_ULP_LEN = const(0x1700)
ULP_ENTRY = const(0x0000)
ULP_SAMPLE_ARRAY0 = const(0x0004)
_ULP_LADDR_1 = const(0x0b6c)
ULP_SAMPLE_ARRAY1 = const(0x0b78)
_ULP_LADDR_2 = const(0x16e0)
ULP_ACTIVE_ARRAY = const(0x16f0)

# ULP HEADER is +12 bytes to the full image size.
# CODE BELOW HERE IS NOT AUTO GENERATED!
_ulp_hdr = b'ulp\x00\x0c\x00\xf0\x16\x04\x00\x00\x00'
_ulp_seg0 = b'\xc3[\x80r'
_ulp_seg1 = b'\x01\x00\x80r\r\x00\x00h\x05\x00\x00@'
_ulp_seg2 = b'\x11\x00\x80r\r\x00\x00h\x01\x00\x00@\x04\x00\x00\x80\x00\x00\x00\x00'

def rebuild_ulp_binary() -> bytearray:
    array_offset = len(_ulp_hdr)
    ulp_firmware = bytearray(_ULP_LEN) # already accounts for header??

    # header
    for byte in range(array_offset):
        ulp_firmware[byte] = _ulp_hdr[byte]

    # seg0 (register init; offset ENTRY)
    for byte in range(len(_ulp_seg0)):
        ulp_firmware[array_offset + ULP_ENTRY + byte] = _ulp_seg0[byte]

    # seg1 (prepare buffer 0 for cpu; offset CODE_LOAD_ADDR1)
    for byte in range(len(_ulp_seg1)):
        ulp_firmware[array_offset + _ULP_LADDR_1 + byte] = _ulp_seg1[byte]

    # seg2 (prepare buffer 1 for cpu; offset CODE_LOAD_ADDR1)
    for byte in range(len(_ulp_seg2)):
        ulp_firmware[array_offset + _ULP_LADDR_2 + byte] = _ulp_seg2[byte]

    return ulp_firmware
