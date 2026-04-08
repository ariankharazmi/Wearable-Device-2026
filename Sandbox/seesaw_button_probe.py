import time
import board
import busio
from adafruit_seesaw import seesaw, digitalio

ADDR = 0x49

# Narrowed to likely candidates first.
PINS = [5, 15, 16, 24]

i2c = busio.I2C(board.SCL, board.SDA)
ss = seesaw.Seesaw(i2c, addr=ADDR)

buttons = {}
for pin in PINS:
    try:
        btn = digitalio.DigitalIO(ss, pin)
        btn.switch_to_input(pull=True)
        buttons[pin] = btn
    except Exception as exc:
        print(f"pin {pin}: unavailable ({exc})")

print("Watching pins:", sorted(buttons.keys()))
print("Press one button at a time: center, up, down, left, right.")
print("Press Ctrl+C to stop.\n")

last = {pin: bool(btn.value) for pin, btn in buttons.items()}
last_change = {pin: 0.0 for pin in buttons}

try:
    while True:
        now = time.perf_counter()
        for pin, btn in buttons.items():
            try:
                val = bool(btn.value)
            except Exception:
                continue

            # Simple debounce so chatter is easier to read.
            if val != last[pin] and (now - last_change[pin]) > 0.12:
                state = "HIGH" if val else "LOW"
                print(f"{time.strftime('%H:%M:%S')}  pin {pin} -> {state}")
                last[pin] = val
                last_change[pin] = now

        time.sleep(0.10)
except KeyboardInterrupt:
    print("\nStopped.")
