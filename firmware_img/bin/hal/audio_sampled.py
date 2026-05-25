from typing import TypeAlias

from hal.drivers.blob_ulp_sampled import *
from machine import Timer, mem8
from esp32 import ULP
import micropython
import wav_file
import _thread
import asyncio
import time

_DEF_RAM_BUFFER_MULT = const(96)
_RTC_BUFFER_SIZE = const(2920)
_RTC_BUFFER_SLICE_WIDTH = const(_RTC_BUFFER_SIZE // 8)
_RTC_FAST_CLK_HZ = const(8_075_000)  # TODO: RTC_FAST is 8 MHz on ESP32??? Will need runtime calibration....
_RTCIO_PAD_DAC1_REG = const(0x484)

_ULP_INSTR_REG_WR_TEMPLATE = const(0x1 << 28 | 26 << 23 | 19 << 18 | _RTCIO_PAD_DAC1_REG // 4)
_ULP_INSTR_REG_WR_DATA_OFFSET = const(10) 
_ULP_INSTR_WAIT_TEMPLATE = const(4 << 28)
_ULP_CLKS_WRITE_DELAY = const(14)  # 8 cycles reg_wr + 6 cycles overhead for wait 

# Linting purposes
ptr32: TypeAlias = memoryview
ptr8: TypeAlias = memoryview
uint: TypeAlias = int

# TODO: New audio driver (uses the standard I2S driver and then
# does register magic to point it at the internal DACs)
class AudioPlayer:
    def __init__(self):
        """
        DO NOT INSTANTIATE THIS CLASS OUTSIDE OF THIS FILE OR THERE WILL
        BE DRAGONS!!!!
        """

        self.volume = 1
        pass

    def set_volume(self, volume: float) -> None:
        """
        Set the output volume.
        NOTE: Volume changes are applied the next time the sample buffer is
        refilled. In the new driver volume changes will be applied at 
        the small buffer write time.

        :param volume: New volume (can be greater than 1 at the risk of clipping)
        """
        self.volume = volume

    def initialize(self, wave_file: str, ram_buffer_mult: int) -> None:
        """
        Initialize the audio engine and prepare it for playback. The audio engine
        exclusively acquires system resources that cannot be shared.
        The audio engine can only handle playing one file at a time.

        :param wave_file: Path to the file to play.
        :param ram_buffer_mult: RAM buffer multiplier (must be an even multiple of the
            ULP buffer size)
        """
        self._audio_f = wav_file.WaveReader(wave_file)

        # NOTE: resampling can be done offline by the application
        channels = self._audio_f.num_channels
        sample_sz = self._audio_f.frame_width
        framerate = self._audio_f.framerate
        frame_cnt = self._audio_f.frame_cnt

        # Driver only currently supports 1 channel 8 bit audio
        # Will add support for resampling later.

        print(f"channels {channels} sample_sz {sample_sz}B/s framerate {framerate} frame_cnt {frame_cnt}")

        self._ulp_buffer_mult = ram_buffer_mult
        self._sample_buffer_size = self._ulp_buffer_mult * _RTC_BUFFER_SLICE_WIDTH
        self._sample_buffer_split = self._sample_buffer_size // 2

        self._sample_buffer = memoryview(bytearray(self._sample_buffer_size))
        self._sample_buffer_lower = self._sample_buffer[:self._sample_buffer_split]
        self._sample_buffer_upper = self._sample_buffer[self._sample_buffer_split:]

        self._sample_buffer_idx = self._sample_buffer_size - 1  # So ISR will refill it
        self._sample_cycles_delta = _RTC_FAST_CLK_HZ // framerate - _ULP_CLKS_WRITE_DELAY
        self._ulp = ULP()

        self._ulp.load_binary(0, rebuild_ulp_binary())
        print(f"sample dt {self._sample_cycles_delta} cycles {self._sample_cycles_delta // 8} us")

        # Zero both buffers (really just DAC writes with a zero argument)
        _zero_sample_buf(ULP_BASE + ULP_SAMPLE_ARRAY0, _RTC_BUFFER_SLICE_WIDTH, 65535)  # type: ignore
        _zero_sample_buf(ULP_BASE + ULP_SAMPLE_ARRAY1, _RTC_BUFFER_SLICE_WIDTH, 65535)  # type: ignore
        self._last_ulp_buf_filled = 1
        self._last_ulp_buf = 1
        self._last_sample_half_filled = 1

    def play(self) -> None:
        """
        Start playing a song. Assumes the audio engine has been pre-initialized with a
        previous initialize() call.
        """

        self._audio_f.seek(0)
        self._isr_pump = Timer(0)

        # 2x required rate to minimize missed refills
        refill_rate_hz = round((self._audio_f.framerate * 2) / _RTC_BUFFER_SLICE_WIDTH)
        self._read_thread = _thread.start_new_thread(self._buffer_fill_thread, ())
        self._isr_pump.init(mode=Timer.PERIODIC, freq=refill_rate_hz, callback=_pump_samples_isr)
        self._ulp.run(ULP_ENTRY)

    def stop(self):
        """

        """
        self._isr_pump.deinit()
        del self._audio_f
        kill_ulp()

    def _buffer_fill_thread(self):
        """
        """
        while True:
            buffer_half = int(self._sample_buffer_idx >= self._sample_buffer_split)
            buffer_to_fill = self._sample_buffer_lower if buffer_half == 1 else self._sample_buffer_upper

            if buffer_half != self._last_sample_half_filled:
                #t_start = time.ticks_ms()
                b_read = asyncio.run(self._audio_f.read_into(buffer_to_fill))
                #t_end = time.ticks_ms()
                #print(f"buf {buffer_half} refill {time.ticks_diff(t_end, t_start)} ms @ c_idx {c_idx}")

                if b_read == 0:
                    print("got eof; playback done")
                    self.stop()
                
                # yield
                time.sleep_ms(0)
                
                # Buffer audio adjust
                if self.volume != 1:
                    self._adjust_buffer_volume(buffer_to_fill)

                self._last_sample_half_filled = buffer_half

            time.sleep_ms(100)

    @micropython.native
    def _adjust_buffer_volume(self, buffer: memoryview[int]) -> None:
        """
        """
        for i in range(len(buffer)):
            new_sample = min(255, round(buffer[i] * self.volume))
            buffer[i] = new_sample

def play_oneshot(file_path: str) -> None:
    """
    """
    SINGLETON_AUDIO_PLAYER.initialize(file_path, _DEF_RAM_BUFFER_MULT)
    SINGLETON_AUDIO_PLAYER.play()

@micropython.viper
def _jit_sample_buf(dest: ptr32, src: ptr8, len: int, delta_cycles: int):
    """
    """
    rtc_word_len = (len - 1) * 2

    for rtc_addr in range(0, rtc_word_len, 2):
        sample_addr: int = rtc_addr >> 1
        sample = src[sample_addr]

        dest[rtc_addr] = (_ULP_INSTR_REG_WR_TEMPLATE | (sample << _ULP_INSTR_REG_WR_DATA_OFFSET))
        dest[rtc_addr + 1] = uint(_ULP_INSTR_WAIT_TEMPLATE) | delta_cycles

    # NOTE: Last sample in the array has extra wait cycles (due to branching logic)
    # Account for this in the final wait instruction.
    dest[rtc_word_len] = (_ULP_INSTR_REG_WR_TEMPLATE | (src[len - 1] << _ULP_INSTR_REG_WR_DATA_OFFSET))
    dest[rtc_word_len + 1] = uint(_ULP_INSTR_WAIT_TEMPLATE) | (delta_cycles - 25)

# Spray ULP coprocessor instruction memory with sleeping gas.
# Ideal for avoiding irritating noises on crashes/reboots.
def kill_ulp():
    """
    """
    self = SINGLETON_AUDIO_PLAYER

    if not hasattr(self, "_ulp"):
        return # Nothing to worry about
    
    _jit_inject_halts(ULP_BASE + ULP_SAMPLE_ARRAY0)  # type: ignore
    _jit_inject_halts(ULP_BASE + ULP_SAMPLE_ARRAY1)  # type: ignore

@micropython.viper
def _jit_inject_halts(dest: ptr32):
    """
    """
    for rtc_addr in range(_RTC_BUFFER_SLICE_WIDTH * 2):
        dest[rtc_addr] = 0

@micropython.viper
def _zero_sample_buf(dest: ptr32, len: int, delta_cycles: int):
    """
    """
    d_wr = (127 << _ULP_INSTR_REG_WR_DATA_OFFSET)

    for rtc_addr in range(0, len * 2, 2):
        dest[rtc_addr] = _ULP_INSTR_REG_WR_TEMPLATE | d_wr
        dest[rtc_addr + 1] = int(_ULP_INSTR_WAIT_TEMPLATE) | delta_cycles

# NOTE: Still rarely missing deadlines (potentially)
_last_call_us = 0

# MUST OCCUR AT LEAST 121 times a second!
# NOTE: weird repeat stretching keeps occuring even with extensive debugging in here.
# This function does not seem to be the problem, as the problem occurs even when
# the ULP is halted after every buffer write (meaning a buffer refill is required
# to restart the ULP; so deadline missing literally can't be causing this)
@micropython.native
def _pump_samples_isr(_: Timer):
    """
    """
    global _last_call_us

    self = SINGLETON_AUDIO_PLAYER

    # NOTE: DEBUGGING
    dt_ms = round(time.ticks_diff(time.ticks_us(), _last_call_us) / 1000)
    _last_call_us = time.ticks_us()

    if dt_ms > 8:
        print(f"\033[33mDEADLINE MISSED: dt_call {dt_ms}/8 ms\033[0m")
    
    # Determine back buffer
    idle_array = mem8[ULP_BASE + ULP_ACTIVE_ARRAY]

    if self._last_ulp_buf_filled != self._last_ulp_buf:
        print(f"\033[31mBUFFER UNDERRUN DETECTED!!! {self._last_ulp_buf} -> {idle_array} rf {self._last_ulp_buf_filled} \033[0m")
        self._last_ulp_buf_filled = self._last_ulp_buf

    # Came in before deadline; nothing to do.
    if idle_array == self._last_ulp_buf: # was ulp buf filled but uh... no.
        return
    
    self._last_ulp_buf = idle_array

    # If buffer swapped an underrun is basically guaranteed.
    test_new_idle = mem8[ULP_BASE + ULP_ACTIVE_ARRAY]
    array_offset = ULP_SAMPLE_ARRAY0 if idle_array == 0 else ULP_SAMPLE_ARRAY1
    
    # rare case (underrun handling)- force resync
    if idle_array != test_new_idle:
        print(f"\033[31mBUFFER SWAP OCCURRED DURING LOAD!!! {idle_array} -> {test_new_idle}\033[0m")
        print(f"force resync to {test_new_idle} (writing {idle_array})")

        # FORCE ULP RESYNC
        _jit_inject_halts(ULP_BASE + array_offset)  # type: ignore
        _jit_sample_buf(ULP_BASE + array_offset, self._sample_buffer[self._sample_buffer_idx:],  # type: ignore
                        _RTC_BUFFER_SLICE_WIDTH, self._sample_cycles_delta)
        self._ulp.run(ULP_BASE + array_offset)

    else:
        _jit_sample_buf(ULP_BASE + array_offset, self._sample_buffer[self._sample_buffer_idx:],  # type: ignore
                        _RTC_BUFFER_SLICE_WIDTH, self._sample_cycles_delta)
  
    self._sample_buffer_idx = (self._sample_buffer_idx + _RTC_BUFFER_SLICE_WIDTH) % (self._sample_buffer_size - _RTC_BUFFER_SLICE_WIDTH)
    self._last_ulp_buf_filled = idle_array


SINGLETON_AUDIO_PLAYER = AudioPlayer()