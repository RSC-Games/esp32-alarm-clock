from internet_recovery import wifi_menu
from micropython import const, mem_info
#from esp import osdebug, LOG_INFO
from hal import peripherals, osk
from binascii import unhexlify
from hashlib import sha256
import recovery_utils
import requests
import logs
import sys

_CHUNK_SIZE = const(24*1024)
_RELEASE_URL = const("https://api.github.com/repos/rsc-games/esp32-alarm-clock/releases/latest")
_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'}

# Find the raw download urls for the firm components.
def get_artifact_urls(latest_release_url: str) -> tuple[tuple[str, str], tuple[str, str]]:
    release_data = requests.get(latest_release_url, headers=_HEADERS)

    if release_data.status_code != 200:
        raise OSError(f"code {release_data.status_code}")

    manifest = release_data.json()
    logs.print_info("recovery", f"found release \"{manifest["tag_name"]}\"")

    assets = manifest["assets"]
    del manifest

    out = {}

    # Extract download URLs
    for artifact in assets:
        artifact_name = artifact["name"]

        if artifact_name in ("clock_firm.img", "clock_firm.img.sig"):
            logs.print_info("recovery", f"found artifact {artifact_name} url {artifact['browser_download_url']}")
            logs.print_info("recovery", f"sig {artifact['digest']}")
            out[artifact_name] = (artifact["browser_download_url"], artifact["digest"])

    if len(out) != 2:
        logs.print_error("recovery", "unable to find firm urls")
        raise RuntimeError("unable to find firm urls")
    
    return out["clock_firm.img"], out["clock_firm.img.sig"]

# Download the entire requested firm contents from GitHub's upstream servers. 
# Hash checking (but NOT signature checking) is performed.
def download_artifact(artifact: tuple[str, str], install_path: str) -> None:
    artifact_res = requests.get(artifact[0], headers=_HEADERS)
    artifact_sha = artifact[1].split(":")

    # Micropython really only supports sha256 (or at least hardware accelerated)
    if artifact_sha[0] != "sha256":
        logs.print_error("recovery", f"bad hash type: {artifact_sha[0]}")
        raise OSError("EINVAL")

    artifact_sha = unhexlify(artifact_sha[1])

    if artifact_res.status_code != 200:
        raise OSError(f"code {artifact_res.status_code}")
    
    calc_hasher = sha256()
    buf = memoryview(bytearray(_CHUNK_SIZE))
    f = open(install_path, "wb")
    
    while True:
        sz = artifact_res.raw.readinto(buf)

        if sz < _CHUNK_SIZE:
            f.write(buf[:sz])
            calc_hasher.update(buf[:sz])
            break

        f.write(buf)
        calc_hasher.update(buf)

    calc_sha = calc_hasher.digest()

    # No SSL certificate is required for HTTPS; avoid installing corrupt files.
    if calc_sha != artifact_sha:
        logs.print_error("recovery", "artifact hash mismatch")
        raise OSError("EINVAL")

    artifact_res.close()
    f.close()


# Firm boot does hardware init.
# RECOVERY STAGES:
#   - Announce recovery mode and prompt for yes/no 
#   - Attempt internet connection (from one of the 6 connection slots in NVS)
#   - If none of those connections are available:
#       - Scan for networks, and ask user to connect to one.
#   - Attempt to download device firmware from the upstream github release page
#   - Download package hash
#   - Install package and reboot
#
# TODO: Eventually need the shared key
#
def main():
    # Boot splash (effectively)
    peripherals.FBCON.write_line("i: getting connection results")
    #osdebug(LOG_INFO)

    peripherals.FBCON.set_hidden(True)
    osk.prompt_ok("RECOVERY", ["Connect to the", "internet to", "repair the", "firmware?"])
    
    # Need network selection menu
    if not peripherals.NIC.link_is_up():
        peripherals.FBCON.write_line("w: no access point in range")

        # No new connection could be made. Cannot continue recovery from here.
        if not wifi_menu.run():
            sys.exit(-1)

        # Reconnection done; install time.

    try:
        # TODO: Move this code into an updater library
        peripherals.FBCON.set_hidden(False)
        peripherals.FBCON.write_line("i: locating firmware files")
        firm_info, firm_sig_info = get_artifact_urls(_RELEASE_URL)
        
        # Download firm files
        peripherals.FBCON.write_line("i: downloading firm/sig")
        download_artifact(firm_sig_info, "/clock_firm.img.sig.tmp")
        download_artifact(firm_info, "/clock_firm.img.tmp")

        # Install the firm files (unique path to avoid installing corrupt data
        # as the firmware). This does run the risk of leaving firmware files on disk
        # that are never used, but the main firmware can handle that.
        peripherals.FBCON.write_line("i: installing firmware")
        recovery_utils.install_new_firmware_local(".tmp")
        peripherals.FBCON.write_line("i: install complete. rebooting")
        sys.exit(0)

    except (OSError, RuntimeError) as ie:
        peripherals.FBCON.write_line("e: firmware download failure")
        logs.print_error("recovery", "unable to download firm")
        sys.print_exception(ie)
        sys.exit(-1)

    except MemoryError:
        logs.print_error("recovery", "oom event")
        mem_info(1)
        sys.exit(-2)