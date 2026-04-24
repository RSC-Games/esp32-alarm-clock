from esp32 import Partition
import machine
import vfs
import os


def firm_entry(_, _2):
    data_partitions = Partition.find(Partition.TYPE_DATA, label="vfs")
    print(data_partitions)
    vfs.mount(data_partitions[0], "/")

    os.unlink("clock_firm.img")
    machine.reset()