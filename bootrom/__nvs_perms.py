# Higher-level driver for the NVS subsystem.
from esp32 import NVS

# Forced RO permissions for hardware.
class ReadOnlyNVS(NVS):
    def __init__(self, nspace: str):
        super().__init__(nspace)    

    # Writes unsupported (in theory, executed by lockout)
    
    # Helper for easily getting variable-length strings.
    def get_str(self, flag: str) -> str:
        """
        NVS driver doesn't support the NVS string function, so
        we will be adding it here.
        """
        s_len = self.get_i32(f"l{flag}")
        dat = bytearray(s_len)
        self.get_blob(flag, dat)
        return dat.decode()
    
    # Helper for easily writing variable-length strings.
    def set_str(self, flag: str, val: str) -> None:
        """
        Write a string value (and pretend its a byte value)
        """
        self.set_i32(f"l{flag}", len(val))
        self.set_blob(flag, val)
    
    # Helper for easily getting variable-length blobs.
    def get_blobn(self, flag: str) -> bytes:
        len = self.get_i32(f"l{flag}")
        dat = bytearray(len)
        self.get_blob(flag, dat)
        return dat
    
    # Helper for easily setting variable-length blobs.
    def set_blobn(self, flag: str, bin: bytes) -> None:
        self.set_i32(f"l{flag}", len(bin))
        self.set_blob(flag, bin)
    
    def _lockout(self) -> None:
        def __stub(*args, **kwargs) -> None:
            raise OSError(1, "EPERM")
        
        self.set_i32 = __stub
        self.set_blob = __stub
        self.set_str = __stub
        self.set_blobn = __stub
        self.commit = __stub

        # Prevent reinjection of valid write functions.
        self.__setattr__ = __stub