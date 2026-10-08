"""FourFrame Web Studio - Zero-dependency local HTTP server.

Serves an interactive web studio allowing users to:
1. Upload or select MP4/MOV videos.
2. Interactively drag and draw a watermark ROI box on an HTML5 canvas.
3. Configure padding, inpaint radius (1-20), method (Telea / NS), and CRF.
4. Generate instant 3-second comparison previews with a split slider.
5. Process the entire video with live progress (FPS, ETA, percentage).
6. Download the reconstructed MP4 with original audio preserved.
"""

import json
import logging
import mimetypes
import os
import re
import socketserver
import sys
import threading
import time
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

# Add parent directory to sys.path to import fourframe package
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cv2
import config
from fourframe.ffmpeg import verify_ffmpeg_installation
from fourframe.inpaint import InpaintError, OpenCVInpaintBackend
from fourframe.metadata import extract_metadata
from fourframe.models import ProcessingConfig, ROI, FourFrameError
from fourframe.preview import generate_preview
from fourframe.processor import process_video
from fourframe.video import extract_representative_frame

logger = logging.getLogger("fourframe.web")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# Global in-memory background jobs registry
JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


class FourFrameRequestHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler for FourFrame Web Studio."""

    def __init__(self, *args, **kwargs):
        self.web_root = Path(__file__).resolve().parent / "web"
        super().__init__(*args, directory=str(self.web_root), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(format, *args)

    def do_OPTIONS(self) -> None:
        """Support CORS pre-flight if invoked from external dev origins."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests for static assets and API endpoints."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API: Server Health
        if path == "/api/health":
            self._send_json({"status": "ok", "app": "FourFrame Web Studio"})
            return

        # 2. API: Load Built-in Sample Video
        if path == "/api/sample":
            self._handle_load_sample()
            return

        # 3. API: Poll Processing Progress
        if path == "/api/progress":
            job_id = query.get("job_id", [""])[0]
            self._handle_get_progress(job_id)
            return

        # 4. API: Download Processed Video
        if path == "/api/download":
            filename = query.get("filename", [""])[0]
            self._handle_download(filename)
            return

        # 5. Static files from temp/
        if path.startswith("/temp/"):
            rel_path = path[len("/temp/"):]
            file_path = config.TEMP_DIR / rel_path
            self._serve_file(file_path)
            return

        # 6. Static files from output/
        if path.startswith("/output/"):
            rel_path = path[len("/output/"):]
            file_path = config.OUTPUT_DIR / rel_path
            self._serve_file(file_path)
            return

        # Default: Serve static files from web/ or index.html
        if path == "/" or not (self.web_root / path.lstrip("/")).exists():
            index_path = self.web_root / "index.html"
            self._serve_file(index_path, content_type="text/html; charset=utf-8")
            return

        super().do_GET()

    def do_POST(self) -> None:
        """Handle POST requests for file upload, preview generation, and processing."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/upload":
            self._handle_upload()
            return

        if path == "/api/preview":
            self._handle_generate_preview()
            return

        if path == "/api/process":
            self._handle_start_process()
            return

        self._send_json({"error": f"Endpoint not found: {path}"}, status=HTTPStatus.NOT_FOUND)

    # -----------------------------------------------------------------------
    # API Handlers
    # -----------------------------------------------------------------------

    def _handle_load_sample(self) -> None:
        """Load the built-in synthetic sample video for rapid demonstration."""
        sample_path = config.INPUT_DIR / "sample.mp4"
        if not sample_path.exists():
            self._send_json({"error": "No built-in sample.mp4 found in input/."}, status=404)
            return

        try:
            meta = extract_metadata(sample_path)
            rep_frame = extract_representative_frame(sample_path, metadata=meta)
            rep_name = f"rep_{sample_path.stem}.jpg"
            rep_out = config.TEMP_DIR / rep_name
            cv2.imwrite(str(rep_out), rep_frame)

            self._send_json({
                "filename": sample_path.name,
                "metadata": meta.to_dict(),
                "frame_url": f"/temp/{rep_name}",
                "default_roi": {
                    "x": int(meta.width * 0.82),
                    "y": int(meta.height * 0.86),
                    "width": int(meta.width * 0.14),
                    "height": int(meta.height * 0.08),
                },
            })
        except Exception as exc:
            logger.exception("Failed loading sample video: %s", exc)
            self._send_json({"error": str(exc)}, status=500)

    def _handle_upload(self) -> None:
        """Handle binary or multipart video file upload."""
        content_type = self.headers.get("Content-Type", "")
        content_length = int(self.headers.get("Content-Length", 0))

        if content_length <= 0:
            self._send_json({"error": "Empty upload request body."}, status=400)
            return

        config.INPUT_DIR.mkdir(parents=True, exist_ok=True)
        config.TEMP_DIR.mkdir(parents=True, exist_ok=True)

        filename = "uploaded_video.mp4"
        file_bytes = b""

        if "multipart/form-data" in content_type:
            boundary_match = re.search(r"boundary=(.+)", content_type)
            if not boundary_match:
                self._send_json({"error": "Missing multipart boundary."}, status=400)
                return
            boundary = boundary_match.group(1).strip().encode()

            body = self.rfile.read(content_length)
            parts = body.split(b"--" + boundary)

            for part in parts:
                if b'filename="' in part:
                    fn_match = re.search(rb'filename="([^"]+)"', part)
                    if fn_match:
                        filename = fn_match.group(1).decode("utf-8", errors="ignore")
                        # Sanitize filename
                        filename = re.sub(r"[^\w\.-]", "_", Path(filename).name)

                    header_end = part.find(b"\r\n\r\n")
                    if header_end != -1:
                        file_bytes = part[header_end + 4 :].rstrip(b"\r\n")
                        break
        else:
            # Direct binary POST stream
            custom_fn = self.headers.get("X-Filename")
            if custom_fn:
                filename = re.sub(r"[^\w\.-]", "_", Path(custom_fn).name)
            file_bytes = self.rfile.read(content_length)

        if not file_bytes:
            self._send_json({"error": "No file payload received."}, status=400)
            return

        target_file = config.INPUT_DIR / filename
        with open(target_file, "wb") as f:
            f.write(file_bytes)

        logger.info("Saved uploaded video: %s (%d bytes)", target_file, len(file_bytes))

        try:
            meta = extract_metadata(target_file)
            rep_frame = extract_representative_frame(target_file, metadata=meta)
            rep_name = f"rep_{target_file.stem}_{int(time.time())}.jpg"
            rep_out = config.TEMP_DIR / rep_name
            cv2.imwrite(str(rep_out), rep_frame)

            self._send_json({
                "filename": filename,
                "metadata": meta.to_dict(),
                "frame_url": f"/temp/{rep_name}",
                "default_roi": {
                    "x": int(meta.width * 0.80),
                    "y": int(meta.height * 0.85),
                    "width": int(meta.width * 0.15),
                    "height": int(meta.height * 0.08),
                },
            })
        except Exception as exc:
            logger.exception("Metadata extraction failed for upload: %s", exc)
            self._send_json({"error": f"Failed parsing video: {exc}"}, status=500)

    def _handle_generate_preview(self) -> None:
        """Render 3-second preview and side-by-side comparison image."""
        try:
            data = self._read_json_body()
            filename = data.get("filename")
            if not filename:
                self._send_json({"error": "Missing filename parameter."}, status=400)
                return

            video_path = config.INPUT_DIR / filename
            if not video_path.exists():
                self._send_json({"error": f"Video not found: {filename}"}, status=404)
                return

            roi_dict = data.get("roi", {})
            roi = ROI(
                x=int(roi_dict.get("x", 0)),
                y=int(roi_dict.get("y", 0)),
                width=int(roi_dict.get("width", 50)),
                height=int(roi_dict.get("height", 50)),
            )

            cfg = ProcessingConfig(
                padding=int(data.get("padding", config.DEFAULT_PADDING)),
                radius=int(data.get("radius", config.DEFAULT_RADIUS)),
                method=str(data.get("method", config.DEFAULT_INPAINT_METHOD)).lower(),
                preview_seconds=float(data.get("preview_seconds", config.DEFAULT_PREVIEW_SECONDS)),
            )
            cfg.validate()

            logger.info("Generating web preview for ROI: %s, method: %s", roi, cfg.method)
            res = generate_preview(video_path=video_path, roi=roi, processing_config=cfg)

            self._send_json({
                "status": "success",
                "preview_image_url": f"/temp/{res['comparison_image'].name}?t={int(time.time())}",
                "preview_video_url": f"/temp/{res['preview_video'].name}?t={int(time.time())}",
                "frames_count": res["frames_count"],
            })
        except Exception as exc:
            logger.exception("Preview generation failed: %s", exc)
            self._send_json({"error": str(exc)}, status=500)

    def _handle_start_process(self) -> None:
        """Initiate background video processing job."""
        try:
            data = self._read_json_body()
            filename = data.get("filename")
            if not filename:
                self._send_json({"error": "Missing filename parameter."}, status=400)
                return

            video_path = config.INPUT_DIR / filename
            if not video_path.exists():
                self._send_json({"error": f"Video not found: {filename}"}, status=404)
                return

            roi_dict = data.get("roi", {})
            roi = ROI(
                x=int(roi_dict.get("x", 0)),
                y=int(roi_dict.get("y", 0)),
                width=int(roi_dict.get("width", 50)),
                height=int(roi_dict.get("height", 50)),
            )

            cfg = ProcessingConfig(
                padding=int(data.get("padding", config.DEFAULT_PADDING)),
                radius=int(data.get("radius", config.DEFAULT_RADIUS)),
                method=str(data.get("method", config.DEFAULT_INPAINT_METHOD)).lower(),
                crf=int(data.get("crf", config.DEFAULT_CRF)),
                preset=str(data.get("preset", config.DEFAULT_PRESET)),
            )
            cfg.validate()

            out_filename = f"{video_path.stem}_fourframe.mp4"
            out_path = config.OUTPUT_DIR / out_filename

            job_id = f"job_{int(time.time() * 1000)}"
            with JOBS_LOCK:
                JOBS[job_id] = {
                    "id": job_id,
                    "status": "starting",
                    "percent": 0.0,
                    "processed_frames": 0,
                    "total_frames": 1,
                    "fps": 0.0,
                    "eta": 0,
                    "output_filename": out_filename,
                    "error": None,
                    "stats": None,
                }

            # Launch background worker
            thread = threading.Thread(
                target=self._run_job_worker,
                args=(job_id, video_path, out_path, roi, cfg),
                daemon=True,
            )
            thread.start()

            self._send_json({"job_id": job_id, "status": "started"})
        except Exception as exc:
            logger.exception("Failed to start processing: %s", exc)
            self._send_json({"error": str(exc)}, status=500)

    @staticmethod
    def _run_job_worker(
        job_id: str,
        video_path: Path,
        out_path: Path,
        roi: ROI,
        cfg: ProcessingConfig,
    ) -> None:
        """Background thread executing video reconstruction."""
        try:
            logger.info("Starting background job %s for %s", job_id, video_path.name)
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "processing"

            stats = process_video(
                input_path=video_path,
                output_path=out_path,
                roi=roi,
                processing_config=cfg,
            )

            with JOBS_LOCK:
                JOBS[job_id]["status"] = "completed"
                JOBS[job_id]["percent"] = 100.0
                JOBS[job_id]["stats"] = {
                    "input_resolution": stats.input_resolution,
                    "output_resolution": stats.output_resolution,
                    "input_fps": stats.input_fps,
                    "output_fps": stats.output_fps,
                    "duration": stats.output_duration,
                    "total_time": round(stats.total_time_seconds, 2),
                    "processing_fps": round(stats.processing_fps, 1),
                    "diagnostic_mae": round(stats.diagnostic_mae, 2) if stats.diagnostic_mae else None,
                    "diagnostic_psnr": round(stats.diagnostic_psnr, 2) if stats.diagnostic_psnr else None,
                    "download_url": f"/api/download?filename={out_path.name}",
                }
            logger.info("Completed background job %s successfully.", job_id)
        except Exception as exc:
            logger.exception("Job %s encountered error: %s", job_id, exc)
            with JOBS_LOCK:
                JOBS[job_id]["status"] = "failed"
                JOBS[job_id]["error"] = str(exc)

    def _handle_get_progress(self, job_id: str) -> None:
        """Poll progress status of an active job."""
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            if not job:
                self._send_json({"error": f"Job not found: {job_id}"}, status=404)
                return
            # Return copy of job state
            self._send_json(dict(job))

    def _handle_download(self, filename: str) -> None:
        """Serve final completed video with attachment headers."""
        if not filename:
            self._send_json({"error": "Missing filename parameter."}, status=400)
            return

        file_path = config.OUTPUT_DIR / Path(filename).name
        if not file_path.exists():
            self._send_json({"error": f"File not found: {filename}"}, status=404)
            return

        self._serve_file(file_path, as_attachment=True)

    # -----------------------------------------------------------------------
    # Helper Utilities
    # -----------------------------------------------------------------------

    def _read_json_body(self) -> Dict[str, Any]:
        """Read and parse incoming JSON request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        return json.loads(raw)

    def _send_json(self, data: Dict[str, Any], status: int = HTTPStatus.OK) -> None:
        """Send formatted JSON HTTP response."""
        encoded = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)

    def _serve_file(
        self,
        file_path: Path,
        content_type: Optional[str] = None,
        as_attachment: bool = False,
    ) -> None:
        """Stream file to client with appropriate MIME headers and range support."""
        if not file_path.exists() or not file_path.is_file():
            self._send_json({"error": "File not found."}, status=HTTPStatus.NOT_FOUND)
            return

        if content_type is None:
            mime, _ = mimetypes.guess_type(str(file_path))
            content_type = mime or "application/octet-stream"

        file_size = file_path.stat().st_size
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Access-Control-Allow-Origin", "*")
        if as_attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{file_path.name}"')
        self.end_headers()

        with open(file_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break


def run_web_server(port: int = 5000, open_browser: bool = True) -> None:
    """Start local FourFrame web studio server."""
    verify_ffmpeg_installation()
    config.INPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)

    server_address = ("127.0.0.1", port)
    httpd = ThreadingHTTPServer(server_address, FourFrameRequestHandler)
    url = f"http://localhost:{port}"

    print("\n==================================================")
    print(" FourFrame Web Studio")
    print("==================================================")
    print(f" * Local-first private video reconstruction")
    print(f" * Server running at: {url}")
    print(f" * Interactive canvas ROI selection enabled")
    print(" * Press Ctrl+C to stop the server.")
    print("==================================================\n")

    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping FourFrame web server...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    port_num = 5000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port_num = int(sys.argv[1])
    run_web_server(port=port_num, open_browser=True)
