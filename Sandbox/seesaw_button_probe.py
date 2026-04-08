import time
import board
import busio
from adafruit_seesaw import seesaw, digitalio

ADDR = 0x49

# Probe a reasonable range of seesaw GPIO pins.
PINS = list(range(0, 32))

i2c = busio.I2C(board.SCL, board.SDA)
ss = seesaw.Seesaw(i2c, addr=ADDR)

buttons = {}
for pin in PINS:
    try:
        btn = digitalio.DigitalIO(ss, pin)
        btn.switch_to_input(pull=True)
        buttons[pin] = btn
    except Exception:
        pass

print("Watching pins:", sorted(buttons.keys()))
last = {pin: bool(btn.value) for pin, btn in buttons.items()}

while True:
    for pin, btn in buttons.items():
        try:
            val = bool(btn.value)
            if val != last[pin]:
                print(f"pin {pin} -> {'HIGH' if val else 'LOW'}")
                last[pin] = val
        except Exception:
            pass
    time.sleep(0.02)
