"""FFmpeg đóng gói media; Python điều phối và đọc MPD XML để tạo manifest JSON."""
import json
import math
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from app.config import settings

NS = {"d": "urn:mpeg:dash:schema:mpd:2011"}


def run(command: list[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr[-3500:] or "Lệnh xử lý media thất bại")
    return result.stdout


def probe(path: Path) -> dict:
    data = json.loads(run([settings.ffprobe_path, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]))
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    if not video or not math.isfinite(float(data["format"].get("duration", 0))) or float(data["format"].get("duration", 0)) <= 0:
        raise ValueError("File không có video hoặc không xác định được thời lượng")
    return data


def dimensions(stream: dict) -> tuple[int, int]:
    width, height = stream["width"], stream["height"]
    rotation = next((int(s.get("rotation", 0)) for s in stream.get("side_data_list", []) if "rotation" in s), 0)
    if abs(rotation) % 180 == 90:
        width, height = height, width
    return width, height


def rendition_sizes(width: int, height: int) -> list[tuple[int, int, int]]:
    short = min(width, height)
    levels = [p for p in (480, 720, 1080) if p <= short] or [short]
    return [(p, max(2, int(width * p / short) // 2 * 2), max(2, int(height * p / short) // 2 * 2)) for p in levels]


def parse_mpd(path: Path, url_prefix: str, quality: str) -> dict:
    root = ET.parse(path).getroot()
    adaptation = root.find("d:Period/d:AdaptationSet", NS)
    if adaptation is None:
        raise ValueError("MPD không có AdaptationSet")
    rep = adaptation.find("d:Representation", NS)
    if rep is None:
        raise ValueError("MPD không có Representation")
    template = rep.find("d:SegmentTemplate", NS)
    if template is None:
        template = adaptation.find("d:SegmentTemplate", NS)
    if template is None:
        raise ValueError("MPD thiếu SegmentTemplate")
    scale = int(template.get("timescale", "1"))
    cursor = 0
    index = int(template.get("startNumber", "1"))
    segments = []
    timeline = template.find("d:SegmentTimeline", NS)
    if timeline is None:
        raise ValueError("MPD thiếu timeline thực tế")
    for item in timeline:
        cursor = int(item.get("t", cursor))
        duration = int(item.attrib["d"])
        repeat = int(item.get("r", "0"))
        if repeat < 0:
            raise ValueError("Không hỗ trợ timeline vô hạn cho video-on-demand")
        for _ in range(repeat + 1):
            # Tên cố định ở lệnh FFmpeg; không tự phân tích container MP4.
            filename = f"seg-{index:05d}.m4s"
            size = (path.parent / filename).stat().st_size
            if size <= 0:
                raise ValueError("Segment rỗng")
            segments.append({"index": len(segments), "start": cursor / scale, "duration": duration / scale, "bytes": size, "url": f"{url_prefix}/{filename}"})
            cursor += duration
            index += 1
    init = path.parent / "init.mp4"
    if not init.is_file() or not segments:
        raise ValueError("Thiếu initialization segment hoặc media segment")
    mime = rep.get("mimeType", adaptation.get("mimeType", "video/mp4"))
    return {"id": quality, "width": int(rep.get("width", "0")), "height": int(rep.get("height", "0")), "mime": mime,
            "codec": rep.attrib["codecs"], "bitrate": int(rep.attrib["bandwidth"]), "init_url": f"{url_prefix}/init.mp4", "segments": segments}


def build_media(source: Path, output: Path, video_id: str, generation: str) -> dict:
    info = probe(source)
    stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    width, height = dimensions(stream)
    audio_present = any(s["codec_type"] == "audio" for s in info["streams"])
    output.mkdir(parents=True, exist_ok=False)
    rates = {int(k): int(v) for k, v in (pair.split(":") for pair in settings.video_bitrates.split(","))}
    base = f"/api/media/{video_id}/{generation}"

    def encode(folder: str, args: list[str]) -> dict:
        target = output / folder
        target.mkdir()
        run([settings.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), *args,
             "-f", "dash", "-seg_duration", str(settings.segment_seconds), "-use_template", "1", "-use_timeline", "1",
             "-init_seg_name", "init.mp4", "-media_seg_name", "seg-$Number%05d$.m4s", str(target / "index.mpd")])
        return parse_mpd(target / "index.mpd", f"{base}/{folder}", folder)

    videos = []
    for label, w, h in rendition_sizes(width, height):
        rate = rates.get(label, min(rates.values()))
        track = encode(f"{label}p", ["-map", "0:v:0", "-an", "-vf", f"scale={w}:{h},setsar=1,fps=30",
            "-c:v", "libx264", "-preset", "fast", "-profile:v", "high", "-level:v", "4.1", "-pix_fmt", "yuv420p",
            "-b:v", str(rate), "-maxrate", str(rate), "-bufsize", str(rate * 2), "-g", str(30 * settings.segment_seconds),
            "-keyint_min", str(30 * settings.segment_seconds), "-sc_threshold", "0", "-force_key_frames", f"expr:gte(t,n_forced*{settings.segment_seconds})"])
        track["video_bitrate"] = track["bitrate"]
        videos.append(track)
    audio = encode("audio", ["-map", "0:a:0", "-vn", "-c:a", "aac", "-b:a", str(settings.audio_bitrate), "-ar", "48000", "-ac", "2"]) if audio_present else None
    reference = videos[0]["segments"]
    for track in videos:
        if len(track["segments"]) != len(reference) or any(abs(a["start"] - b["start"]) > 0.04 or abs(a["duration"] - b["duration"]) > 0.04 for a, b in zip(reference, track["segments"])):
            raise ValueError("Ranh giới segment giữa các chất lượng không khớp")
        # ABR dùng ít nhất bitrate encode và bitrate tổng trung bình đo từ đầu ra.
        total_bytes = sum(s["bytes"] for s in track["segments"])
        duration = sum(s["duration"] for s in track["segments"])
        track["bitrate"] = max(track["video_bitrate"], math.ceil(total_bytes * 8 / duration)) + (audio["bitrate"] if audio else 0)
    duration = reference[-1]["start"] + reference[-1]["duration"]
    if abs(duration - float(info["format"]["duration"])) > 0.25:
        raise ValueError("Timeline đầu ra khác thời lượng nguồn quá mức cho phép")
    run([settings.ffmpeg_path, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-frames:v", "1", "-vf", "scale=640:-2", str(output / "thumbnail.jpg")])
    manifest = {"version": 1, "video_id": video_id, "duration": duration, "renditions": videos, "audio": audio}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
