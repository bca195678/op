#!/usr/bin/env python3
"""
ledcam.py — USB camera LED color detector for AXN-2020 front panel LEDs

Modes:
  calibrate    Live feed with sliders for all camera settings. S=save to camera_settings.json, Q/ESC=quit.
  live         Continuous live feed using saved camera settings. Q/ESC to quit.
  select-rois  Capture a frame then select ROIs interactively.
               Saves ./tmp/camera_settings.json and ./tmp/ledcam_rois.json
  detect       Open live window for 3 seconds. ROI colors refresh every 500ms.
               Loads camera_settings.json automatically. Saves annotated frame on close.
  diagnose     Print raw BGR channel stats per ROI (threshold tuning helper).
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime

import cv2
import numpy as np

SNAPSHOT_PATH = "./tmp/ledcam_snapshot.jpg"
DETECT_PATH   = "./tmp/ledcam_detect.jpg"


def rois_path(profile=None):
    if profile:
        return f"./tmp/ledcam_rois_{profile}.json"
    return "./tmp/ledcam_rois.json"
SETTINGS_PATH        = "./tmp/camera_settings.json"
SETTINGS_PATH_SKILL  = ".claude/skills/ledcam/camera_settings.json"

DEFAULT_SETTINGS = {
    "Focus":        120,
    "Exposure":     -6,    # cv2 actual value (negative)
    "Brightness":   128,
    "Contrast":     128,
    "Saturation":   128,
    "Gain":         0,
    "WhiteBalance": 5000,  # Kelvin
    "Sharpness":    128,
    "Backlight":    0,
}

# OpenCV trackbars require non-negative integer ranges
SLIDER_MAX = {
    "Focus":        255,
    "Exposure":     13,    # slider 0–13  →  actual = slider - 13
    "Brightness":   255,
    "Contrast":     255,
    "Saturation":   255,
    "Gain":         255,
    "WhiteBalance": 4500,  # slider 0–4500  →  actual = slider + 2000
    "Sharpness":    255,
    "Backlight":    3,
}

SLIDER_KEYS = list(SLIDER_MAX.keys())

COLOR_BGR = {
    "green":   (0, 200, 0),
    "amber":   (0, 165, 255),
    "off":     (100, 100, 100),
    "unknown": (0, 0, 255),
}


# ─── Settings helpers ─────────────────────────────────────────────────────────

def setting_to_slider(key, val):
    if key == "Exposure":     return max(0, min(13,   int(val + 13)))
    if key == "WhiteBalance": return max(0, min(4500, int(val - 2000)))
    return max(0, int(val))


def slider_to_setting(key, sval):
    if key == "Exposure":     return sval - 13
    if key == "WhiteBalance": return sval + 2000
    return sval


def load_settings():
    for path in (SETTINGS_PATH, SETTINGS_PATH_SKILL):
        if os.path.exists(path):
            with open(path) as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
    return dict(DEFAULT_SETTINGS)


def save_settings_file(settings):
    os.makedirs("./tmp", exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)
    print(f"Settings saved → {SETTINGS_PATH}")


def apply_settings(cap, settings):
    cap.set(cv2.CAP_PROP_AUTOFOCUS,     0)
    cap.set(cv2.CAP_PROP_FOCUS,         settings["Focus"])
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)   # 0.25 = manual on most drivers
    cap.set(cv2.CAP_PROP_EXPOSURE,      settings["Exposure"])
    cap.set(cv2.CAP_PROP_BRIGHTNESS,    settings["Brightness"])
    cap.set(cv2.CAP_PROP_CONTRAST,      settings["Contrast"])
    cap.set(cv2.CAP_PROP_SATURATION,    settings["Saturation"])
    cap.set(cv2.CAP_PROP_GAIN,          settings["Gain"])
    cap.set(cv2.CAP_PROP_WB_TEMPERATURE, settings["WhiteBalance"])
    cap.set(cv2.CAP_PROP_SHARPNESS,     settings["Sharpness"])
    cap.set(cv2.CAP_PROP_BACKLIGHT,     settings["Backlight"])


def open_camera(index):
    cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera index {index}", file=sys.stderr)
        sys.exit(1)
    return cap


# ─── Color detection ──────────────────────────────────────────────────────────

def get_mid_bgr(crop):
    """Return mean (B, G, R) of mid-brightness pixels (V 60–230), or None if too few."""
    if crop.size == 0:
        return None
    v = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[:, :, 2]
    mask = (v >= 60) & (v <= 230)
    if mask.sum() < 10:
        return None
    bgr = crop[mask].astype(float)
    return bgr[:, 0].mean(), bgr[:, 1].mean(), bgr[:, 2].mean()  # B, G, R


def classify_color(crop):
    """Return 'green', 'amber', 'off', or 'unknown' using BGR channel ratios."""
    if crop.size == 0:
        return "unknown"
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    v_max = hsv[:, :, 2].max()
    if v_max < 40:
        return "off"
    result = get_mid_bgr(crop)
    if result is None:
        return "off"
    B, G, R = result
    # Require sufficient brightness — dim ambient light is "off", not a color
    if max(B, G, R) < 140:
        return "off"
    if G - R > 8:
        return "green"
    if R - B > 4:
        return "amber"
    return "unknown"


def classify_rois(frame, rois):
    h_img, w_img = frame.shape[:2]
    results = {}
    for roi in rois:
        x  = max(0, min(roi["x"], w_img - 1))
        y  = max(0, min(roi["y"], h_img - 1))
        x2 = min(roi["x"] + roi["w"], w_img)
        y2 = min(roi["y"] + roi["h"], h_img)
        results[roi["label"]] = classify_color(frame[y:y2, x:x2])
    return results


def annotate_frame(frame, rois, results_by_label):
    h_img, w_img = frame.shape[:2]
    out = frame.copy()
    for roi in rois:
        x  = max(0, min(roi["x"], w_img - 1))
        y  = max(0, min(roi["y"], h_img - 1))
        x2 = min(roi["x"] + roi["w"], w_img)
        y2 = min(roi["y"] + roi["h"], h_img)
        color = results_by_label.get(roi["label"], "unknown")
        bgr = COLOR_BGR.get(color, (255, 255, 255))
        cv2.rectangle(out, (x, y), (x2, y2), bgr, 2)
        cv2.putText(out, f"{roi['label']}:{color}", (x, max(y - 10, 25)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, bgr, 2)
    return out


# ─── Modes ────────────────────────────────────────────────────────────────────

def _cal_sharpness(cap):
    for _ in range(3):
        cap.read()
    ret, frame = cap.read()
    if not ret:
        return 0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def _cal_show_progress(cap, win, text, pct):
    ret, frame = cap.read()
    if not ret:
        return
    cv2.rectangle(frame, (10, 10), (610, 60), (0, 0, 0), -1)
    cv2.putText(frame, text, (15, 47), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 2)
    cv2.rectangle(frame, (10, 65), (610, 85), (50, 50, 50), -1)
    cv2.rectangle(frame, (10, 65), (10 + int(6 * pct), 85), (0, 255, 0), -1)
    cv2.imshow(win, frame)
    cv2.waitKey(1)


def _cal_autofocus(cap, win):
    best_val, best_score = 0, -1
    coarse = range(0, 256, 10)
    for i, val in enumerate(coarse):
        cap.set(cv2.CAP_PROP_FOCUS, val)
        score = _cal_sharpness(cap)
        if score > best_score:
            best_score, best_val = score, val
        _cal_show_progress(cap, win, f"Autofocus... {int((i+1)/len(coarse)*100)}%",
                           int((i+1)/len(coarse)*100))
    best_score = -1
    fine = range(max(0, best_val - 15), min(255, best_val + 15) + 1)
    for i, val in enumerate(fine):
        cap.set(cv2.CAP_PROP_FOCUS, val)
        score = _cal_sharpness(cap)
        if score > best_score:
            best_score, best_val = score, val
        _cal_show_progress(cap, win, f"Fine tuning... {int((i+1)/len(fine)*100)}%",
                           int((i+1)/len(fine)*100))
    return best_val


def mode_calibrate(args):
    settings = load_settings()

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera index {args.camera}", file=sys.stderr)
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_AUTOFOCUS,    0)
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)
    cap.set(cv2.CAP_PROP_AUTO_WB,      0)

    # Apply saved settings
    prop_map = {
        "Focus":        cv2.CAP_PROP_FOCUS,
        "Exposure":     cv2.CAP_PROP_EXPOSURE,
        "Brightness":   cv2.CAP_PROP_BRIGHTNESS,
        "Contrast":     cv2.CAP_PROP_CONTRAST,
        "Saturation":   cv2.CAP_PROP_SATURATION,
        "Gain":         cv2.CAP_PROP_GAIN,
        "WhiteBalance": cv2.CAP_PROP_WB_TEMPERATURE,
        "Sharpness":    cv2.CAP_PROP_SHARPNESS,
        "Backlight":    cv2.CAP_PROP_BACKLIGHT,
    }
    for name, prop in prop_map.items():
        if name in settings:
            cap.set(prop, settings[name])
            print(f"Loaded {name} = {settings[name]}")

    WIN = "Camera"
    cv2.namedWindow(WIN)
    cv2.createTrackbar("Focus",        WIN, int(cap.get(cv2.CAP_PROP_FOCUS)),               255,  lambda v: cap.set(cv2.CAP_PROP_FOCUS,          v))
    cv2.createTrackbar("Exposure",     WIN, int(cap.get(cv2.CAP_PROP_EXPOSURE)) + 13,        13,  lambda v: cap.set(cv2.CAP_PROP_EXPOSURE,        v - 13))
    cv2.createTrackbar("Brightness",   WIN, int(cap.get(cv2.CAP_PROP_BRIGHTNESS)),           255, lambda v: cap.set(cv2.CAP_PROP_BRIGHTNESS,      v))
    cv2.createTrackbar("Contrast",     WIN, int(cap.get(cv2.CAP_PROP_CONTRAST)),             255, lambda v: cap.set(cv2.CAP_PROP_CONTRAST,        v))
    cv2.createTrackbar("Saturation",   WIN, int(cap.get(cv2.CAP_PROP_SATURATION)),           255, lambda v: cap.set(cv2.CAP_PROP_SATURATION,      v))
    cv2.createTrackbar("Gain",         WIN, int(cap.get(cv2.CAP_PROP_GAIN)),                 255, lambda v: cap.set(cv2.CAP_PROP_GAIN,            v))
    cv2.createTrackbar("WhiteBalance", WIN, int(cap.get(cv2.CAP_PROP_WB_TEMPERATURE))-2000, 4500, lambda v: cap.set(cv2.CAP_PROP_WB_TEMPERATURE,  v + 2000))
    cv2.createTrackbar("Sharpness",    WIN, int(cap.get(cv2.CAP_PROP_SHARPNESS)),            255, lambda v: cap.set(cv2.CAP_PROP_SHARPNESS,       v))
    cv2.createTrackbar("Backlight",    WIN, int(cap.get(cv2.CAP_PROP_BACKLIGHT)),              3, lambda v: cap.set(cv2.CAP_PROP_BACKLIGHT,       v))

    print("Calibrate: A=autofocus  F=set focus  S=save  Q/ESC=quit")

    typing, typed = False, ""

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if typing:
            cv2.rectangle(frame, (10, 10), (320, 55), (0, 0, 0), -1)
            cv2.putText(frame, f"Focus: {typed}_", (15, 44),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 0), 2)

        # Key hint overlay (top-left)
        hints = ["[A] Autofocus", "[F] Set focus", "[S] Save settings", "[Q] Quit"]
        x, y = 10, 45
        cv2.rectangle(frame, (x - 8, y - 38), (x + 320, y + len(hints) * 45 - 4), (0, 0, 0), -1)
        for i, hint in enumerate(hints):
            cv2.putText(frame, hint, (x, y + i * 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 200, 0), 2, cv2.LINE_AA)

        cv2.imshow(WIN, frame)
        key = cv2.waitKey(1) & 0xFF

        if key in (ord('q'), ord('Q'), 27) and not typing:
            break
        elif key in (ord('s'), ord('S')) and not typing:
            saved = {name: int(cap.get(prop)) for name, prop in prop_map.items()}
            os.makedirs("./tmp", exist_ok=True)
            with open(SETTINGS_PATH, "w") as f:
                json.dump(saved, f, indent=2)
            print(f"Settings saved -> {SETTINGS_PATH}")
        elif key == ord('a') and not typing:
            best = _cal_autofocus(cap, WIN)
            cap.set(cv2.CAP_PROP_FOCUS, best)
            cv2.setTrackbarPos("Focus", WIN, best)
        elif key == ord('f') and not typing:
            typing, typed = True, ""
        elif typing:
            if key == 13:   # Enter
                if typed.isdigit():
                    val = max(0, min(255, int(typed)))
                    cap.set(cv2.CAP_PROP_FOCUS, val)
                    cv2.setTrackbarPos("Focus", WIN, val)
                typing = False
            elif key == 27:
                typing = False
            elif key == 8 and typed:
                typed = typed[:-1]
            elif chr(key).isdigit() and len(typed) < 3:
                typed += chr(key)

    cap.release()
    cv2.destroyAllWindows()


def mode_live(args):
    settings = load_settings()
    cap = open_camera(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  9999)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 9999)
    apply_settings(cap, settings)
    for _ in range(10):
        cap.read()

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Live feed — {w}x{h}  |  Q or ESC to quit")

    WIN = "Live Feed"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 1280, 720)

    while True:
        ret, frame = cap.read()
        if not ret:
            print("ERROR: Failed to read frame", file=sys.stderr)
            break
        hints = ["[Q] Quit"]
        x, y = 10, 45
        cv2.rectangle(frame, (x - 8, y - 38), (x + 200, y + len(hints) * 45 - 4), (0, 0, 0), -1)
        for i, hint in enumerate(hints):
            cv2.putText(frame, hint, (x, y + i * 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 200, 0), 2, cv2.LINE_AA)

        cv2.imshow(WIN, frame)
        k = cv2.waitKey(1) & 0xFF
        if k in (ord('q'), ord('Q'), 27):  # Q or ESC
            break

    cap.release()
    cv2.destroyAllWindows()



def _select_rois_interactive(base_img, labels):
    """Custom ROI selector with live overlay showing current target and confirmed ROIs."""
    WIN = "ROI Calibration"
    font = cv2.FONT_HERSHEY_SIMPLEX
    ih, iw = base_img.shape[:2]
    fs = max(0.5, iw / 1920)
    lh = int(30 * fs)

    confirmed = []       # list of (label, x1, y1, x2, y2)
    drag = {"active": False, "x0": 0, "y0": 0, "x1": 0, "y1": 0}
    state = {"confirm": False, "redo": False, "done": False}

    def mouse_cb(event, x, y, flags, _):
        if event == cv2.EVENT_LBUTTONDOWN:
            drag["active"] = True
            drag["x0"] = drag["x1"] = x
            drag["y0"] = drag["y1"] = y
        elif event == cv2.EVENT_MOUSEMOVE and drag["active"]:
            drag["x1"] = x
            drag["y1"] = y
        elif event == cv2.EVENT_LBUTTONUP:
            drag["active"] = False
            drag["x1"] = x
            drag["y1"] = y

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, min(iw, 1600), min(ih, 900))
    cv2.setMouseCallback(WIN, mouse_cb)

    idx = 0
    open_ended = len(labels) == 0
    total = len(labels)

    while not state["done"] and (open_ended or idx < total):
        label = str(idx + 1) if open_ended else labels[idx]
        disp = base_img.copy()

        # Draw confirmed ROIs
        for (lbl, x1, y1, x2, y2) in confirmed:
            cv2.rectangle(disp, (x1, y1), (x2, y2), (0, 200, 0), 2)
            cv2.putText(disp, lbl, (x1, max(y1 - 5, 10)), font, fs * 0.7, (0, 200, 0), 1, cv2.LINE_AA)

        # Draw current drag box
        if drag["x0"] != drag["x1"] or drag["y0"] != drag["y1"]:
            cv2.rectangle(disp, (drag["x0"], drag["y0"]), (drag["x1"], drag["y1"]), (0, 255, 255), 2)

        # Top instruction bar
        bar_h = lh * 4 + 10
        cv2.rectangle(disp, (0, 0), (iw, bar_h), (20, 20, 20), -1)
        if open_ended:
            cv2.putText(disp, f"ROI {idx + 1}  —  draw box, ENTER confirm, ESC when done",
                        (10, lh), font, fs * 1.1, (0, 255, 255), 2, cv2.LINE_AA)
        else:
            cv2.putText(disp, f"NOW SELECTING: {label}  ({idx+1} of {total})",
                        (10, lh), font, fs * 1.1, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(disp, "Drag: draw box    ENTER/SPACE: confirm    R: redo    ESC: finish",
                    (10, lh * 2 + 4), font, fs * 0.8, (0, 200, 0), 1, cv2.LINE_AA)

        # Progress bar (only when total is known)
        if not open_ended:
            prog_w = int(iw * (idx / total))
            cv2.rectangle(disp, (0, bar_h - 6), (prog_w, bar_h), (0, 200, 100), -1)

        cv2.imshow(WIN, disp)
        k = cv2.waitKey(30) & 0xFF

        if k in (13, 32):   # ENTER or SPACE — confirm
            x1, x2 = sorted([drag["x0"], drag["x1"]])
            y1, y2 = sorted([drag["y0"], drag["y1"]])
            if x2 - x1 > 2 and y2 - y1 > 2:
                confirmed.append((label, x1, y1, x2, y2))
                drag.update({"x0": 0, "y0": 0, "x1": 0, "y1": 0})
                idx += 1
        elif k in (ord('r'), ord('R')):   # redo current
            drag.update({"x0": 0, "y0": 0, "x1": 0, "y1": 0})
        elif k == 27:   # ESC — finish early
            state["done"] = True

    cv2.destroyAllWindows()

    rois = []
    for (lbl, x1, y1, x2, y2) in confirmed:
        rois.append({"label": lbl, "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1})
    return rois


def mode_select_rois(args):
    labels = [l.strip() for l in args.labels.split(",")] if args.labels else []

    # Always capture a fresh snapshot with saved settings at max resolution
    settings = load_settings()
    cap = open_camera(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  9999)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 9999)
    apply_settings(cap, settings)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera resolution: {w}x{h}")
    print("Camera settings applied:")
    for k, v in settings.items():
        print(f"  {k:<14} {v}")
    for _ in range(10):
        cap.read()
    ret, captured_frame = cap.read()
    cap.release()
    if not ret:
        print("ERROR: Failed to capture frame.", file=sys.stderr)
        return
    os.makedirs("./tmp", exist_ok=True)
    ts_snap = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = f"./tmp/ledcam_snapshot_{ts_snap}.jpg"
    cv2.imwrite(snapshot_path, captured_frame)
    print(f"Snapshot captured → {snapshot_path}  ({w}x{h} px)")
    print("Window: drag to draw box, ENTER/SPACE confirm, R redo, ESC finish early.")
    print(f"Expected labels: {labels or '(auto-numbered)'}")

    rois = _select_rois_interactive(captured_frame, labels)

    img = captured_frame.copy()
    for r in rois:
        x, y, w, h = r["x"], r["y"], r["w"], r["h"]
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(img, r["label"], (x, max(y - 5, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    rp = rois_path(args.profile)
    with open(rp, "w") as f:
        json.dump(rois, f, indent=2)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    annotated = f"./tmp/ledcam_snapshot_{ts}_rois.jpg"
    cv2.imwrite(annotated, img)

    print(f"\n{len(rois)} ROIs saved → {rp}")
    print(f"Annotated snapshot → {annotated}")
    for r in rois:
        print(f"  {r['label']:12s}  x={r['x']} y={r['y']} w={r['w']} h={r['h']}")


def mode_detect(args):
    rp = rois_path(args.profile)
    if not os.path.exists(rp):
        print(f"ERROR: No ROIs found at {rp}. Run --mode select-rois first.", file=sys.stderr)
        sys.exit(1)

    with open(rp) as f:
        rois = json.load(f)

    settings = load_settings()
    cap = open_camera(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  9999)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 9999)
    apply_settings(cap, settings)
    for _ in range(10):
        cap.read()

    WIN = "LED Detection"
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, 1280, 720)

    DURATION          = 3.0
    CLASSIFY_INTERVAL = 0.5

    results_by_label = {}
    last_classify    = 0.0
    last_frame       = None
    start            = time.time()

    while True:
        elapsed = time.time() - start
        if elapsed >= DURATION:
            break

        ret, frame = cap.read()
        if not ret:
            continue

        now = time.time()
        if now - last_classify >= CLASSIFY_INTERVAL:
            results_by_label = classify_rois(frame, rois)
            last_classify = now

        annotated = annotate_frame(frame, rois, results_by_label)
        remaining = max(0.0, DURATION - elapsed)
        # Key hint overlay (top-left)
        hints = ["[Q] Quit"]
        hx, hy = 10, 45
        cv2.rectangle(annotated, (hx - 8, hy - 38), (hx + 200, hy + len(hints) * 45 - 4), (0, 0, 0), -1)
        for i, hint in enumerate(hints):
            cv2.putText(annotated, hint, (hx, hy + i * 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 200, 0), 2, cv2.LINE_AA)
        # Countdown (top-right)
        h_a, w_a = annotated.shape[:2]
        cv2.putText(annotated, f"Closing in {remaining:.1f}s", (w_a - 300, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.imshow(WIN, annotated)
        last_frame = annotated

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    if last_frame is None:
        print("ERROR: No frame captured", file=sys.stderr)
        sys.exit(1)

    os.makedirs("./tmp", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    profile_tag = f"_{args.profile}" if args.profile else ""
    detect_path = f"./tmp/ledcam_detect{profile_tag}_{ts}.jpg"
    cv2.imwrite(detect_path, last_frame)

    ordered = [(roi["label"], results_by_label.get(roi["label"], "unknown")) for roi in rois]
    print(f"{'Label':<14} {'Color'}")
    print("-" * 22)
    for label, color in ordered:
        print(f"{label:<14} {color}")

    print(f"\nAnnotated frame → {detect_path}")
    tally = Counter(color for _, color in ordered)
    print(f"\nSummary: {dict(tally)}")


def mode_diagnose(args):
    rp = rois_path(args.profile)
    if not os.path.exists(rp):
        print(f"ERROR: No ROIs found at {rp}.", file=sys.stderr)
        sys.exit(1)

    with open(rp) as f:
        rois = json.load(f)

    settings = load_settings()
    cap = open_camera(args.camera)
    apply_settings(cap, settings)
    for _ in range(10):
        cap.read()
    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("ERROR: Failed to capture frame", file=sys.stderr)
        sys.exit(1)

    h_img, w_img = frame.shape[:2]
    print(f"{'Port':<8} {'B':>6} {'G':>6} {'R':>6}  {'R-B':>6}  {'G-R':>6}  {'G-B':>6}  classify")
    print("-" * 68)
    for roi in rois:
        x  = max(0, min(roi["x"], w_img - 1))
        y  = max(0, min(roi["y"], h_img - 1))
        x2 = min(roi["x"] + roi["w"], w_img)
        y2 = min(roi["y"] + roi["h"], h_img)
        crop  = frame[y:y2, x:x2]
        result = get_mid_bgr(crop)
        color  = classify_color(crop)
        if result:
            B, G, R = result
            print(f"{roi['label']:<8} {B:>6.1f} {G:>6.1f} {R:>6.1f}  {R-B:>+6.1f}  {G-R:>+6.1f}  {G-B:>+6.1f}  {color}")
        else:
            print(f"{roi['label']:<8}  (no mid-brightness pixels)  {color}")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LED color detector via USB camera")
    parser.add_argument("--mode", required=True,
                        choices=["calibrate", "live", "select-rois", "detect", "diagnose"])
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera index (default: 0)")
    parser.add_argument("--profile", default=None,
                        help="Named ROI profile (e.g. 'ports', 'status'). "
                             "Omit to use the default ledcam_rois.json.")
    parser.add_argument("--labels", default="",
                        help="Comma-separated LED labels for select-rois mode "
                             "(e.g. '0/1,0/2,0/3,0/4'). Omit to auto-number.")
    args = parser.parse_args()

    if args.mode == "calibrate":
        mode_calibrate(args)
    elif args.mode == "live":
        mode_live(args)
    elif args.mode == "select-rois":
        mode_select_rois(args)
    elif args.mode == "detect":
        mode_detect(args)
    elif args.mode == "diagnose":
        mode_diagnose(args)


if __name__ == "__main__":
    main()
