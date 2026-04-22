from esp import osdebug, LOG_INFO
from micropython import const
from hal import peripherals
import recovery_utils
import requests
import logs
import sys

_CHUNK_SIZE = const(32768)
_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'}

# Find the raw download urls for the firm components.
# TODO: even though HTTPS downloads are occurring, artifact hashes should be checked
# with the ones provided by github
def get_artifact_urls(latest_release_url: str) -> tuple[str, str]:
    release_data = requests.get(latest_release_url, headers=_HEADERS)

    if release_data.status_code != 200:
        raise OSError(f"download failure (code {release_data.status_code})")

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
            out[artifact_name] = artifact["browser_download_url"]

        # TODO: read the artifact["digest"] field for the hash

    if len(out) != 2:
        logs.print_error("recovery", "unable to locate one or more firm urls")
        raise RuntimeError("unable to find firm urls")
    
    return out["clock_firm.img"], out["clock_firm.img.sig"]

# Download the entire requested firm contents from GitHub's upstream servers. 
#
# TODO: hash checks should be done in here (we're iterating over
# the entire file contents anyways).
def download_artifact(artifact_url: str, install_path: str) -> None:
    firm_bin_res = requests.get(artifact_url, headers=_HEADERS)

    if firm_bin_res.status_code != 200:
        raise OSError(f"download failure (code {firm_bin_res.status_code})")
    
    buf = memoryview(bytearray(_CHUNK_SIZE))
    f = open(install_path, "wb")
    
    while True:
        sz = firm_bin_res.raw.readinto(buf)

        if sz < _CHUNK_SIZE:
            f.write(buf[:sz])
            break

        f.write(buf)

    firm_bin_res.close()
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
    osdebug(LOG_INFO)
    
    # Need network selection menu
    if not peripherals.NIC.link_is_up():
        peripherals.FBCON.write_line("w: no access point in range")
        #peripherals.FBCON.set_hidden(True)
        logs.print_error("recovery", "wifi menu not implemented; necessary to continue")

        while not peripherals.NIC.link_is_up():
            pass
        # Attempt reconnection (again)

    try:
        # TODO: Move this code into an updater library
        peripherals.FBCON.write_line("i: locating firmware files")
        firm_url, firm_sig_url = get_artifact_urls("https://api.github.com/repos/rsc-games/esp32-alarm-clock/releases/latest")
        
        # Download firm files
        peripherals.FBCON.write_line("i: downloading firm/sig")
        download_artifact(firm_sig_url, "/clock_firm.img.sig.tmp")
        download_artifact(firm_url, "/clock_firm.img.tmp")

        # Install the firm files (unique path to avoid installing corrupt data
        # as the firmware). This does run the risk of leaving firmware files on disk
        # that are never used, but the main firmware can handle that.
        peripherals.FBCON.write_line("i: installing firmware")
        recovery_utils.install_new_firmware_local(".tmp")
        peripherals.FBCON.write_line("i: install complete. rebooting")
        sys.exit(0)

    except (OSError, RuntimeError) as ie:
        peripherals.FBCON.write_line("e: firmware download failure")
        logs.print_error("recovery", "unable to download firmware files")
        sys.print_exception(ie)

        while True:
            pass
        sys.exit(-1)