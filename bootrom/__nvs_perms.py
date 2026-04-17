# Higher-level driver for the NVS subsystem.
from _mpy_shed.buffer_mp import AnyReadableBuf
from esp32 import NVS

# Forced RO permissions.
# TODO: allow write permissions if unlocked (write command will be stubbed
# out for any non-recovery firmware if locked)
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
        len = self.get_i32(f"{flag}_len")
        dat = bytearray(len)
        self.get_blob(flag, dat)
        return dat.decode()
    

    def _lockout(self) -> None:
        def __stub(*args, **kwargs) -> None:
            raise OSError(1, "EPERM")
        
        self.set_i32 = __stub
        self.set_blob = __stub
        self.commit = __stub