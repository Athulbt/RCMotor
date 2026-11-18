import csv
import os
import sys
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")   # no real window during tests
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import pygame
    import pc_controller
except ImportError:  # pygame not installed (e.g. on the Pi)
    pygame = None

import rc  # noqa: E402


@unittest.skipIf(pygame is None, "pygame not installed")
class PygameControllerTests(unittest.TestCase):
    def test_keyboard_presses_map_to_buttons(self):
        with pc_controller.PygameController() as joystick:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_w))
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
            presses = joystick.check_presses()
            self.assertTrue(presses["dup"])
            self.assertTrue(presses["cross"])
            self.assertFalse(presses["ddown"])
            # presses are cleared once read
            self.assertFalse(joystick.check_presses()["cross"])

    def test_idle_inputs_are_zero(self):
        with pc_controller.PygameController() as joystick:
            joystick.check_presses()
            if joystick.joystick is None:   # a real controller may be plugged in
                self.assertEqual(joystick["lx"], 0.0)
            self.assertEqual(joystick["rt"], 0.0)
            self.assertEqual(joystick["lt"], 0.0)

    def test_full_run_in_pc_mode(self):
        calls = {"n": 0}
        original = pc_controller.PygameController.check_presses

        def scripted(self):
            calls["n"] += 1
            if calls["n"] == 3:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_w))
            if calls["n"] == 10:
                pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
            return original(self)

        pc_controller.PygameController.check_presses = scripted
        try:
            with tempfile.TemporaryDirectory() as tmp:
                rc.run(rc.parse_args(["--pc", "--no-camera", "--data-dir", tmp]))
                sessions = os.listdir(tmp)
                self.assertEqual(len(sessions), 1)
                with open(os.path.join(tmp, sessions[0], "controls.csv")) as f:
                    rows = list(csv.DictReader(f))
                self.assertGreaterEqual(len(rows), 1)
        finally:
            pc_controller.PygameController.check_presses = original
        self.assertEqual(calls["n"], 10)


if __name__ == "__main__":
    unittest.main()
