"""
main.py — GestureFlow entry point.

Architecture
------------
  Main thread : Tkinter settings UI (required by macOS AppKit)
  Thread-2    : Camera capture + MediaPipe + gesture detection + action dispatch
  Queue       : Thread-2 → Main thread for HUD frames (live preview)

MediaPipe 0.10+ uses the Tasks API — HandLandmarker with a .task model file.
"""

from __future__ import annotations

import os
# Tell OpenCV not to try to spin its own auth loop (macOS requirement
# when running from a non-main thread). Camera permission must be granted
# to Terminal in System Settings → Privacy → Camera first.
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "1")

import queue
import threading
import time
import sys

import cv2
import numpy as np

import config as cfg_mod
from gesture_engine import GestureEngine
from action_dispatcher import ActionDispatcher
from hud_renderer import HUDRenderer
from settings_ui import SettingsUI

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "hand_landmarker.task")

# Landmark indices for drawing connections (21-point hand skeleton)
HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),        # thumb
    (0,5),(5,6),(6,7),(7,8),        # index
    (5,9),(9,10),(10,11),(11,12),   # middle
    (9,13),(13,14),(14,15),(15,16), # ring
    (13,17),(0,17),(17,18),(18,19),(19,20), # pinky + palm
]


# ── Shared state (thread-safe) ────────────────────────────────────────────────

class SharedState:
    def __init__(self, initial_config: dict):
        self._lock   = threading.Lock()
        self._config = initial_config.copy()
        self._status: dict = {
            "fps": 0.0,
            "hand_detected": False,
            "gesture_count": 0,
            "last_gesture": None,
        }
        self._stop = threading.Event()

    def get_config(self) -> dict:
        with self._lock:
            return self._config.copy()

    def update_config(self, key: str, value):
        with self._lock:
            self._config[key] = value
        cfg_mod.save(self._config)

    def get_status(self) -> dict:
        with self._lock:
            return self._status.copy()

    def update_status(self, **kwargs):
        with self._lock:
            self._status.update(kwargs)

    def stop(self):
        self._stop.set()

    def is_stopped(self) -> bool:
        return self._stop.is_set()


# ── Landmark drawing helper ───────────────────────────────────────────────────

def _draw_landmarks(frame: np.ndarray, landmarks: list, w: int, h: int):
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    for a, b in HAND_CONNECTIONS:
        cv2.line(frame, pts[a], pts[b], (80, 220, 180), 2, cv2.LINE_AA)
    for px, py in pts:
        cv2.circle(frame, (px, py), 4, (255, 255, 255), -1)
        cv2.circle(frame, (px, py), 4, (60, 200, 140), 1)


# ── Camera / processing thread ────────────────────────────────────────────────

def camera_loop(state: SharedState, frame_queue: queue.Queue):
    try:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision
        from mediapipe import Image as MpImage, ImageFormat
    except ImportError as e:
        print(f"[ERROR] mediapipe import failed: {e}")
        state.stop()
        return

    if not os.path.exists(MODEL_PATH):
        print(f"[ERROR] Model not found: {MODEL_PATH}")
        print("  Run: curl -L https://storage.googleapis.com/mediapipe-models/"
              "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task "
              f"-o '{MODEL_PATH}'")
        state.stop()
        return

    engine     = GestureEngine(state.get_config())
    dispatcher = ActionDispatcher(state.get_config())
    hud        = HUDRenderer()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Cannot open webcam. Check camera permissions.")
        state.stop()
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    gesture_count = 0
    fps_ema       = 30.0
    prev_ts       = time.time()

    # Build HandLandmarker (Tasks API)
    cfg = state.get_config()
    options = mp_vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=mp_vision.RunningMode.IMAGE,
        num_hands=1,
        min_hand_detection_confidence=float(cfg["min_confidence"]),
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = mp_vision.HandLandmarker.create_from_options(options)

    try:
        while not state.is_stopped():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.03)
                continue

            frame = cv2.flip(frame, 1)
            now   = time.time()
            dt    = now - prev_ts
            prev_ts = now
            fps_ema = 0.85 * fps_ema + 0.15 * (1.0 / max(dt, 0.001))

            cfg = state.get_config()
            engine.update_config(cfg)
            dispatcher.update_config(cfg)

            h, w = frame.shape[:2]
            rgb  = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_img = MpImage(image_format=ImageFormat.SRGB, data=rgb)
            result = landmarker.detect(mp_img)

            hand_detected = bool(result.hand_landmarks)
            if hand_detected:
                lm_list = result.hand_landmarks[0]   # NormalizedLandmark list

                if cfg.get("show_landmarks", True):
                    _draw_landmarks(frame, lm_list, w, h)

                # Wrist = index 0
                wrist = lm_list[0]
                engine.add_position(wrist.x, wrist.y)

                px, py = int(wrist.x * w), int(wrist.y * h)
                hud.add_trail(px, py)

                gesture = engine.detect()
                if gesture:
                    gesture_count += 1
                    state.update_status(gesture_count=gesture_count,
                                        last_gesture=gesture)
                    hud.notify_gesture(gesture)
                    if cfg.get("enabled", True):
                        dispatcher.dispatch(gesture)
            else:
                engine.reset()

            state.update_status(fps=fps_ema, hand_detected=hand_detected)
            frame = hud.draw(frame, cfg, fps_ema, hand_detected)

            try:
                frame_queue.put_nowait(frame)
            except queue.Full:
                pass

    finally:
        landmarker.close()
        cap.release()
        print("[camera] Thread exiting.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    if sys.version_info < (3, 8):
        print("GestureFlow requires Python 3.8+")
        sys.exit(1)

    initial_cfg = cfg_mod.load()
    state       = SharedState(initial_cfg)
    fq          = queue.Queue(maxsize=2)

    cam_thread = threading.Thread(
        target=camera_loop, args=(state, fq), daemon=True, name="camera")
    cam_thread.start()

    print("=" * 50)
    print("  ✋  GestureFlow — Mac Gesture Control v1.0")
    print("=" * 50)
    print("  Swipe LEFT  → previous Space")
    print("  Swipe RIGHT → next Space")
    print("  Close the Settings window to quit")
    print("=" * 50)
    print("\n  ⚠  Grant Camera + Accessibility access if prompted.\n")

    ui = SettingsUI(state, fq)
    ui.run()

    state.stop()
    cam_thread.join(timeout=3)
    print("GestureFlow stopped. Bye!")


if __name__ == "__main__":
    main()
