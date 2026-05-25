from hal.peripherals import get_snooze
from hal.audio_beeper import play_tone
from window import Window
import xglcd_font
import _thread
import time

_WK_TO_STR = const(("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                    "Saturday", "Sunday"))
_MONTH_TO_STR = const(("January", "February", "March", "April", "May",
                       "June", "July", "August", "September", "October",
                       "November", "December"))
_DAY_SUFFIX = {1: "st", 2: "nd", 3: "rd"}

# TODO: Main clock screen (shows time in BIG LETTERS with date underneath) 
#   (with TIME / ALARM / SETTINGS row)
class Clock(Window):
    def __init__(self):
        # TODO: make font cache
        self.font = xglcd_font.XglcdFont("/firm/res/fonts/Bitstream_Vera35x32.c", 35, 32, 48, 11)
        self.small_font = xglcd_font.XglcdFont("/firm/res/fonts/Tiny3x5.c", 3, 5)
        self.refresh_settings()
        self._repaint = False

    def refresh_settings(self):
        self._last_minute = -1
        # TODO: Get 12/24 hr config
        self._12_hr = False

        # TODO: get time zone
        # TODO: get auto dst
        self.local_time = LocalTime(0, True)  # XXX: hard coded

        # TODO: refresh alarms list.
        self.alarms = []
        pass

    # TODO: clock applet handles alarms.
    def tick(self):
        _, m, d, hr, mn, _, wd, _ = self.local_time.get_local_time()

        # TODO: process alarms every second or so rather than every
        # 33 milliseconds....
        for alarm in self.alarms:
            alarm.tick((_, m, d, hr, mn, _, wd, _))

        # repaint if minute changed
        if mn != self._last_minute:
            self._repaint = True
            self._last_minute = mn

    def repaint(self, display) -> None:
        if not self._repaint:
            return
        
        _, m, d, hr, mn, _, wd, _ = self.local_time.get_local_time()
        print("repainting")

        # TODO: format 12/24 hour (later)
        # BUG: (lcd not cleared when repainting)
        d_time = f"{hr}:{mn:0>2}"
        d_date = f"{_WK_TO_STR[wd]}, {_MONTH_TO_STR[m - 1]} {d}{_DAY_SUFFIX.get(d % 10, "th")}"

        # TODO: draw date (small text)
        # TODO: draw options row/AM/PM

        # Draw time (AM/PM not yet supported)
        time_width = self.font.measure_text(d_time)
        display.draw_text((128 - time_width) // 2, 18, d_time, self.font)

        # Draw date line
        date_width = self.small_font.measure_text(d_date)
        display.draw_text((128 - date_width) // 2, 46, d_date, self.small_font)

        display.present()
        self._repaint = False

class Alarm():
    def __init__(self, time: tuple[int, ...], wkday: tuple | None):
        """
        Alarm time. Time parameter is a timestamp in the format hour, minute, month, 
        day. Unused fields should be set to -1, but hour and minute must always
        be used. If the weekday field is set, the month and day fields are ignored.
        """
        if wkday is not None:
            self.month = time[2]
            self.day = time[3]
            self.wkday = None
        else:
            self.month = -1
            self.day = -1
            self.wkday = wkday

        self.hour = time[0]
        self.minute = time[1]
        self.last_day_triggered = -1  # Prevent retriggering
        # TODO: Snooze functionality

    def _alarm_hit(self, curtime: tuple[int, ...]) -> bool:
        _, m, d, hr, mn, _, wd, _ = curtime

        hr_min_trigger = hr == self.hour and mn == self.minute

        # Path 1: weekday set
        if self.wkday is not None:
            return wd in self.wkday and hr_min_trigger
        
        # Path 2: month/day set
        if self.month != -1 and self.day != -1:
            return m == self.month and d == self.day and hr_min_trigger
        
        # path 3: just hour/min
        return hr_min_trigger
    
    def tick(self, curtime: tuple[int, ...]) -> None:
        cur_day = curtime[2]

        if self.last_day_triggered == cur_day:
            return
        
        # TODO: ALARM THREAD
        if self._alarm_hit(curtime):
            print("alarm triggered")
            self.last_day_triggered = cur_day
            _thread.start_new_thread(_alarm_thread, (self, 1.))

# Time is stored in the RTC as UTC. This makes time sync and DST
# calibration easier. However, localtime conversion must be done on the
# fly (as well as DST adjustments). This class handles that functionality.
class LocalTime():
    # DST RULES:
    # Start: Second Sunday in March.
    # End: First Sunday in November.
    def __init__(self, utc_offset: int, auto_dst_adjust: bool):
        self.utc_offset = utc_offset
        self.auto_dst = auto_dst_adjust

    def _get_dst_offset(self) -> int:
        if not self.auto_dst:
            return 0  # Never do DST
        
        _, m, d, h, _, _, _, _ = self.get_local_time(dst=False)

        # DST START:
        # month >= 3 and month_day >= 8 and h >= 2
        # DST END:
        # month >= 11 and month_day <= 7 and h < 2
        # TODO: can probably condense into one conditional
        if m >= 3 and m <= 11: # DST MONTH RANGE
            # DST_START
            if m == 3 and d >= 8 and h >= 2:
                return 1
            
            # DST_END
            elif m == 11 and d <= 7 and h < 2:
                return 1
            
            # DST
            elif m > 3 and m < 11:
                return 1
            
        return 0
    
    def get_local_time(self, dst=True) -> tuple[int, ...]:
        """
        Get the current local time. By default, it performs the DST
        offset math. This function is also used internally to determine
        whether DST should be accounted for (dst=False)
        """
        time_utc_s = time.mktime(time.localtime())
        offset_h = self.utc_offset
        
        if dst:
            offset_h += self._get_dst_offset()

        # BUGFIX: Hours = 60 mins = 3600 seconds (had 60 seconds)
        return time.localtime(time_utc_s + offset_h * 3600)
    
def _alarm_thread(self: Alarm, volume: float):
    print("entered alarm thread")

    while True:        
        for _ in range(4):
            if get_snooze():
                return

            play_tone(1200, 90, volume)
            time.sleep_ms(35)

        time.sleep_ms(400)