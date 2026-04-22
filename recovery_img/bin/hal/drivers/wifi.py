
from hal.drivers.fbcon import GLOBAL_FBCON
from __nvs_perms import ReadOnlyNVS
from network import WLAN
import network
import logs
import time


# Network configuration NVS:
# Stores all of the currently associated network devices.
# Supports up to 8 network slots, with each slot's usage represented by a
# bitmask 'slots'. A 0 value means unused, and a 1 means used.
#
# NVS format:
# - slots (int): bitmask representing used/unused entries. Only 8 are supported.
# - last (int): most recently used slot. Used to speed up network association.
# - net<x>_ssid: network slot <x> ssid
# - net<x>_auth: network slot <x> authentication mode (determined at scan time)
# - net<x>_psk: network slot <x> psk/hash
#
# WiFi passwords are currently stored unencrypted.
#
# TODO: Use a unique key to encrypt the wifi information (use hidden unique aes key
# + the shared public key + mac address)
class NetworkConfig(ReadOnlyNVS):
    def __init__(self) -> None:
        super().__init__("config-wifi")
        logs.print_warning("net", "WiFi configuration info is not encrypted!")

        try:
            self.get_i32("slots")
        except OSError:
            # Initialize wifi config data
            self.set_i32("slots", 0x00)
            self.set_i32("last", -1)
            self.commit()

    def get_free_slot(self) -> int | None:
        """
        Find the last occurring free slot in the NVS, or return None
        if no slots are available.
        """
        slots = self.get_i32("slots")

        for i in range(8):
            if slots & 0x1 == 0:
                return i
            
            slots >>= 1

        return None
    
    def _mark_slot_allocated(self, slot_id: int) -> None:
        """
        Mark a slot in the bitmask as allocated, if it hasn't already
        been so marked. Commit is deferred.
        """
        if self.slot_used(slot_id):
            raise OSError("cannot allocate used slot!")
        
        slots = self.get_i32("slots")
        slots |= 1 << slot_id
        self.set_i32("slots", slots)

    def free_slot(self, slot_id: int) -> None:
        """
        Mark a slot as freed. The changes are instantly committed.
        """
        if not self.slot_used(slot_id):
            raise OSError("cannot free already freed slot!")
        
        # Prevent dangling reference to the now unused slot.
        if self.get_i32("last") == slot_id:
            self.set_i32("last", -1)
        
        slots = self.get_i32("slots")
        slots ^= ~(1 << slot_id)
        self.set_i32("slots", slots)
        self.erase_key(f"net{slot_id}_ssid")
        self.erase_key(f"net{slot_id}_auth")
        self.erase_key(f"net{slot_id}_psk")
        self.commit()
    
    def slot_used(self, slot: int) -> bool:
        """
        Determine whether the requested slot is currently in use or not.
        """
        return self.get_i32("slots") & (1 << slot) == 1
    
    def set_slot(self, slot: int, ssid: str, auth: int, psk: str) -> None:
        """
        Set/update the access point data stored within the provided slot.
        Immediate commit is forced.
        """
        if not self.slot_used(slot):
            self._mark_slot_allocated(slot)

        self.set_str(f"net{slot}_ssid", ssid)
        self.set_i32(f"net{slot}_auth", auth)
        self.set_str(f"net{slot}_psk", psk)
        self.commit()

    def set_most_recent(self, slot: int) -> None:
        """
        Set the most recently connected slot to the provided slot, if it hasn't
        already been updated.
        """
        if self.slot_used(slot) and self.get_i32("last") != slot:
            self.set_i32("last", slot)
            self.commit()

    def get_most_recent_id(self) -> int:
        """
        Get the most recently connected network slot id (useful for a full spread
        wifi search and enables the driver to skip the already tested most recent)
        """
        return self.get_i32("last")

    def get_most_recent_slot(self) -> tuple[str, int, str] | None:
        """
        Load the connection information for the most recent network connection,
        if any exists.
        """
        last = self.get_i32("last")

        # No previous slot.
        if last == -1:
            return None

        return self.get_slot(last)

    def get_slot(self, slot: int) -> tuple[str, int, str]:
        """
        Get the connection information at the requested network slot.
        """
        if not self.slot_used(slot):
            raise OSError("attempting to read unallocated slot!")
        
        ssid = self.get_str(f"net{slot}_ssid")
        auth = self.get_i32(f"net{slot}_auth")
        psk = self.get_str(f"net{slot}_psk")

        return ssid, auth, psk


class WiFiManager:
    def __init__(self):
        self.net_cfg = NetworkConfig()
        self.wlan = WLAN(WLAN.IF_STA)
        self.scan_results = []


    # TODO: Bring up should run in a separate thread
    def bring_up(self) -> bool:
        """
        Enable the network and try to connect to any of the registered
        slots.
        """
        self.wlan.active(True)
        self.scan_results = self.wlan.scan()
        self.wlan.config(reconnects=10)

        # Try most recently associated network
        last_network = self.net_cfg.get_most_recent_slot()

        if last_network is not None:
            GLOBAL_FBCON.write_line("i: TRY assoc last network")

            if self.try_connect(last_network):
                return True
            
        # Try sequential connections (excluding the most recent)
        last_net_id = self.net_cfg.get_most_recent_id()

        for slot_id in range(8):
            if slot_id == last_net_id or not self.net_cfg.slot_used(slot_id):
                continue

            GLOBAL_FBCON.write_line(f"i: TRY assoc net slot {slot_id}")
            network_info = self.net_cfg.get_slot(slot_id)

            if self.try_connect(network_info):
                return True

        # No networks available/registered. 
        logs.print_warning("recovery", "no networks available")
        return False
    
    def link_is_up(self) -> bool:
        return self.wlan.isconnected()

    def try_connect(self, last_network: tuple[str, int, str]) -> bool:
        ssids = [res[0].decode() for res in self.scan_results]

        # Don't bother connecting when the ssid isn't even available
        if not last_network[0] in ssids:
            return False
        
        if last_network[1] == network.WLAN.SEC_OPEN:
            self.wlan.connect(last_network[0])
        else:
            self.wlan.connect(last_network[0], last_network[2])

        # Wait for proper connection.
        while self.wlan.status() == network.STAT_CONNECTING:
            print('waiting')
            time.sleep_ms(100)

        network_state = self.wlan.status()
        logs.print_info("net", f"got ending wifi state {network_state}")

        return network_state == network.STAT_GOT_IP
    
    def get_ip(self) -> str:
        return self.wlan.ipconfig("addr4")[0]