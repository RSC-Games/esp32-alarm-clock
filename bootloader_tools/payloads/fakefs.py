from io import BytesIO
from vfs import mount
import sys

class FakeFS:
    def __init__(self, fname: str, in_bytes: bytes) -> None:
        """
        Initializes a fake FS. Takes the filename (target file path) of the singular file
        and creates a fake file entry.
        """
        self.fname = f"/{fname}"
        self.f_bytes = in_bytes

    def mount(self, readonly: bool, _: bool) -> None:
        if not readonly:
            raise OSError("ro fs cannot be mounted rw")
        
        # Don't care otherwise (tho idk what the _ is)

    def umount(self) -> None:
        del self.fname
        del self.f_bytes

    def open(self, path: str, perms: str) -> BytesIO:
        if not path == self.fname:
            raise OSError("ENOENT")
        
        if not perms == "rb":
            raise OSError("EPERM")
        
        return BytesIO(self.f_bytes)
    
    def stat(self, path: str) -> tuple:
        if not path == self.fname:
            raise OSError("ENOENT")
        
        return (16384, 0, 0, 0, 0, 0, len(self.f_bytes), 0, 0, 0)

    def statvfs(self, path: str) -> tuple:
        raise NotImplementedError("not implemented")

    def rename(self, src: str, dest: str) -> None:
        raise OSError("EPERM")

    def rmdir(self, path: str) -> None: 
        raise OSError("EPERM")

    def remove(self, path: str) -> None:
        raise OSError("EPERM")
        
    def mkdir(self, path: str) -> None:
        raise OSError("EPERM")
        
    def ilistdir(self, path: str): # -> Iterable:
        # NOTE: not implemented
        pass

    def chdir(self, path: str) -> None:
        pass

    def getcwd(self) -> str:
        return "/"


def do_fake_repl():
    fs = None

    try:
        fs = FakeFS("file", bytes(512))

        mount(fs, "/test", readonly=True)
    except BaseException as ie:
        sys.print_exception(ie)

    while True:
        print(sys.ps1, end="")
        in_text = sys.stdin.readline()

        try:
            out = eval(in_text, globals().update({'fs':fs}), locals())

            if out is not None:
                print(out)
        except:
            try:
                exec(in_text, globals().update({'fs':fs}), locals())
            except BaseException as ie:
                sys.print_exception(ie)


def firm_entry(_, _2):
    do_fake_repl()