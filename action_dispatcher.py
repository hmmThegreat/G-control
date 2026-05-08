import subprocess


class ActionDispatcher:
    """Translates gesture events into macOS system actions."""

    def __init__(self, config: dict):
        self.config = config

    def update_config(self, config: dict):
        self.config = config

    def dispatch(self, gesture: str):
        natural = self.config.get("natural_scrolling", False)
        # Natural scrolling: swipe direction matches trackpad feel
        # swipe RIGHT → go to previous (left) space, swipe LEFT → go to next (right) space
        effective = gesture
        if natural:
            effective = "left" if gesture == "right" else "right"

        mode = self.config.get("mode", "spaces")
        if mode == "spaces":
            self._switch_space(effective)
        elif mode == "slides":
            self._switch_slide(effective)

    def _switch_space(self, direction: str):
        # key code 123 = left arrow, 124 = right arrow (with Ctrl)
        key_code = 124 if direction == "right" else 123
        script = (
            f'tell application "System Events" to key code {key_code} '
            f'using {{control down}}'
        )
        subprocess.Popen(["osascript", "-e", script])

    def _switch_slide(self, direction: str):
        # Send arrow key for presentation apps
        key_code = 124 if direction == "right" else 123
        script = (
            f'tell application "System Events" to key code {key_code}'
        )
        subprocess.Popen(["osascript", "-e", script])
