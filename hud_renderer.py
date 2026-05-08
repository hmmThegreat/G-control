import time
import cv2
import numpy as np


class HUDRenderer:
    """Draws gesture feedback overlay onto camera frames."""

    _FONT = cv2.FONT_HERSHEY_SIMPLEX

    def __init__(self):
        self._gesture: str | None = None
        self._gesture_ts: float = 0.0
        self._display_secs: float = 1.1
        self._trail: list[tuple[int, int, float]] = []

    def notify_gesture(self, gesture: str):
        self._gesture = gesture
        self._gesture_ts = time.time()

    def add_trail(self, px: int, py: int):
        now = time.time()
        self._trail.append((px, py, now))
        cutoff = now - 0.55
        self._trail = [(x, y, t) for x, y, t in self._trail if t > cutoff]

    def draw(self, frame: np.ndarray, config: dict, fps: float = 0.0,
             hand_detected: bool = False) -> np.ndarray:
        h, w = frame.shape[:2]
        now = time.time()

        # ── Top status bar ────────────────────────────────────────────────
        bar = frame.copy()
        cv2.rectangle(bar, (0, 0), (w, 52), (12, 12, 22), -1)
        cv2.addWeighted(bar, 0.75, frame, 0.25, 0, frame)

        enabled = config.get("enabled", True)
        mode = config.get("mode", "spaces").upper()

        # Status dot
        dot_color = (30, 210, 110) if (enabled and hand_detected) else \
                    (50, 200, 255) if enabled else (70, 70, 90)
        cv2.circle(frame, (22, 26), 8, dot_color, -1)
        status_txt = "ACTIVE" if (enabled and hand_detected) else \
                     "READY" if enabled else "PAUSED"
        cv2.putText(frame, status_txt, (36, 31), self._FONT, 0.55,
                    dot_color, 1, cv2.LINE_AA)

        # Mode label
        cv2.putText(frame, f"MODE: {mode}", (w // 2 - 52, 31),
                    self._FONT, 0.50, (160, 160, 190), 1, cv2.LINE_AA)

        # FPS
        cv2.putText(frame, f"{fps:.0f} fps", (w - 72, 31),
                    self._FONT, 0.50, (100, 100, 130), 1, cv2.LINE_AA)

        # ── Swipe trail ───────────────────────────────────────────────────
        if config.get("show_trail", True) and len(self._trail) > 1:
            for i in range(1, len(self._trail)):
                age = now - self._trail[i][2]
                alpha = max(0.0, 1.0 - age / 0.55)
                r = max(2, int(7 * alpha))
                ci = int(255 * alpha)
                cv2.circle(frame, (self._trail[i][0], self._trail[i][1]),
                           r, (ci, ci // 2, 255), -1)

        # ── Gesture banner ────────────────────────────────────────────────
        elapsed = now - self._gesture_ts
        if self._gesture and elapsed < self._display_secs:
            fade = 1.0 - (elapsed / self._display_secs)
            if self._gesture == "left":
                txt = "\u2190  SWIPE LEFT"
                base = (255, 130, 50)
            else:
                txt = "SWIPE RIGHT  \u2192"
                base = (50, 210, 255)

            color = tuple(int(c * fade) for c in base)
            sz, _ = cv2.getTextSize(txt, self._FONT, 1.6, 3)
            tx, ty = (w - sz[0]) // 2, h // 2 + 24
            # shadow
            cv2.putText(frame, txt, (tx + 2, ty + 2),
                        self._FONT, 1.6, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(frame, txt, (tx, ty),
                        self._FONT, 1.6, color, 3, cv2.LINE_AA)

        # ── Bottom hint ───────────────────────────────────────────────────
        cv2.putText(frame, "Use Settings panel to configure  |  Q to quit",
                    (15, h - 12), self._FONT, 0.38, (70, 70, 100), 1, cv2.LINE_AA)

        return frame
