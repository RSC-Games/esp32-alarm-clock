from __nvs_perms import ReadOnlyNVS
from esp32 import Partition
import machine
import vfs
import os

# NOTE: this payload removes the installed app firm blob

def firm_entry(_, nvs: ReadOnlyNVS):
    data_partitions = Partition.find(Partition.TYPE_DATA, label="vfs")
    print(data_partitions)
    vfs.mount(data_partitions[0], "/")

    os.unlink(f"{nvs.get_str("firm")}.img")
    machine.reset()