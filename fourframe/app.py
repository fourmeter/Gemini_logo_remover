"""FourFrame: Command-Line Interface and Interactive Workflow Runner."""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from config import (
    ALLOWED_METHODS,
    DEFAULT_CRF,
    DEFAULT_METHOD,
    DEFAULT_PADDING,
    DEFAULT_PRESET,
    DEFAULT_PREVIEW_SECONDS,
    DEFAULT_RADIUS,
    LOG_FORMAT,
    OUTPUT_DIR,
    TEMP_DIR,
)
from fourframe.ffmpeg import verify_ffmpeg_installation
from fourframe.inpaint import OpenCVInpaintBackend
from fourframe.metadata import extract_metadata
from fourframe.models import (
    FFmpegNotFoundError,
    FourFrameError,
    ProcessingConfig,
    ROI,
    ROIValidationError,
    UserCancelledError,
    VideoMetadata,
)
from fourframe.preview import generate_preview
from fourframe.processor import process_video
from fourframe.selection import ManualDetectionStrategy, select_watermark_roi
from fourframe.video import extract_representative_frame

# Configure root logger
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger("fourframe")


def parse_cli_roi(roi_str: str) -> ROI:
    """Parse comma-separated 'x,y,w,h' string into an ROI object."""
    try:
        parts = [int(p.strip()) for p in roi_str.split(",")]
        if len(parts) != 4:
            raise ValueError()
        return ROI(x=parts[0], y=parts[1], width=parts[2], height=parts[3])
    except Exception as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid ROI format '{roi_str}'. Expected format: 'x,y,width,height' (e.g. 1650,960,120,50)"
        ) from exc


def parameter_tuning_menu(config: ProcessingConfig) -> bool:
    """Interactive menu allowing the user to tune parameters before reprocessing preview.

    Returns:
        True if parameters were updated and preview should re-run, False to cancel.
    """
    while True:
        print("\n" + "-" * 35)
        print(" PARAMETER TUNING MENU")
        print("-" * 35)
        print(f"1. Start processing with current settings")
        print(f"2. Change padding (current: {config.padding}px)")
        print(f"3. Change inpainting radius (current: {config.radius})")
        print(f"4. Change inpaint method (current: '{config.method}')")
        print("5. Return / Re-run Preview")
        print("6. Cancel application")

        choice = input("\nSelect an option [1-6]: ").strip()

        if choice == "1":
            return False  # Proceed directly
        elif choice == "2":
            val = input(f"Enter new padding in pixels (0..50) [{config.padding}]: ").strip()
            if val.isdigit():
                config.padding = int(val)
                print(f"-> Padding updated to {config.padding}")
        elif choice == "3":
            val = input(f"Enter new radius (1..20) [{config.radius}]: ").strip()
            if val.isdigit():
                config.radius = int(val)
                print(f"-> Radius updated to {config.radius}")
        elif choice == "4":
            print(f"Available methods: {', '.join(ALLOWED_METHODS)}")
            val = input(f"Enter method name [{config.method}]: ").strip().lower()
            if val in ALLOWED_METHODS:
                config.method = val
                print(f"-> Method updated to '{config.method}'")
            else:
                print("Invalid method choice.")
        elif choice in ("5", ""):
            return True  # Re-run preview
        elif choice == "6":
            raise UserCancelledError("User cancelled in parameter tuning menu.")
        else:
            print("Invalid selection. Please choose 1-6.")


def run_pipeline(
    input_path: Path,
    output_path: Optional[Path] = None,
    config: Optional[ProcessingConfig] = None,
    explicit_roi: Optional[ROI] = None,
    non_interactive: bool = False,
    keep_temp: bool = False,
) -> None:
    """Execute the interactive FourFrame watermark removal workflow."""
    cfg = config or ProcessingConfig()
    cfg.validate()

    # 1. Startup sanity checks
    verify_ffmpeg_installation()

    in_file = Path(input_path).resolve()
    if not in_file.is_file():
        raise FileNotFoundError(f"Input file not found: {in_file}")

    if output_path:
        out_file = Path(output_path).resolve()
    else:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_file = OUTPUT_DIR / f"{in_file.stem}_fourframe.mp4"

    # 2. Print initial header and metadata
    print("\nFourFrame")
    print("-" * 35)
    print("Loading video...\n")

    metadata: VideoMetadata = extract_metadata(in_file)
    print(f"Resolution: {metadata.width}x{metadata.height}")
    print(f"FPS:        {metadata.fps:.2f}")
    print(f"Duration:   {metadata.duration:.1f} sec")
    print(f"Audio:      {'Yes' if metadata.has_audio else 'No'}\n")

    # 3. Watermark ROI selection
    rep_frame = extract_representative_frame(in_file, metadata)

    current_roi: ROI
    if explicit_roi is not None:
        explicit_roi.validate_bounds(metadata.width, metadata.height)
        current_roi = explicit_roi
        logger.info("Using CLI-specified watermark ROI: %s", current_roi.to_dict())
    else:
        print("Select the watermark region.")
        current_roi = select_watermark_roi(rep_frame)

    print("\nSelected:")
    print(f"x={current_roi.x}")
    print(f"y={current_roi.y}")
    print(f"width={current_roi.width}")
    print(f"height={current_roi.height}\n")

    inpaint_backend = OpenCVInpaintBackend()

    # 4. Preview and Approval Loop
    while True:
        print(f"Creating {cfg.preview_seconds:.1f}-second preview...")
        prev_vid, prev_img = generate_preview(
            video_path=in_file,
            metadata=metadata,
            roi=current_roi,
            config=cfg,
            inpaint_backend=inpaint_backend,
            preview_output_dir=TEMP_DIR,
            interactive_display=not non_interactive,
        )
        print("Preview complete.")

        if non_interactive:
            logger.info("Non-interactive mode: Auto-approving preview.")
            break

        # Prompt user approval
        print("\nApprove preview?")
        print("[Y] Yes (Start processing)")
        print("[N] No  (Tune parameters)")
        print("[R] Reselect watermark")
        print("[C] Cancel")

        ans = input("\nChoice [Y/N/R/C]: ").strip().upper()

        if ans in ("Y", ""):
            break
        elif ans == "R":
            print("\nReselecting watermark region...")
            current_roi = select_watermark_roi(rep_frame)
            print("\nSelected:")
            print(f"x={current_roi.x}")
            print(f"y={current_roi.y}")
            print(f"width={current_roi.width}")
            print(f"height={current_roi.height}\n")
            continue
        elif ans == "N":
            rerun_preview = parameter_tuning_menu(cfg)
            if not rerun_preview:
                break
        elif ans == "C":
            raise UserCancelledError("Workflow cancelled by user.")
        else:
            print("Invalid choice. Please enter Y, N, R, or C.")

    # 5. Full processing
    detection_strategy = ManualDetectionStrategy(current_roi)
    stats = process_video(
        input_path=in_file,
        output_path=out_file,
        detection_strategy=detection_strategy,
        config=cfg,
        metadata=metadata,
        inpaint_backend=inpaint_backend,
        temp_dir=TEMP_DIR,
        keep_temp=keep_temp,
    )

    # 6. Report final statistics
    print("\n" + stats.format_summary())


def main() -> None:
    """CLI Argument Parser and entry point."""
    parser = argparse.ArgumentParser(
        prog="FourFrame",
        description="Local-first visible video watermark remover using OpenCV and FFmpeg.",
        epilog="Note: This tool reconstructs user-selected visible regions locally. "
        "It does NOT alter or strip invisible provenance/watermarking systems.",
    )

    parser.add_argument(
        "--web",
        action="store_true",
        help="Launch the interactive FourFrame Web Studio in your browser",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to bind the Web Studio server (default: 5000)",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        default=None,
        help="Path to input video file (e.g. input/sample.mp4)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to output video file (defaults to output/<name>_fourframe.mp4)",
    )
    parser.add_argument(
        "--padding",
        "-p",
        type=int,
        default=DEFAULT_PADDING,
        help=f"Mask boundary padding in pixels (default: {DEFAULT_PADDING})",
    )
    parser.add_argument(
        "--radius",
        "-r",
        type=int,
        default=DEFAULT_RADIUS,
        help=f"Inpainting radius (1..20, default: {DEFAULT_RADIUS})",
    )
    parser.add_argument(
        "--method",
        "-m",
        type=str,
        default=DEFAULT_METHOD,
        choices=ALLOWED_METHODS,
        help=f"Inpainting algorithm (default: '{DEFAULT_METHOD}')",
    )
    parser.add_argument(
        "--preview-seconds",
        type=float,
        default=DEFAULT_PREVIEW_SECONDS,
        help=f"Preview clip length in seconds (default: {DEFAULT_PREVIEW_SECONDS})",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=DEFAULT_CRF,
        help=f"FFmpeg x264 CRF quality (16..28, lower=better, default: {DEFAULT_CRF})",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default=DEFAULT_PRESET,
        help=f"FFmpeg x264 encoding preset (default: '{DEFAULT_PRESET}')",
    )
    parser.add_argument(
        "--roi",
        type=parse_cli_roi,
        default=None,
        help="Pre-defined ROI as 'x,y,width,height' to bypass interactive GUI selection",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Automatically approve preview and proceed to processing (useful for scripting)",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Do not delete intermediate video files after muxing",
    )

    args = parser.parse_args()

    if args.web:
        from web_server import run_web_server
        try:
            run_web_server(port=args.port, open_browser=True)
        except KeyboardInterrupt:
            print("\nWeb studio stopped.\n")
        sys.exit(0)

    if not args.input:
        parser.error("the following arguments are required: -i/--input (or use --web to open the Web Studio)")

    config = ProcessingConfig(
        padding=args.padding,
        radius=args.radius,
        method=args.method,
        crf=args.crf,
        preset=args.preset,
        preview_seconds=args.preview_seconds,
    )

    try:
        run_pipeline(
            input_path=args.input,
            output_path=args.output,
            config=config,
            explicit_roi=args.roi,
            non_interactive=args.non_interactive,
            keep_temp=args.keep_temp,
        )
    except FFmpegNotFoundError as exc:
        print(f"\n[FFmpeg Error]: {exc}\n", file=sys.stderr)
        sys.exit(2)
    except UserCancelledError as exc:
        print(f"\n[Cancelled]: {exc}\n")
        sys.exit(0)
    except FourFrameError as exc:
        print(f"\n[Processing Error]: {exc}\n", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[Interrupted]: Workflow stopped by user.\n")
        sys.exit(130)


if __name__ == "__main__":
    main()
