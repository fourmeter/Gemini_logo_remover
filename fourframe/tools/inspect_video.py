"""CLI utility to inspect video metadata using FFprobe."""

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fourframe.ffmpeg import verify_ffmpeg_installation
from fourframe.metadata import extract_metadata


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FourFrame Video Metadata Inspector (FFprobe)",
    )
    parser.add_argument("video_path", type=Path, help="Path to video file")
    parser.add_argument("--json", action="store_true", help="Output raw JSON format")

    args = parser.parse_args()

    try:
        verify_ffmpeg_installation()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        metadata = extract_metadata(args.video_path)
    except Exception as exc:
        print(f"Metadata extraction failed: {exc}", file=sys.stderr)
        sys.exit(1)

    data = metadata.to_dict()

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print("\n========================================")
        print(" FourFrame Video Metadata")
        print("========================================")
        print(f" Filename:      {data['filename']}")
        print(f" Resolution:    {data['width']}x{data['height']}")
        print(f" Framerate:     {data['fps']} FPS")
        print(f" Total Frames:  {data['frame_count']}")
        print(f" Duration:      {data['duration']}s")
        print(f" Video Codec:   {data['video_codec'] or 'unknown'}")
        print(f" Pixel Format:  {data['pixel_format'] or 'unknown'}")
        print(f" Audio Present: {'Yes' if data['has_audio'] else 'No'}")
        if data['has_audio']:
            print(f" Audio Codec:   {data['audio_codec']}")
        print("========================================\n")


if __name__ == "__main__":
    main()
