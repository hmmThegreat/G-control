import time
from collections import deque


class GestureEngine:
    """Detects left/right swipe gestures from a rolling window of hand positions."""

    def __init__(self, config: dict):
        self.config = config
        self._positions: deque = deque(maxlen=60)
        self._last_gesture_time = 0.0

    def update_config(self, config: dict):
        self.config = config

    def add_position(self, x_norm: float, y_norm: float):
        """Feed normalised wrist position (0–1 range) for each frame."""
        self._positions.append((x_norm, y_norm, time.time()))

    def reset(self):
        self._positions.clear()

    def detect(self) -> str | None:
        """Returns 'left', 'right', or None."""
        if not self.config.get("enabled", True):
            return None

        now = time.time()
        cooldown = float(self.config.get("cooldown", 0.8))
        if now - self._last_gesture_time < cooldown:
            return None

        window = int(self.config.get("frame_window", 20))
        recent = list(self._positions)[-window:]
        if len(recent) < 5:
            return None

        time_span = recent[-1][2] - recent[0][2]
        if time_span < 0.05:
            return None

        dx = recent[-1][0] - recent[0][0]
        sensitivity = float(self.config.get("sensitivity", 0.15))
        if abs(dx) < sensitivity:
            return None

        # Consistency check — majority of micro-steps in same direction
        steps = [recent[i][0] - recent[i - 1][0] for i in range(1, len(recent))]
        positive = sum(1 for s in steps if s > 0)
        negative = sum(1 for s in steps if s < 0)
        total = len(steps)

        gesture = None
        if dx > 0 and positive / total > 0.55:
            gesture = "right"
        elif dx < 0 and negative / total > 0.55:
            gesture = "left"

        if gesture:
            self._last_gesture_time = now
            self._positions.clear()

        return gesture
