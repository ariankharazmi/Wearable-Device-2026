import time
import board
from adafruit_seesaw import digitalio, rotaryio, seesaw

i2c = board.I2C()
ss = seesaw.Seesaw(i2c, addr=0x49)

product = (ss.get_version() >> 16) & 0xFFFF
print("Found product", product)
if product != 5740:
    print("Wrong firmware loaded? Expected 5740")

for pin in (1, 2, 3, 4, 5):
    ss.pin_mode(pin, ss.INPUT_PULLUP)

select_btn = digitalio.DigitalIO(ss, 1)
up_btn = digitalio.DigitalIO(ss, 2)
left_btn = digitalio.DigitalIO(ss, 3)
down_btn = digitalio.DigitalIO(ss, 4)
right_btn = digitalio.DigitalIO(ss, 5)

encoder = rotaryio.IncrementalEncoder(ss)
last_pos = encoder.position
last = {
    "select": select_btn.value,
    "up": up_btn.value,
    "left": left_btn.value,
    "down": down_btn.value,
    "right": right_btn.value,
}

while True:
    pos = encoder.position
    if pos != last_pos:
        print("Position:", pos)
        last_pos = pos

    current = {
        "select": select_btn.value,
        "up": up_btn.value,
        "left": left_btn.value,
        "down": down_btn.value,
        "right": right_btn.value,
    }
    for name, val in current.items():
        if val != last[name]:
            print(name, "released" if val else "pressed")
            last[name] = val
    time.sleep(0.05)
