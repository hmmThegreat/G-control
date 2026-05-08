"""
settings_ui.py — Dark-themed Tkinter settings panel for GestureFlow.
Embeds live camera preview and exposes all configuration sliders/toggles.
"""

from __future__ import annotations

import queue
import tkinter as tk
from tkinter import font as tkfont
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main import SharedState

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False


# ── Colour palette ────────────────────────────────────────────────────────────
BG       = "#0d0d1a"
SURFACE  = "#15152a"
CARD     = "#1c1c35"
BORDER   = "#2a2a4a"
ACCENT   = "#7c3aed"   # purple
ACCENT2  = "#06b6d4"   # cyan
GREEN    = "#10b981"
RED      = "#ef4444"
AMBER    = "#f59e0b"
TEXT     = "#e2e8f0"
MUTED    = "#64748b"
TROUGH   = "#25253d"


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[:2], 16), int(h[2:4], 16), int(h[4:], 16)


class SettingsUI:
    W, H = 460, 820
    CAM_W, CAM_H = 430, 242   # 16:9 preview inside panel

    def __init__(self, shared_state: "SharedState", frame_queue: queue.Queue):
        self.state = shared_state
        self.fq = frame_queue

        self.root = tk.Tk()
        self.root.title("✋  GestureFlow — Settings")
        self.root.geometry(f"{self.W}x{self.H}+60+60")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        # Tk vars (mirrored from config)
        cfg = self.state.get_config()
        self._enabled      = tk.BooleanVar(value=cfg["enabled"])
        self._sensitivity  = tk.DoubleVar(value=cfg["sensitivity"])
        self._cooldown     = tk.DoubleVar(value=cfg["cooldown"])
        self._confidence   = tk.DoubleVar(value=cfg["min_confidence"])
        self._landmarks    = tk.BooleanVar(value=cfg["show_landmarks"])
        self._trail        = tk.BooleanVar(value=cfg["show_trail"])
        self._natural      = tk.BooleanVar(value=cfg["natural_scrolling"])
        self._mode         = tk.StringVar(value=cfg["mode"])

        self._cam_label: tk.Label | None = None
        self._status_hand  = tk.StringVar(value="—")
        self._status_fps   = tk.StringVar(value="0")
        self._status_count = tk.StringVar(value="0")
        self._status_last  = tk.StringVar(value="—")

        self._gesture_flash_until = 0.0

        self._build_ui()
        self._bind_vars()

    # ─────────────────────────────── UI BUILD ────────────────────────────────

    def _build_ui(self):
        root = self.root

        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(root, bg=SURFACE, height=64)
        hdr.pack(fill="x")
        tk.Label(hdr, text="✋  GestureFlow", bg=SURFACE, fg=TEXT,
                 font=("Helvetica Neue", 20, "bold")).pack(side="left", padx=18, pady=14)
        tk.Label(hdr, text="v1.0  •  Spaces Mode", bg=SURFACE, fg=MUTED,
                 font=("Helvetica Neue", 11)).pack(side="right", padx=18)

        # ── Camera preview ────────────────────────────────────────────────────
        cam_frame = tk.Frame(root, bg=BG, pady=10)
        cam_frame.pack(fill="x")
        if PIL_OK:
            self._cam_label = tk.Label(cam_frame, bg="#000010",
                                       width=self.CAM_W, height=self.CAM_H)
            self._cam_label.pack()
        else:
            tk.Label(cam_frame, text="⚠  Install Pillow for live preview\n(pip3 install Pillow)",
                     bg="#000010", fg=MUTED, width=60, height=10,
                     font=("Helvetica Neue", 11)).pack()

        # ── Status row ────────────────────────────────────────────────────────
        st = tk.Frame(root, bg=CARD, pady=6)
        st.pack(fill="x", padx=12, pady=(0, 8))
        self._build_stat(st, "Hand",    self._status_hand,  GREEN,  0)
        self._build_stat(st, "FPS",     self._status_fps,   ACCENT2, 1)
        self._build_stat(st, "Gestures",self._status_count, ACCENT,  2)
        self._build_stat(st, "Last",    self._status_last,  AMBER,   3)

        # ── Enable toggle ─────────────────────────────────────────────────────
        self._toggle_btn = tk.Button(
            root, textvariable=tk.StringVar(),
            command=self._toggle_enabled,
            relief="flat", bd=0, cursor="hand2",
            font=("Helvetica Neue", 14, "bold"),
            padx=0, pady=14, width=38,
        )
        self._toggle_btn.pack(fill="x", padx=12, pady=(0, 10))
        self._refresh_toggle_btn()

        # ── Settings cards ────────────────────────────────────────────────────
        self._build_slider_card(root, "Sensitivity",
            "Minimum hand movement to trigger a swipe",
            self._sensitivity, 0.05, 0.40, 0.01)

        self._build_slider_card(root, "Cooldown  (seconds)",
            "Pause between consecutive gestures",
            self._cooldown, 0.3, 2.5, 0.1)

        self._build_slider_card(root, "Detection Confidence",
            "MediaPipe hand detection threshold",
            self._confidence, 0.40, 0.95, 0.05)

        # ── Toggles ───────────────────────────────────────────────────────────
        tgl_card = self._card(root)
        self._build_toggle_row(tgl_card, "Show Hand Landmarks", self._landmarks)
        self._build_toggle_row(tgl_card, "Show Swipe Trail",    self._trail)
        self._build_toggle_row(tgl_card, "Natural Scrolling  (mirrors trackpad)",
                               self._natural)

        # ── Footer ────────────────────────────────────────────────────────────
        tk.Label(root, text="Close this window to quit GestureFlow",
                 bg=BG, fg=MUTED, font=("Helvetica Neue", 10)).pack(pady=(6, 2))

    def _build_stat(self, parent, label, var, color, col):
        f = tk.Frame(parent, bg=CARD)
        f.grid(row=0, column=col, padx=6, pady=4, sticky="ew")
        parent.columnconfigure(col, weight=1)
        tk.Label(f, text=label, bg=CARD, fg=MUTED,
                 font=("Helvetica Neue", 9)).pack()
        tk.Label(f, textvariable=var, bg=CARD, fg=color,
                 font=("Helvetica Neue", 13, "bold")).pack()

    def _card(self, parent) -> tk.Frame:
        outer = tk.Frame(parent, bg=CARD, bd=0,
                         highlightbackground=BORDER, highlightthickness=1)
        outer.pack(fill="x", padx=12, pady=4)
        return outer

    def _build_slider_card(self, parent, title, subtitle, var, lo, hi, step):
        card = self._card(parent)

        top = tk.Frame(card, bg=CARD)
        top.pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(top, text=title, bg=CARD, fg=TEXT,
                 font=("Helvetica Neue", 12, "bold")).pack(side="left")
        val_lbl = tk.Label(top, textvariable=var, bg=CARD, fg=ACCENT2,
                           font=("Helvetica Neue", 12, "bold"))
        val_lbl.pack(side="right")
        # Format display to 2dp
        var.trace_add("write", lambda *_: val_lbl.config(
            text=f"{var.get():.2f}"))

        tk.Label(card, text=subtitle, bg=CARD, fg=MUTED,
                 font=("Helvetica Neue", 9)).pack(anchor="w", padx=12)

        s = tk.Scale(card, variable=var, from_=lo, to=hi, resolution=step,
                     orient="horizontal", bg=CARD, fg=TEXT,
                     troughcolor=TROUGH, activebackground=ACCENT,
                     highlightthickness=0, bd=0, showvalue=False,
                     sliderlength=18, length=410)
        s.pack(padx=12, pady=(2, 10), fill="x")

    def _build_toggle_row(self, parent, label, var):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=14, pady=5)
        tk.Label(row, text=label, bg=CARD, fg=TEXT,
                 font=("Helvetica Neue", 11)).pack(side="left")
        cb = tk.Checkbutton(row, variable=var, bg=CARD,
                            activebackground=CARD, selectcolor=ACCENT,
                            fg=TEXT, cursor="hand2")
        cb.pack(side="right")

    def _refresh_toggle_btn(self):
        on = self._enabled.get()
        self._toggle_btn.config(
            text="⏸  PAUSE GESTURE CONTROL" if on else "▶  ENABLE GESTURE CONTROL",
            bg=ACCENT if on else "#2a2a4a",
            fg=TEXT,
            activebackground="#5b21b6" if on else "#3a3a5a",
            activeforeground=TEXT,
        )

    # ─────────────────────────────── BINDINGS ────────────────────────────────

    def _bind_vars(self):
        """Push Tk var changes back to SharedState + save config."""
        self._enabled.trace_add(   "write", lambda *_: self._push("enabled",           self._enabled.get()))
        self._sensitivity.trace_add("write", lambda *_: self._push("sensitivity",       round(self._sensitivity.get(), 3)))
        self._cooldown.trace_add(  "write", lambda *_: self._push("cooldown",           round(self._cooldown.get(), 2)))
        self._confidence.trace_add("write", lambda *_: self._push("min_confidence",     round(self._confidence.get(), 2)))
        self._landmarks.trace_add( "write", lambda *_: self._push("show_landmarks",     self._landmarks.get()))
        self._trail.trace_add(     "write", lambda *_: self._push("show_trail",         self._trail.get()))
        self._natural.trace_add(   "write", lambda *_: self._push("natural_scrolling",  self._natural.get()))

    def _push(self, key: str, value):
        self.state.update_config(key, value)
        if key == "enabled":
            self._refresh_toggle_btn()

    def _toggle_enabled(self):
        self._enabled.set(not self._enabled.get())

    # ─────────────────────────────── MAIN LOOP ───────────────────────────────

    def _poll(self):
        """Called every ~33 ms from tkinter event loop."""
        # Update camera frame
        if PIL_OK and self._cam_label:
            try:
                raw = self.fq.get_nowait()
                import cv2
                rgb = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb).resize(
                    (self.CAM_W, self.CAM_H), Image.BILINEAR)
                imgtk = ImageTk.PhotoImage(image=img)
                self._cam_label.imgtk = imgtk   # keep reference
                self._cam_label.config(image=imgtk)
            except queue.Empty:
                pass

        # Update status
        st = self.state.get_status()
        detected = st.get("hand_detected", False)
        self._status_hand.set("✓ Yes" if detected else "✗ No")
        self._status_fps.set(f"{st.get('fps', 0):.0f}")
        self._status_count.set(str(st.get("gesture_count", 0)))
        last = st.get("last_gesture")
        self._status_last.set("← Left" if last == "left" else
                               "Right →" if last == "right" else "—")

        self.root.after(33, self._poll)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(33, self._poll)
        self.root.mainloop()

    def _on_close(self):
        self.state.stop()
        self.root.destroy()
