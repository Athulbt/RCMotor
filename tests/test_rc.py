import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rc  # noqa: E402


class SteeringTests(unittest.TestCase):
    def test_center_inside_deadzone(self):
        self.assertEqual(rc.steering_duty(0.0), rc.SERVO_DUTY_CENTER)
        self.assertEqual(rc.steering_duty(0.05), rc.SERVO_DUTY_CENTER)

    def test_full_lock(self):
        self.assertAlmostEqual(rc.steering_duty(1.0), rc.SERVO_DUTY_RIGHT)
        self.assertAlmostEqual(rc.steering_duty(-1.0), rc.SERVO_DUTY_LEFT)

    def test_out_of_range_is_clamped(self):
        self.assertAlmostEqual(rc.steering_duty(5.0), rc.SERVO_DUTY_RIGHT)

    def test_partial_is_between(self):
        duty = rc.steering_duty(0.5)
        self.assertTrue(rc.SERVO_DUTY_RIGHT < duty < rc.SERVO_DUTY_CENTER)

    def test_labels(self):
        self.assertEqual(rc.steering_label(0.5), "right")
        self.assertEqual(rc.steering_label(-0.5), "left")
        self.assertEqual(rc.steering_label(0.0), "straight")


class ThrottleTests(unittest.TestCase):
    def test_cruise_used_without_triggers(self):
        self.assertEqual(rc.throttle_from_inputs(0, 0, 1.0), 1.0)
        self.assertEqual(rc.throttle_from_inputs(0, 0, -1.0), -1.0)

    def test_trigger_overrides_cruise(self):
        self.assertAlmostEqual(rc.throttle_from_inputs(0.4, 0, -1.0), 0.4)
        self.assertAlmostEqual(rc.throttle_from_inputs(0, 0.7, 1.0), -0.7)

    def test_direction_label(self):
        self.assertEqual(rc.direction_label(0.3), "forward")
        self.assertEqual(rc.direction_label(-0.3), "backward")
        self.assertEqual(rc.direction_label(0), "stopped")


class CarTests(unittest.TestCase):
    def test_car_runs_on_fake_gpio(self):
        car = rc.Car(rc.FakeGPIO())
        car.drive(0.5)
        self.assertEqual(car.throttle, 0.5)
        car.drive(-2)
        self.assertEqual(car.throttle, -1.0)
        car.cleanup()
        self.assertEqual(car.throttle, 0)


class LogTests(unittest.TestCase):
    def test_log_writes_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = rc.SessionLog(tmp)
            log.write(0.5, 1.0, "img_00000.jpg")
            log.write(0.0, 0.0)
            log.close()
            with open(os.path.join(log.folder, "controls.csv")) as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["steering"], "right")
            self.assertEqual(rows[0]["direction"], "forward")
            self.assertEqual(rows[1]["direction"], "stopped")


if __name__ == "__main__":
    unittest.main()
