#
# This file is part of the micropython-esp32-ulp project,
# https://github.com/micropython/micropython-esp32-ulp
#
# SPDX-FileCopyrightText: 2018-2023, the micropython-esp32-ulp authors, see AUTHORS file.
# SPDX-License-Identifier: MIT

from .util import garbage_collect

from .preprocess import preprocess
from .assemble import Assembler
from .link import make_binary
garbage_collect('after import')


def src_to_binary_ext(src, cpu):
    assembler = Assembler(cpu)
    src = preprocess(src)
    assembler.assemble(src, remove_comments=False)  # comments already removed by preprocessor
    garbage_collect('before symbols export')
    addrs_syms = assembler.symbols.export()
    text, data, bss_len = assembler.fetch()
    return make_binary(text, data, bss_len), addrs_syms


def src_to_binary(src, cpu):
    binary, addrs_syms = src_to_binary_ext(src, cpu)
    print('\033[33mSYMBOLS:\tADDR\tWORD\tNAME\033[0m')
    for addr_words, sym in addrs_syms:
        addr_bytes = addr_words * 4
        print('\033[33m\t\t0x%04x \t0x%04x \t%s\033[0m' % (addr_bytes, addr_words, sym))
    return binary, addrs_syms


def assemble_file(filename, cpu):
    with open(filename) as f:
        src = f.read()

    binary = src_to_binary(src, cpu)

    if filename.endswith('.s') or filename.endswith('.S'):
        filename = filename[:-2]
    with open(filename + '.ulp', 'wb') as f:
        f.write(binary)

