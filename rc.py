"""
RC car controller for Raspberry Pi.

Drives a DC motor (through an L298N/DROK-style H-bridge) and a steering servo
from an Xbox controller, records camera frames and logs every control input
to CSV so each session can be replayed or used as a training dataset.

Run on the Pi:            python3 rc.py
Without a camera:         python3 rc.py --no-camera
With a live preview:      python3 rc.py --show
On a PC (no Pi hardware): python3 rc.py --sim
"""

import argparse
import csv
import datetime
import os
import sys
import time

# ---------------------------------------------------------------------------
# Configuration — change these to match your wiring and servo
# ---------------------------------------------------------------------------
SERVO_PIN = 17          # steering servo signal
IN1_PIN = 24            # motor driver IN1
IN2_PIN = 25            # motor driver IN2
ENA_PIN = 23            # motor driver ENA (speed, driven with PWM)

SERVO_FREQ_HZ = 50
MOTOR_PWM_FREQ_HZ = 1000

# Servo duty cycles (%) measured on the original car
SERVO_DUTY_RIGHT = 8.0
SERVO_DUTY_CENTER = 9.0
SERVO_DUTY_LEFT = 10.5
SERVO_HOLD_SECONDS = 0.15   # pulse length before the signal is released (stops jitter)
SERVO_MIN_CHANGE = 0.1      # ignore duty changes smaller than this

STEER_DEADZONE = 0.10       # joystick values inside this are "straight"
TRIGGER_DEADZONE = 0.05
CRUISE_SPEED = 1.0          # speed (0-1) used by the D-pad forward/backward

LOG_INTERVAL_SECONDS = 1.0  # how often a row + image are saved
LOOP_DELAY_SECONDS = 0.02   # main loop period (~50 Hz)
DATA_DIR = os.path.join(os.path.expanduser("~"), "rc_data")


# ---------------------------------------------------------------------------
# Pure helpers (no hardware, easy to test)
# ---------------------------------------------------------------------------
def clamp(value, low, high):
    return max(low, min(high, value))


def steering_duty(x, deadzone=STEER_DEADZONE):
    """Map joystick x (-1 = full left, 1 = full right) to a servo duty cycle."""
    x = clamp(x, -1.0, 1.0)
    if abs(x) < deadzone:
        return SERVO_DUTY_CENTER
    # rescale so steering starts smoothly at the edge of the dead zone
    amount = (abs(x) - deadzone) / (1.0 - deadzone)
    if x > 0:
        return SERVO_DUTY_CENTER + amount * (SERVO_DUTY_RIGHT - SERVO_DUTY_CENTER)
    return SERVO_DUTY_CENTER + amount * (SERVO_DUTY_LEFT - SERVO_DUTY_CENTER)


def steering_label(x, deadzone=STEER_DEADZONE):
    if x >= deadzone:
        return "right"
    if x <= -deadzone:
        return "left"
    return "straight"


def throttle_from_inputs(forward_trigger, reverse_trigger, cruise):
    """
    Combine triggers and D-pad cruise into one throttle value in [-1, 1].
    Triggers override cruise while held; positive = forward.
    """
    forward_trigger = clamp(forward_trigger, 0.0, 1.0)
    reverse_trigger = clamp(reverse_trigger, 0.0, 1.0)
    if forward_trigger > TRIGGER_DEADZONE or reverse_trigger > TRIGGER_DEADZONE:
        return forward_trigger - reverse_trigger
    return clamp(cruise, -1.0, 1.0)


def direction_label(throttle):
    if throttle > 0:
        return "forward"
    if throttle < 0:
        return "backward"
    return "stopped"


# ---------------------------------------------------------------------------
# Hardware
# ---------------------------------------------------------------------------
class FakeGPIO:
    """Stand-in for RPi.GPIO so the script can run on a normal computer."""

    BCM = OUT = "x"
    LOW, HIGH = 0, 1

    class _PWM:
        def __init__(self, pin, freq):
            self.pin = pin

        def start(self, duty):
            pass

        def ChangeDutyCycle(self, duty):
            pass

        def stop(self):
            pass

    def setmode(self, mode):
        pass

    def setwarnings(self, flag):
        pass

    def setup(self, pin, mode):
        pass

    def output(self, pin, value):
        pass

    def PWM(self, pin, freq):
        return self._PWM(pin, freq)

    def cleanup(self):
        print("[sim] GPIO cleaned up")


def load_gpio(simulate):
    if simulate:
        return FakeGPIO()
    try:
        import RPi.GPIO as GPIO
        return GPIO
    except (ImportError, RuntimeError):
        print("RPi.GPIO not available - run with --sim to test without a Pi.")
        sys.exit(1)


class Car:
    def __init__(self, gpio):
        self.gpio = gpio
        gpio.setmode(gpio.BCM)
        gpio.setwarnings(False)
        for pin in (IN1_PIN, IN2_PIN, ENA_PIN, SERVO_PIN):
            gpio.setup(pin, gpio.OUT)

        self.motor_pwm = gpio.PWM(ENA_PIN, MOTOR_PWM_FREQ_HZ)
        self.motor_pwm.start(0)
        self.servo = gpio.PWM(SERVO_PIN, SERVO_FREQ_HZ)
        self.servo.start(0)

        self.throttle = 0.0
        self.servo_duty = None
        self.servo_release_at = 0.0
        self.stop()
        self.steer_duty(SERVO_DUTY_CENTER)

    def drive(self, throttle):
        """throttle in [-1, 1]; sign = direction, magnitude = speed."""
        throttle = clamp(throttle, -1.0, 1.0)
        g = self.gpio
        if throttle > 0:
            g.output(IN1_PIN, g.LOW)
            g.output(IN2_PIN, g.HIGH)
        elif throttle < 0:
            g.output(IN1_PIN, g.HIGH)
            g.output(IN2_PIN, g.LOW)
        else:
            g.output(IN1_PIN, g.LOW)
            g.output(IN2_PIN, g.LOW)
        self.motor_pwm.ChangeDutyCycle(abs(throttle) * 100)
        self.throttle = throttle

    def stop(self):
        self.drive(0)

    def steer_duty(self, duty):
        """Move the servo only when the target changes, then release the signal."""
        now = time.monotonic()
        if self.servo_duty is None or abs(duty - self.servo_duty) >= SERVO_MIN_CHANGE:
            self.servo.ChangeDutyCycle(duty)
            self.servo_duty = duty
            self.servo_release_at = now + SERVO_HOLD_SECONDS
        elif self.servo_release_at and now >= self.servo_release_at:
            self.servo.ChangeDutyCycle(0)
            self.servo_release_at = 0.0

    def cleanup(self):
        try:
            self.stop()
            self.motor_pwm.stop()
            self.servo.stop()
        finally:
            self.gpio.cleanup()


# ---------------------------------------------------------------------------
# Camera and logging
# ---------------------------------------------------------------------------
class Camera:
    def __init__(self, index, show):
        import cv2
        self.cv2 = cv2
        self.show = show
        self.cap = cv2.VideoCapture(index)
        if not self.cap.isOpened():
            raise RuntimeError("Could not open camera %d" % index)

    def read(self):
        ok, frame = self.cap.read()
        if not ok:
            return None
        if self.show:
            self.cv2.imshow("RC camera", frame)
            self.cv2.waitKey(1)
        return frame

    def save(self, frame, path):
        return self.cv2.imwrite(path, frame)

    def close(self):
        self.cap.release()
        if self.show:
            self.cv2.destroyAllWindows()


class SessionLog:
    FIELDS = ["timestamp", "steer_x", "steering", "throttle", "direction", "image"]

    def __init__(self, root):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.folder = os.path.join(root, "session_" + stamp)
        self.image_folder = os.path.join(self.folder, "images")
        os.makedirs(self.image_folder, exist_ok=True)
        self.file = open(os.path.join(self.folder, "controls.csv"), "w", newline="")
        self.writer = csv.DictWriter(self.file, fieldnames=self.FIELDS)
        self.writer.writeheader()
        self.rows = 0

    def write(self, steer_x, throttle, image_name=""):
        self.writer.writerow({
            "timestamp": datetime.datetime.now().isoformat(timespec="milliseconds"),
            "steer_x": round(steer_x, 3),
            "steering": steering_label(steer_x),
            "throttle": round(throttle, 3),
            "direction": direction_label(throttle),
            "image": image_name,
        })
        self.file.flush()
        self.rows += 1

    def close(self):
        self.file.close()


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def run(args):
    from approxeng.input.selectbinder import ControllerResource

    car = Car(load_gpio(args.sim))
    camera = None
    log = None
    try:
        if not args.no_camera:
            try:
                camera = Camera(args.camera, args.show)
            except Exception as error:
                print("Camera disabled:", error)

        log = SessionLog(args.data_dir)
        print("Logging to", log.folder)

        cruise = 0.0
        next_log = time.monotonic()

        print("Waiting for controller...")
        with ControllerResource() as joystick:
            print("Controller connected")
            while joystick.connected:
                presses = joystick.check_presses()

                if presses["cross"]:            # A: quit
                    print("Quit pressed")
                    break
                if presses["dup"]:              # D-pad up: cruise forward
                    cruise = CRUISE_SPEED
                if presses["ddown"]:            # D-pad down: cruise backward
                    cruise = -CRUISE_SPEED
                if presses["triangle"] or presses["l1"]:   # Y or LB: stop
                    cruise = 0.0

                steer_x = joystick["lx"]
                throttle = throttle_from_inputs(joystick["rt"], joystick["lt"], cruise)

                car.drive(throttle)
                car.steer_duty(steering_duty(steer_x))

                frame = camera.read() if camera else None

                now = time.monotonic()
                if now >= next_log:
                    next_log = now + LOG_INTERVAL_SECONDS
                    image_name = ""
                    if frame is not None:
                        image_name = "img_%05d.jpg" % log.rows
                        if not camera.save(frame, os.path.join(log.image_folder, image_name)):
                            image_name = ""
                    log.write(steer_x, throttle, image_name)

                time.sleep(LOOP_DELAY_SECONDS)
            else:
                print("Controller disconnected")
    except IOError:
        print("No controller found - pair the Xbox controller and try again.")
    except KeyboardInterrupt:
        print("Stopped with Ctrl+C")
    finally:
        # always stop the motor, even after a crash or disconnect
        car.cleanup()
        if camera:
            camera.close()
        if log:
            log.close()
            print("Saved %d log rows to %s" % (log.rows, log.folder))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Raspberry Pi RC car controller")
    parser.add_argument("--no-camera", action="store_true", help="run without a camera")
    parser.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    parser.add_argument("--show", action="store_true", help="show a live camera preview window")
    parser.add_argument("--sim", action="store_true", help="fake the GPIO pins (run on a PC)")
    parser.add_argument("--data-dir", default=DATA_DIR, help="where sessions are saved")
    return parser.parse_args(argv)


if __name__ == "__main__":
    run(parse_args())
