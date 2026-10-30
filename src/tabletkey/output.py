"""Linux uinput output with balanced key releases across shutdown and profile changes."""

from collections import Counter

from evdev import UInput, ecodes

from tabletkey.config import Settings, parse_binding
from tabletkey.protocol import ControlEvent


class Output:
    def __init__(self, settings: Settings) -> None:
        self.actions = {control: parse_binding(binding) for control, binding in settings.bindings.items()}
        keys = {ecodes.KEY_ESC}
        for action in self.actions.values():
            keys.update(action.keys)
        self.keyboard = UInput({ecodes.EV_KEY: sorted(keys)}, name="TabletKey Virtual Keyboard")
        try:
            self.mouse = UInput(
                {
                    ecodes.EV_KEY: [ecodes.BTN_LEFT],
                    ecodes.EV_REL: [ecodes.REL_X, ecodes.REL_Y, ecodes.REL_WHEEL],
                },
                name="TabletKey Virtual Mouse",
            )
        except BaseException:
            self.keyboard.close()
            raise
        self.held: Counter[int] = Counter()
        self.active: set[str] = set()

    def handle(self, event: ControlEvent) -> None:
        action = self.actions[event.control]
        if action.scroll:
            if event.pressed:
                self.mouse.write(ecodes.EV_REL, ecodes.REL_WHEEL, action.scroll)
                self.mouse.syn()
            return
        if event.pressed:
            if event.control in self.active:
                return
            self.active.add(event.control)
            for code in action.keys:
                if not self.held[code]:
                    self.keyboard.write(ecodes.EV_KEY, code, 1)
                self.held[code] += 1
        else:
            if event.control not in self.active:
                return
            self.active.remove(event.control)
            for code in reversed(action.keys):
                self.held[code] -= 1
                if not self.held[code]:
                    self.keyboard.write(ecodes.EV_KEY, code, 0)
                    del self.held[code]
        self.keyboard.syn()

    def release_all(self) -> None:
        try:
            for code in reversed(list(self.held)):
                self.keyboard.write(ecodes.EV_KEY, code, 0)
            self.keyboard.syn()
        finally:
            self.held.clear()
            self.active.clear()

    def close(self) -> None:
        try:
            self.release_all()
        finally:
            try:
                self.keyboard.close()
            finally:
                self.mouse.close()
