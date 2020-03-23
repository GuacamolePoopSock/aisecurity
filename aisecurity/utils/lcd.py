"""

"aisecurity.hardware.lcd"

LCD utils.

"""

import concurrent.futures
import functools
import time
import warnings

from keras import backend as K
from termcolor import cprint
import requests

from aisecurity.db.log import THRESHOLDS
from aisecurity.utils.paths import CONFIG


################################ INITS ################################

# AUTOINIT
COLORS = None
LCD_DEVICE, PROGRESS_BAR, GPIO = None, None, None

try:
    from adafruit_character_lcd.character_lcd_i2c import Character_LCD_I2C as character_lcd
    import board
    import busio
except (NotImplementedError, ModuleNotFoundError, ValueError):
    # ValueError- a different mode has already been set
    warnings.warn("LCD not found")

try:
    I2C = busio.I2C(board.SCL, board.SDA)
    I2C.scan()
except (RuntimeError, NameError) as error:
    if isinstance(error, RuntimeError):
        raise RuntimeError("Wire configuration incorrect")
    elif isinstance(error, NameError):
        warnings.warn("i2c not found")

try:
    import Jetson.GPIO as GPIO
    GPIO.cleanup()
    GPIO.setmode(GPIO.BCM)
    try:
        COLORS = [18, 23]
        for color in COLORS:
            GPIO.setup(color, GPIO.OUT)
    except RuntimeError:
        warnings.warn("Improper wire configuration")
except (ImportError, RuntimeError) as e:
    if isinstance(e, ImportError):
        warnings.warn("Jetson.GPIO not found")
    elif isinstance(e, RuntimeError):
        warnings.warn("/dev/ cannot be accessed: use sudo")


# LCD INIT
def init():
    global LCD_DEVICE, PROGRESS_BAR

    LCD_DEVICE = LCD()
    LCD_DEVICE.set_message("Loading...\n[Initializing]")

    PROGRESS_BAR = LCDProgressBar(total=THRESHOLDS["num_recognized"], lcd=LCD_DEVICE)


################################ CLASSES ################################

# LCD WRAPPER CLASS (WITH DEV SUPPORT)
class LCD:

    def __init__(self, mode="physical"):
        assert mode in ("physical", "dev"), "supported modes are physical (physical LCD) and dev (testing)"
        self._lcd = None

        try:
            self._lcd = character_lcd(I2C, 16, 2, backlight_inverted=False)
            self.mode = "physical"
            assert self.mode == mode  # making sure that physical doesn't override user choice
        except (ValueError, NameError, AssertionError):
            self._lcd = LCDSimulation()
            self.mode = "dev"

            if self.mode != mode:
                warnings.warn("physical lcd mode requested but only dev lcd available")
            warnings.warn("dev lcd does not support colors")


    # FUNCTIONALITY
    def set_message(self, message, backlight="white"):

        # TODO: get correct colors
        def green_display():
            GPIO.output(COLORS[0], GPIO.HIGH)
            GPIO.output(COLORS[1], GPIO.HIGH)

        def red_display():
            GPIO.output(COLORS[0], GPIO.LOW)
            GPIO.output(COLORS[1], GPIO.LOW)

        def violet_display():
            GPIO.output(COLORS[0], GPIO.LOW)
            GPIO.output(COLORS[1], GPIO.HIGH)

        def white_display():
            GPIO.output(COLORS[0], GPIO.HIGH)
            GPIO.output(COLORS[1], GPIO.LOW)

        display_dict = {
            "green": green_display,
            "red": red_display,
            "violet": violet_display,
            "white": white_display
        }

        assert backlight in display_dict.keys(), "backlight must be green, red, violet, or white"

        self._lcd.message = message

        if self.mode == "physical":
            # set backlight if supported
            display_dict[backlight]()

    def clear(self):
        self._lcd.clear()


    # RETRIEVERS
    @property
    def lcd(self):
        return self._lcd

    @property
    def message(self):
        return self._lcd.message


# SIMULATION SUPPORT FOR DEV
class LCDSimulation:

    def __init__(self):
        self.message = None

    def __setattr__(self, key, value):
        if key == "message" and value:
            cprint(value, attrs=["bold"])
        super(LCDSimulation, self).__setattr__(key, value)

    def clear(self):
        self.message = "<Message cleared>"


# LCD PROGRESS BAR
class LCDProgressBar:

    def __init__(self, total, lcd, length=16, marker="#"):
        self.total = total
        self.lcd = lcd
        self.bar_length = length - 2  # compensate for [] at beginning and end
        self.marker = marker
        self.progress = 0

    def reset(self, previous_msg=None):
        self.progress = 0.
        if previous_msg:
            self.lcd.set_message("{}\n[{}]".format(previous_msg, " " * self.bar_length))

    def _update(self, percent, previous_msg=None):
        self.progress += percent

        if self.progress >= 1.:
            self.progress = 1.

        done = self.marker * round(self.progress * self.bar_length)
        left = " " * (self.bar_length - len(done))

        if previous_msg:
            self.lcd.set_message("{}\n[{}{}]".format(previous_msg, done, left))
        else:
            self.lcd.set_message("[{}{}]".format(done, left))

    def update(self, amt=1, previous_msg=None):
        if amt > self.total:
            amt = self.total
        elif amt < 0:
            raise ValueError("amt cannot be negative")
        self._update(amt / self.total, previous_msg)


################################ FUNCTIONS AND DECORATORS ################################

# RESET
def reset():
    global LCD_DEVICE, PROGRESS_BAR

    PROGRESS_BAR.reset()
    LCD_DEVICE.clear()


# ADD DISPLAY
def on_recognized(best_match, use_server):
    global LCD_DEVICE, PROGRESS_BAR

    if LCD_DEVICE and PROGRESS_BAR:
        reset()

        best_match = best_match.replace("_", " ").title()

        if use_server:
            request = requests.get(CONFIG["server_address"])
            data = request.json()

            if data["accept"]:
                LCD_DEVICE.set_message("ID Accepted\n{}".format(best_match), backlight="green")
            elif "visitor" in best_match.lower():
                LCD_DEVICE.set_message("Welcome to MHS,\n{}".format(best_match), backlight="violet")
            else:
                LCD_DEVICE.set_message("No Senior Priv\n{}".format(best_match), backlight="red")

        else:
            if "visitor" in best_match.lower():
                LCD_DEVICE.set_message("Welcome to MHS,\n{}".format(best_match), backlight="violet")
            else:
                LCD_DEVICE.set_message("[Server Error]\n{}".format(best_match), backlight="green")


# PROGRESS BAR DECORATOR
def progress_bar(lcd, expected_time, msg=None, marker="#", sess=None):

    def _progress_bar(func):

        def timed_progress_bar(future, expected_time, marker="#", previous_msg=None):
            # complete early if future completes; wait for future if it doesn't complete in expected_time
            pbar = LCDProgressBar(total=expected_time, lcd=lcd, marker=marker)

            for sec in range(expected_time - 1):
                if future.done():
                    pbar.update(expected_time - sec, previous_msg=previous_msg)
                    return
                else:
                    time.sleep(1)
                    pbar.update(previous_msg=previous_msg)

            future.result()
            pbar.update(previous_msg=previous_msg)

        @functools.wraps(func)
        def _func(*args, **kwargs):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                if sess:
                    K.set_session(sess)
                future = pool.submit(func, *args, **kwargs)
                timed_progress_bar(future, expected_time, marker, msg)

            return future.result()

        return _func

    return _progress_bar