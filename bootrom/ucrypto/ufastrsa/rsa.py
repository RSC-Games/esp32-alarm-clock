from ucrypto.ufastrsa.srandom import rndsrcnz

class RSA:
    def __init__(self, bits, n, e=0, d=0):
        self.bits = bits
        self.bytes = (bits + 7) >> 3
        self.n = n
        self.e = e
        self.d = d
        self.rndsrcnz = rndsrcnz

    def pkcs_sign(self, value):
        len_padding = self.bytes - 3 - len(value)
        assert len_padding >= 0, len_padding
        base = int.from_bytes(
            b"\x00\x01" + len_padding * b"\xff" + b"\x00" + value, "big"
        )
        return int.to_bytes(pow(base, self.d, self.n), self.bytes, "big")

    # TODO: patch pcks asserts (should be replaced with ifs)
    def pkcs_verify(self, value):
        if not len(value) == self.bytes:
            raise RuntimeError("invalid signature")

        signed = int.to_bytes(
            pow(int.from_bytes(value, "big"), self.e, self.n), self.bytes, "big"
        )
        idx = signed.find(b"\0", 1)

        if not (idx != -1 and signed[:idx] == b"\x00\x01" + (idx - 2) * b"\xff"):
            raise RuntimeError("pkcs1 signature not properly formatted")

        return signed[idx + 1 :]

    def pkcs_encrypt(self, value):
        len_padding = self.bytes - 3 - len(value)
        assert len_padding >= 0
        base = int.from_bytes(
            b"\x00\x02" + self.rndsrcnz(len_padding) + b"\x00" + value, "big"
        )
        return int.to_bytes(pow(base, self.e, self.n), self.bytes, "big")

    def pkcs_decrypt(self, value):
        assert len(value) == self.bytes
        decrypted = int.to_bytes(
            pow(int.from_bytes(value, "big"), self.d, self.n), self.bytes, "big"
        )
        idx = decrypted.find(b"\0", 2)
        assert idx != -1 and decrypted[:2] == b"\x00\x02"
        return decrypted[idx + 1 :]
