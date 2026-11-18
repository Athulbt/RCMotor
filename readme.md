# RCMotor

A Raspberry Pi RC car controlled with an Xbox controller. It drives a DC motor and a steering servo. It also records camera frames and logs every control input to CSV, so you can review a drive or build a dataset (for example, for self-driving experiments).

## Features

- **Proportional steering:** the left stick steers smoothly instead of only snapping left, straight or right.
- **Variable speed:** the triggers control speed with PWM, and the D-pad sets a fixed cruise speed.
- **Safe shutdown:** the motor always stops on quit, on a crash, on Ctrl+C or if the controller disconnects.
- **Session logs:** each drive is saved in its own folder, with a `controls.csv` and matching camera images.
- **Simulation mode:** `--sim` runs the script on a normal PC without GPIO hardware.

## Hardware

- Raspberry Pi (any model with GPIO pins)
- Servo motor for steering
- DC motor with a motor driver (e.g. DROK / L298N)
- Xbox controller (wired, or wireless with an adapter or Bluetooth)
- Raspberry Pi camera module or USB webcam (optional)

## Wiring (BCM numbering)

| Part          | Pin     |
|---------------|---------|
| Servo signal  | GPIO 17 |
| Motor IN1     | GPIO 24 |
| Motor IN2     | GPIO 25 |
| Motor ENA     | GPIO 23 |

Pins, servo positions and speeds are in the **Configuration** section at the top of `rc.py`.

## Install

```bash
pip3 install -r requirements.txt
```

## Run

```bash
python3 rc.py              # normal run
python3 rc.py --show       # with a live camera preview (needs a display)
python3 rc.py --no-camera  # without a camera
python3 rc.py --sim        # on a PC, with GPIO faked
```

Other options: `--camera N` picks a different camera, and `--data-dir PATH` changes where sessions are saved (default `~/rc_data`).

## Controls

| Input            | Action                          |
|------------------|---------------------------------|
| Left stick       | Steer left / right              |
| Right trigger    | Forward (speed = how far pressed) |
| Left trigger     | Backward (speed = how far pressed) |
| D-pad up         | Cruise forward                  |
| D-pad down       | Cruise backward                 |
| Y or LB          | Stop                            |
| A                | Quit and clean up GPIO          |

The triggers take priority over cruise while you hold them.

## Recorded data

```
~/rc_data/session_20261118_143000/
├── controls.csv
└── images/
    ├── img_00000.jpg
    └── ...
```

Each `controls.csv` row has: `timestamp, steer_x, steering, throttle, direction, image`.

## Tests

```bash
python3 -m unittest discover tests
```

The tests use the simulated GPIO, so they run on any computer.

## Tuning

If the car goes the wrong way, swap the `IN1_PIN` / `IN2_PIN` values. If the wheels don't sit straight, adjust `SERVO_DUTY_CENTER`, `SERVO_DUTY_LEFT` and `SERVO_DUTY_RIGHT`.
