"""Chạy tại thư mục server: python -m scripts.prepare_demo --size 1080x1920."""

import argparse
import json

from app.config import settings
from app.media import build_media, run

parser = argparse.ArgumentParser()
parser.add_argument("--seconds", type=float, default=41)
parser.add_argument("--size", default="1920x1080")
parser.add_argument("--no-audio", action="store_true")
parser.add_argument("--id", default="demo")
args = parser.parse_args()
if not args.id.isalnum():
    parser.error("ID chỉ gồm chữ và số")
source = settings.storage / f"{args.id}-source.mp4"
source.parent.mkdir(parents=True, exist_ok=True)
command = [
    settings.ffmpeg_path,
    "-y",
    "-f",
    "lavfi",
    "-i",
    f"testsrc2=size={args.size}:rate=30",
]
if not args.no_audio:
    command += ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000"]
command += [
    "-t",
    str(args.seconds),
    "-c:v",
    "libx264",
    "-preset",
    "ultrafast",
    "-pix_fmt",
    "yuv420p",
]
if not args.no_audio:
    command += ["-c:a", "aac"]
command += [str(source)]
run(command)
manifest = build_media(source, settings.storage / "demo" / args.id / "v1", args.id, "v1")
print(
    json.dumps(
        {
            "id": args.id,
            "duration": manifest["duration"],
            "qualities": [r["id"] for r in manifest["renditions"]],
        }
    )
)
