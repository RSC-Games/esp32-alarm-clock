from typing import TypeAlias

from hal.drivers.blob_ulp_sampled import *
from esp32 import ULP
import micropython
import time

_RTC_BUFFER_SIZE = const(2920)
_RTC_BUFFER_SLICE_WIDTH = const(_RTC_BUFFER_SIZE // 8)
_RTC_FAST_CLK_HZ = const(8_075_000)  # TODO: RTC_FAST is 8 MHz on ESP32??? Will need runtime calibration....
_RTCIO_PAD_DAC1_REG = const(0x484)
_TICK_MICROS_MUL = const(1_000_000)

_ULP_INSTR_REG_WR_TEMPLATE = const(0x1 << 28 | 26 << 23 | 19 << 18 | _RTCIO_PAD_DAC1_REG // 4)
_ULP_INSTR_REG_WR_DATA_OFFSET = const(10) 
_ULP_INSTR_WAIT_TEMPLATE = const(4 << 28)
_ULP_CLKS_WRITE_DELAY = const(14)  # 8 cycles reg_wr + 6 cycles overhead for wait 

# Linting purposes
ptr32: TypeAlias = memoryview
ptr8: TypeAlias = memoryview
uint: TypeAlias = int

class Beeper:
    def __init__(self):
        """
        Beeper should only be initialized within this file.
        """

    def initialize(self, tone_freq: int, pulse_dur_ms: int, volume: float) -> None:
        """
        Initialize beeper engine and prepare for playback. The beeper internally
        uses the same hardware engines as the audio playback system, so when this
        engine is being used the sampled audio engine MUST NOT BE USED!
        """
        # Buffer only needs to be filled once (other half intentionally traps)

        # Nyquist sampling rate adjustment (must sample twice the requested frequency)
        tone_freq *= 2 

        # Driver only currently supports 1 channel 8 bit audio
        # Will add support for resampling later.
        sample_us_delta = _TICK_MICROS_MUL // tone_freq
        sample_cycles_delta = _RTC_FAST_CLK_HZ // tone_freq - _ULP_CLKS_WRITE_DELAY
        num_samples = round((pulse_dur_ms * 1000) / sample_us_delta)
        self._ulp = ULP()

        # TODO: should use a different ULP binary for this one.
        print(f"playing freq of {tone_freq} for {pulse_dur_ms} ms sample ct {num_samples}")

        self._ulp.load_binary(0, rebuild_ulp_binary())
        print(f"sample dt {sample_cycles_delta} cycles {sample_us_delta} us")

        # Buffer gen/write and trap buffer
        high_samp = round(255 * volume)
        _jit_gen_frequency(ULP_BASE + ULP_SAMPLE_ARRAY0, high_samp, self._num_samples, self._sample_cycles_delta)  # type: ignore
        _jit_inject_halts(ULP_BASE + ULP_SAMPLE_ARRAY1)  # type: ignore

    def play(self) -> None:
        """
        Run the beeper. Must be externally cancelled.
        """
        self._ulp.run(ULP_ENTRY)

def play_tone(freq: int, dur_ms: int, vol: float) -> None:
    """
    Play a frequency for a given amount of time. While the tone playing
    is done by the ULP, this function blocks until tone playback is finished.

    :param freq: Frequency to play
    :param dur_ms: Duration of the frequency (in ms)
    :param vol: Volume of the beep
    """
    SINGLETON_BEEPER.initialize(freq, dur_ms, vol)
    SINGLETON_BEEPER.play()
    time.sleep_ms(dur_ms)

@micropython.viper
def _jit_gen_frequency(dest: ptr32, high_samp: int, len: int, delta_cycles: int):
    """
    Generate the frequency buffer samples for the lower buffer.

    :param dest: Destination buffer
    :param high_samp: High sample (pre volume adjusted)
    :param len: Sample count to write
    :param delta_cycles: Cycles between each buffer write.
    """

    if len > _RTC_BUFFER_SLICE_WIDTH:
        raise IndexError(f"{len} > {_RTC_BUFFER_SLICE_WIDTH}")

    for rtc_addr in range(0, len * 2, 2):
        sample: int = high_samp if rtc_addr % 4 == 0 else 0

        dest[rtc_addr] = (_ULP_INSTR_REG_WR_TEMPLATE | (sample << _ULP_INSTR_REG_WR_DATA_OFFSET))
        dest[rtc_addr + 1] = uint(_ULP_INSTR_WAIT_TEMPLATE) | delta_cycles

@micropython.viper
def _jit_inject_halts(dest: ptr32):
    """
    """
    for rtc_addr in range(_RTC_BUFFER_SLICE_WIDTH * 2):
        dest[rtc_addr] = 0

SINGLETON_BEEPER = Beeper()