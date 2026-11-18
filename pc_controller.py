"""
PC test mode: reads an Xbox controller (or the keyboard) with pygame and shows
a small dashboard window, so rc.py can be tested on Windows/macOS/Linux
without a Raspberry Pi.

It exposes the same interface rc.py uses from approxeng.input:
    with PygameController() as joystick:
        while joystick.connected:
            presses = joystick.check_presses()   # presses["cross"], presses["dup"], ...
            joystick["lx"], joystick["rt"], joystick["lt"]

Keyboard (always works, even with a controller plugged in):
    Left / Right   steer
    Up / Down      hold to drive forward / backward
    W / S          cruise forward / backward
    Space          stop
    Esc            quit
"""

import os
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

# Xbox controller layout as reported by SDL2 on Windows
AXIS_LX = 0
AXIS_LT = 4
AXIS_RT = 5
BUTTON_NAMES = {0: "cross", 1: "circle", 2: "square", 3: "triangle", 4: "l1", 5: "r1"}

KEY_PRESSES = {
    pygame.K_ESCAPE: "cross",
    pygame.K_SPACE: "triangle",
    pygame.K_w: "dup",
    pygame.K_s: "ddown",
}

WINDOW_SIZE = (420, 230)
BG = (24, 26, 30)
FG = (230, 232, 236)
MUTED = (140, 145, 155)
ACCENT = (80, 160, 255)
FORWARD = (90, 200, 120)
BACKWARD = (235, 110, 90)


class Presses:
    """Behaves like approxeng's ButtonPresses: missing buttons read as False."""

    def __init__(self, names):
        self.names = set(names)

    def __getitem__(self, name):
        return name in self.names


class PygameController:
    def __init__(self):
        self.connected = False
        self.joystick = None
        self.screen = None
        self.font = None
        self.small = None
        self._pending = set()
        # Triggers report a misleading value until they are first moved,
        # so ignore each one until a motion event has been seen for it.
        self._trigger_seen = {AXIS_LT: False, AXIS_RT: False}

    # -- context manager ----------------------------------------------------
    def __enter__(self):
        pygame.init()
        pygame.display.set_caption("RC car - PC test mode")
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        self.font = pygame.font.SysFont("consolas", 20)
        self.small = pygame.font.SysFont("consolas", 14)
        pygame.joystick.init()
        if pygame.joystick.get_count() > 0:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick.init()
            print("Controller found:", self.joystick.get_name())
        else:
            print("No controller found - using the keyboard (arrows, W/S, Space, Esc)")
        self.connected = True
        return self

    def __exit__(self, *exc):
        pygame.quit()
        return False

    # -- input --------------------------------------------------------------
    def _pump(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._pending.add("cross")
            elif event.type == pygame.KEYDOWN and event.key in KEY_PRESSES:
                self._pending.add(KEY_PRESSES[event.key])
            elif event.type == pygame.JOYBUTTONDOWN and event.button in BUTTON_NAMES:
                self._pending.add(BUTTON_NAMES[event.button])
            elif event.type == pygame.JOYHATMOTION:
                _, hat_y = event.value
                if hat_y == 1:
                    self._pending.add("dup")
                elif hat_y == -1:
                    self._pending.add("ddown")
            elif event.type == pygame.JOYAXISMOTION and event.axis in self._trigger_seen:
                self._trigger_seen[event.axis] = True
            elif event.type == pygame.JOYDEVICEREMOVED:
                print("Controller unplugged - switching to keyboard")
                self.joystick = None
            elif event.type == pygame.JOYDEVICEADDED and self.joystick is None:
                self.joystick = pygame.joystick.Joystick(event.device_index)
                self.joystick.init()
                print("Controller connected:", self.joystick.get_name())

    def check_presses(self):
        self._pump()
        presses = Presses(self._pending)
        self._pending = set()
        return presses

    def _trigger(self, axis):
        if not self.joystick or not self._trigger_seen[axis]:
            return 0.0
        return (self.joystick.get_axis(axis) + 1.0) / 2.0   # -1..1  ->  0..1

    def __getitem__(self, name):
        keys = pygame.key.get_pressed()
        if name == "lx":
            if keys[pygame.K_LEFT] or keys[pygame.K_RIGHT]:
                return float(keys[pygame.K_RIGHT]) - float(keys[pygame.K_LEFT])
            return self.joystick.get_axis(AXIS_LX) if self.joystick else 0.0
        if name == "rt":
            return 1.0 if keys[pygame.K_UP] else self._trigger(AXIS_RT)
        if name == "lt":
            return 1.0 if keys[pygame.K_DOWN] else self._trigger(AXIS_LT)
        raise KeyError(name)

    # -- dashboard ----------------------------------------------------------
    def draw(self, steer_x, throttle, steering, direction, rows):
        s = self.screen
        s.fill(BG)
        w = WINDOW_SIZE[0]
        source = self.joystick.get_name() if self.joystick else "Keyboard"
        s.blit(self.small.render("Input: " + source[:40], True, MUTED), (16, 12))

        # steering bar (centre = straight)
        s.blit(self.font.render("Steering  %-8s %+.2f" % (steering, steer_x), True, FG), (16, 40))
        bar = pygame.Rect(16, 68, w - 32, 18)
        pygame.draw.rect(s, (50, 54, 62), bar, border_radius=4)
        mid = bar.centerx
        pygame.draw.line(s, MUTED, (mid, bar.top), (mid, bar.bottom))
        x = mid + int(steer_x * (bar.width / 2))
        pygame.draw.rect(s, ACCENT, pygame.Rect(x - 5, bar.top - 3, 10, bar.height + 6), border_radius=3)

        # throttle bar (fills from the centre)
        colour = FORWARD if throttle > 0 else BACKWARD if throttle < 0 else MUTED
        s.blit(self.font.render("Throttle  %-8s %+.2f" % (direction, throttle), True, FG), (16, 104))
        bar = pygame.Rect(16, 132, w - 32, 18)
        pygame.draw.rect(s, (50, 54, 62), bar, border_radius=4)
        length = int(abs(throttle) * (bar.width / 2))
        fill = pygame.Rect(bar.centerx if throttle >= 0 else bar.centerx - length, bar.top, length, bar.height)
        pygame.draw.rect(s, colour, fill, border_radius=4)
        pygame.draw.line(s, MUTED, (bar.centerx, bar.top), (bar.centerx, bar.bottom))

        s.blit(self.small.render("Logged rows: %d" % rows, True, MUTED), (16, 166))
        s.blit(self.small.render("Keys: arrows drive/steer  W/S cruise  Space stop  Esc quit",
                                 True, MUTED), (16, 196))
        pygame.display.flip()
