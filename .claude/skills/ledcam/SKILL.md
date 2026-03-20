---
name: ledcam
description: USB camera LED color detection for AXN-2020 front panel — calibrate, ROI selection, and live detect (green/amber/off). Use when the user wants to detect or verify LED states on the AXN-2020 device.
---

# ledcam

Captures the AXN-2020 front-panel LED states using a USB camera connected to the Host PC. Detects LED colors (green / amber / off) by analyzing image regions you define once during setup.

## Environment Variables

```
SCRIPT      = .claude/skills/ledcam/ledcam.py
CAMERA      = 0               (USB camera index)
ROIS        = ./tmp/ledcam_rois[_<profile>].json
DETECT_OUT  = ./tmp/ledcam_detect[_<profile>]_<YYYYMMDD_HHMMSS>.jpg
```

## Prerequisites

OpenCV must be installed in WinPython (one-time):
```bash
"$PYTHON" -m pip install opencv-python
```

---

## Camera Settings File

`./tmp/camera_settings.json` stores calibrated camera parameters and is loaded automatically by all modes. Created/updated by pressing **S** in `--mode calibrate`.

| Key | Range | Default | Notes |
|-----|-------|---------|-------|
| Focus | 0–255 | 120 | Manual focus distance |
| Exposure | −13–0 | −6 | Negative = shorter exposure |
| Brightness | 0–255 | 128 | |
| Contrast | 0–255 | 128 | |
| Saturation | 0–255 | 128 | |
| Gain | 0–255 | 0 | |
| WhiteBalance | 2000–6500 | 5000 | Kelvin |
| Sharpness | 0–255 | 128 | |
| Backlight | 0–3 | 0 | |

---

## Step-by-Step Workflow

### Step 0a — Calibrate camera settings (one-time)

Opens a live feed with sliders for all camera parameters. Adjust until the LEDs look correct, then press **S** to save to `./tmp/camera_settings.json`. Press **Q** or **ESC** to quit.

```bash
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode calibrate
```

### Step 0b — Live feed (optional check)

Opens a continuous live window using saved camera settings. Press **Q** or **ESC** to quit.

```bash
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode live
```

Use this to visually verify the camera is aimed correctly before running detection.

### Step 1 — Verify camera is available

```bash
"$PYTHON" -c "
import cv2
cap = cv2.VideoCapture(0)
print('Camera 0: available' if cap.isOpened() else 'Camera 0: NOT found')
cap.release()
"
```

### Step 2 — Select ROIs (one-time setup)

Captures a frame with saved camera settings, then opens the ROI selection window.

**Open-ended (no labels needed — draw as many as you want):**
```bash
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode select-rois
```

**With a named profile** (saves to `./tmp/ledcam_rois_<profile>.json`):
```bash
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode select-rois --profile ports
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode select-rois --profile status
```

**Pre-labelled (port names known in advance):**
```bash
# Pass the exact labels you need — the number of labels is not fixed
"$PYTHON" .claude/skills/ledcam/ledcam.py \
  --mode select-rois --labels "0/1,0/2,0/3,0/4"
```

**In the ROI selection window:**
- Click and drag to draw a box around each LED
- Press **ENTER** or **SPACE** to confirm each box
- Press **R** to redo the current box
- Press **ESC** when finished (open-ended) or to finish early (pre-labelled)

In open-ended mode ROIs are auto-numbered 1, 2, 3, …

Saves ROI coordinates to `./tmp/ledcam_rois.json` and an annotated reference snapshot.

> ROI JSON can be hand-edited if adjustments are needed.

### Step 3 — Detect LED colors

Opens a **live window for 3 seconds**, refreshing ROI color labels every 500ms, then saves the final annotated frame and closes automatically.

```bash
# Default profile
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode detect

# Named profile
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode detect --profile ports
```

**Example output:**
```
Label          Color
----------------------
1              green
2              green
3              green

Annotated frame → ./tmp/ledcam_detect_20260308_143052.jpg
  (with --profile ports) → ./tmp/ledcam_detect_ports_20260308_143052.jpg

Summary: {'green': 3}
```

Saves an annotated image with bounding boxes and color labels to `./tmp/ledcam_detect[_<profile>]_<YYYYMMDD_HHMMSS>.jpg`.

---

## Color Detection Ranges (HSV)

| Color  | OpenCV H range | S min | V min | Notes |
|--------|---------------|-------|-------|-------|
| Green  | 35 – 90       | 60    | 60    | ~120–170° in standard degrees |
| Amber  | 8 – 28        | 100   | 80    | ~16–56° in standard degrees |
| Off    | any           | any   | < 50  | Dim/dark pixel |

If detection is wrong, edit the HSV thresholds in `ledcam.py → classify_color()`.

---

## Complete Example — Verify LEDs After `diag led test`

```bash
# 1. Set LEDs via CLI (e.g. via checkspec skill)
#    diag led test port all color green

# 2. Select ROIs (first time only — or if camera moved)
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode select-rois

# 3. Detect
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode detect
```

With a named profile:
```bash
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode select-rois --profile ports
"$PYTHON" .claude/skills/ledcam/ledcam.py --mode detect --profile ports
```

---

## Skill Workflow (for Claude)

1. **Check camera** — verify index 0 is available
2. **Live feed** — if user wants to check the view, run `--mode live`; user presses Q/ESC to quit
3. **Check ROIs** — check if the ROI file for the requested profile exists:
   - default: `./tmp/ledcam_rois.json`
   - named profile: `./tmp/ledcam_rois_<profile>.json`
   If it exists, skip to step 5
4. **Select ROIs** — run `--mode select-rois [--profile <name>]`. Do NOT assume the number of ports — use open-ended mode (no `--labels`) so the user draws as many ROIs as they need, or pass `--labels` only if the user specifies exact port names. Instruct user to draw boxes, press ENTER to confirm each, ESC when done.
5. **Detect** — run `--mode detect [--profile <name>]`; a live window opens for 3 seconds then closes automatically; report table and annotated image path

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `Cannot open camera index 0` | Camera not connected or in use | Check USB connection; close other apps using camera |
| All colors show `unknown` | ROIs in wrong position (camera moved) | Re-run `--mode select-rois` |
| Green detected as `unknown` | LED too dim or HSV range off | Adjust `green_mask` H/S/V thresholds in `ledcam.py` |
| Amber detected as `unknown` | LED hue slightly outside range | Adjust `amber_mask` H range (try H 5–35) |
| OpenCV window doesn't appear | Running headless or RDP without display | Run select-rois directly on the Windows desktop session |
