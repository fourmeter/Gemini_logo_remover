# FourFrame — Local-First Visible Video Watermark Remover

FourFrame is a production-oriented, local-first Python application designed for reconstructing user-selected visible watermark and logo regions in videos using **OpenCV** and **FFmpeg**.

---

## 1. What FourFrame Does

FourFrame removes visible watermarks and logos from MP4 and MOV videos entirely on your local machine:
- **Zero Cloud Uploads**: 100% private. No external APIs, no remote processing, no analytics.
- **Accurate Inpainting**: Reconstructs background textures using Fast Marching (Telea) or Navier-Stokes PDE methods.
- **Audio Preservation**: Preserves the original audio stream bit-for-bit without lossy re-encoding where possible.
- **Aspect Ratio & Framerate Retention**: Retains native dimensions, timebase, and stream characteristics.
- **Interactive Preview & Approval**: Generates a fast 3-second comparison preview allowing parameter tuning before committing to the full video.

> **Provenance Notice**:
> FourFrame is strictly intended for reconstructing user-selected, visible regions of video files. It **does NOT** attempt to alter, bypass, or strip invisible provenance metadata or attribution watermarks (such as SynthID or C2PA credentials). Output files should never be described or marketed as "provenance-free."

---

## 2. Architecture & Pipeline

```text
INPUT VIDEO (MP4/MOV)
         │
         ▼
[FFprobe Metadata Inspection]  ──► Validate resolution, framerate, duration, audio
         │
         ▼
[Representative Frame Extraction] ──► Extract informative frame at ~10% timestamp
         │
         ▼
[Manual Watermark ROI Selection]  ──► OpenCV interactive bounding box selection
         │
         ▼
[Mask Generation & Padding]    ──► Configurable boundary expansion (default 5px)
         │
         ▼
[3-Second Preview Generation]  ──► Side-by-side [Original | Mask | Inpainted]
         │
         ▼
[User Approval / Tuning Loop]  ──► Interactive parameter adjustments (radius/method)
         │  (Approved)
         ▼
[Frame-by-Frame Processing]    ──► Low-memory streaming loop (cv2.inpaint)
         │
         ▼
[Temporary Processed Video]    ──► Intermediate video stored in temp/
         │
         ▼
[FFmpeg Audio Muxing]          ──► Multiplex original audio (-map 0:v -map 1:a?)
         │
         ▼
[Validation & Cleanup]         ──► FFprobe integrity verification & temp deletion
         │
         ▼
FINAL OUTPUT MP4
```

---

## 3. Project Structure

```text
fourframe/
│
├── app.py                     # Main CLI and interactive workflow runner
├── requirements.txt           # Python dependencies (opencv-python, numpy)
├── README.md                  # Complete documentation and user guide
├── config.py                  # Default constants, bounds, and directory paths
│
├── fourframe/                 # Core engine package
│   ├── __init__.py            # Package exports
│   ├── video.py               # VideoCapture/VideoWriter I/O and frame streaming
│   ├── metadata.py            # FFprobe metadata parser with OpenCV fallbacks
│   ├── selection.py           # ROI selector and DetectionStrategy interface
│   ├── mask.py                # Binary uint8 mask generation & visualization
│   ├── inpaint.py             # InpaintBackend and OpenCV inpaint kernels
│   ├── preview.py             # 3-second preview generator & comparison tiling
│   ├── processor.py           # Frame-by-frame streaming pipeline
│   ├── ffmpeg.py              # FFmpeg audio muxing & output validation
│   ├── progress.py            # Terminal progress bar with FPS and ETA
│   └── models.py              # Dataclasses (ROI, VideoMetadata, ProcessingConfig)
│
├── tools/
│   ├── inspect_video.py       # Standalone video metadata inspection tool
│   └── create_synthetic_sample.py # Test video generator with simulated watermark
│
├── tests/
│   └── test_fourframe.py      # Automated unit test suite
│
├── input/                     # Default directory for source videos
├── output/                    # Default directory for cleaned videos
└── temp/                      # Intermediate working files (auto-cleaned)
```

---

## 4. System Prerequisites & FFmpeg Installation

FourFrame requires external system binaries for **FFmpeg** and **FFprobe** (version 4.4+ recommended).

### Windows
Install via Windows Package Manager (`winget`) or Chocolatey:
```powershell
winget install Gyan.FFmpeg
# or
choco install ffmpeg
```
*Verify that `ffmpeg -version` and `ffprobe -version` execute in PowerShell.*

### macOS
Install via Homebrew:
```bash
brew install ffmpeg
```

### Linux (Ubuntu/Debian)
```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

---

## 5. Python Installation

FourFrame supports Python 3.11+.

```bash
cd fourframe

# Optional: Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 6. Running the Application

### Interactive Web Studio (Browser UI)
Launch the browser-based studio with drag-and-drop video upload and interactive canvas ROI selection:
```bash
python app.py --web
# or
python web_server.py
```
This automatically opens `http://localhost:5000` with real-time ROI drawing, instant 3-second comparison previews, and progress streaming.

### CLI Usage (Terminal & OpenCV Window)
Place your video in `input/` and run:
```bash
python app.py --input input/sample.mp4
```

### Customized Run
```bash
python app.py \
    --input input/sample.mp4 \
    --output output/cleaned_video.mp4 \
    --padding 6 \
    --radius 3 \
    --method telea \
    --preview-seconds 3 \
    --crf 18 \
    --preset medium
```

### Scripted / Non-Interactive Mode
To bypass the interactive GUI selection and auto-approve the preview:
```bash
python app.py \
    --input input/sample.mp4 \
    --roi 1050,620,180,60 \
    --non-interactive
```

---

## 7. Manual Watermark Selection

When started in interactive mode:
1. FourFrame reads video metadata and extracts a representative frame (avoiding black title cards).
2. An OpenCV GUI window opens displaying the frame:
   - **Click & Drag**: Draw a bounding box tightly around the visible watermark.
   - **SPACE or ENTER**: Confirm selection.
   - **C or ESC**: Cancel selection.
3. Coordinates are validated to ensure `x >= 0`, `y >= 0`, `w > 0`, `h > 0` and that the box remains inside the frame boundaries.

---

## 8. Configuration Options

| Flag | Default | Allowed Values | Description |
|---|---|---|---|
| `--input, -i` | *Required* | File path | Path to source MP4/MOV file |
| `--output, -o` | `output/<name>_fourframe.mp4` | File path | Destination path for output |
| `--padding, -p` | `5` | `0 .. 50` | Extra pixel padding added to each side of ROI |
| `--radius, -r` | `3` | `1 .. 20` | Inpainting neighborhood radius |
| `--method, -m` | `telea` | `telea`, `ns` | Inpainting algorithm (Telea or Navier-Stokes) |
| `--preview-seconds` | `3.0` | `> 0` | Duration of preview clip in seconds |
| `--crf` | `18` | `16 .. 28` | x264 quality factor (lower = higher quality) |
| `--preset` | `medium` | `ultrafast` .. `veryslow` | x264 compression efficiency preset |
| `--roi` | `None` | `x,y,w,h` | Explicit ROI string (e.g. `1050,620,180,60`) |
| `--non-interactive` | `False` | Flag | Auto-approve preview and execute immediately |
| `--keep-temp` | `False` | Flag | Retain intermediate video file in `temp/` |

---

## 9. Inpainting Algorithms Explained

### 1. `telea` (Fast Marching Method, Alexandru Telea)
- Propagates color and image gradients from the boundary of the mask inward.
- Fast, smooth, and handles text watermarks over uniform or soft-gradient backgrounds well.

### 2. `ns` (Navier-Stokes Fluid Dynamics)
- Uses partial differential equations based on fluid dynamics to propagate isophote lines (lines of equal intensity) into the hole.
- Better suited for textured, non-uniform backgrounds where edge continuity is important.

---

## 10. Interactive Preview & Parameter Tuning

Before running the full video, FourFrame renders a short 3-second preview:
1. A comparison composite image is displayed and saved to `temp/preview_comparison.png`:
   - `[ 1. Original | 2. Mask Overlay (Red) | 3. Inpainted Preview ]`
2. An interactive terminal prompt appears:
   ```text
   Approve preview?
   [Y] Yes (Start processing)
   [N] No  (Tune parameters)
   [R] Reselect watermark
   [C] Cancel
   ```
3. Selecting `[N]` opens the parameter tuning menu:
   - Modify padding (0 to 50 px)
   - Change inpainting radius (1 to 20)
   - Switch between `telea` and `ns`
   - Re-evaluate the preview instantly

---

## 11. Testing and Verification

Run the comprehensive unit test suite:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

Inspect metadata of any video:
```bash
python tools/inspect_video.py input/sample.mp4
# Or in JSON format:
python tools/inspect_video.py input/sample.mp4 --json
```

Generate a synthetic demo video for quick experimentation:
```bash
python tools/create_synthetic_sample.py --output input/sample.mp4 --duration 3
```

---

## 12. Future Tracking Architecture

FourFrame V1 uses the `ManualDetectionStrategy`, which assumes the watermark remains in a fixed position across the duration of the video.

The codebase is built on an extensible `DetectionStrategy` pattern:

```python
class DetectionStrategy(ABC):
    @abstractmethod
    def initialize(self, frame: np.ndarray) -> None:
        pass

    @abstractmethod
    def update(self, frame: np.ndarray) -> ROI:
        pass

    @abstractmethod
    def get_roi(self) -> ROI:
        pass
```

### Adding an OpenCV Tracker (CSRT / KCF) in V2
To support moving watermarks, you can implement a new strategy without modifying any frame processing or FFmpeg muxing code:

```python
class OpenCVTrackerStrategy(DetectionStrategy):
    def __init__(self, tracker_type: str = "CSRT"):
        self.tracker_type = tracker_type
        self.tracker = None
        self.roi = None

    def initialize(self, frame: np.ndarray) -> None:
        self.roi = select_watermark_roi(frame)
        self.tracker = cv2.TrackerCSRT_create()
        self.tracker.init(frame, (self.roi.x, self.roi.y, self.roi.width, self.roi.height))

    def update(self, frame: np.ndarray) -> ROI:
        success, box = self.tracker.update(frame)
        if success:
            x, y, w, h = [int(v) for v in box]
            self.roi = ROI(x=x, y=y, width=w, height=h)
        return self.roi

    def get_roi(self) -> ROI:
        return self.roi
```

---

## 13. Limitations & Troubleshooting

- **Fixed Location (V1)**: The watermark must remain in the same location throughout the video. If the camera pans across drastically different backgrounds, `ns` with a small radius (2-3) often produces the cleanest output.
- **Large Watermarks**: Large watermarks (> 25% of the frame) will produce blur with classical inpainting. Neural diffusion models (planned for V3) are required for massive area reconstruction.
- **`[FFmpeg Error]: Binary 'ffmpeg' is not accessible`**: Ensure FFmpeg is installed and added to your system `PATH`. Restart your terminal after installing.
- **Audio Out of Sync**: FourFrame preserves the native frame rate and duration metadata to ensure synchronous audio-video multiplexing.
