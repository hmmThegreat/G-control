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

        window = int(self.config.get("frame_window", 25))
        recent = list(self._positions)[-window:]
        if len(recent) < int(window * 0.5):
            return None

        time_span = recent[-1][2] - recent[0][2]
        if time_span < 0.1:  # Need at least 100ms of data
            return None

        xs = [p[0] for p in recent]
        ys = [p[1] for p in recent]

        dx = xs[-1] - xs[0]
        dy = ys[-1] - ys[0]
        
        sensitivity = float(self.config.get("sensitivity", 0.12))
        
        # 1. Total horizontal displacement must exceed sensitivity
        if abs(dx) < sensitivity:
            return None
            
        # 2. Must be primarily horizontal (reject up/down or steep diagonal swipes)
        if abs(dy) > abs(dx) * 0.8:
            return None

        # 3. Movement should be mostly unidirectional (filter out hand waving)
        max_x = max(xs)
        min_x = min(xs)
        path_length = max_x - min_x
        
        if path_length == 0:
            return None
            
        # If net displacement is close to the max path length, it's a straight swipe
        if abs(dx) / path_length < 0.6:
            return None

        gesture = None
        if dx > 0:
            gesture = "right"
        elif dx < 0:
            gesture = "left"

        if gesture:
            self._last_gesture_time = now
            self._positions.clear()

        return gesture
