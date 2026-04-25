from micropython import const
import logs

# REBOOT2BOOTLOADER:
R2B_RECOVERY_IMG = const(0)
R2B_UART = const(1)

def reboot_to_recovery():
    """
    Reboot the device to the recovery.img firm.
    """
    from machine import deepsleep, RTC
    RTC().memory(R2B_RECOVERY_IMG.to_bytes(1))
    logs.print_warning("boot", "rebooting to recovery.img")

    deepsleep(1)

def reboot_to_uart():
    """
    Reboot the device to uart boot.
    """
    from machine import deepsleep, RTC
    RTC().memory(R2B_UART.to_bytes(1))
    logs.print_warning("boot", "rebooting to uart download boot")

    deepsleep(1)