import subprocess
import os
import srt
from datetime import timedelta

def generate_srt(translation, output_dir):
    subs = []
    for i, seg in enumerate(translation["segments"], 1):
        start = timedelta(seconds=seg["start"])
        end = timedelta(seconds=seg["end"])
        subs.append(srt.Subtitle(index=i, start=start, end=end, content=seg["text"].strip()))
    srt_path = os.path.join(output_dir, "subtitles.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(subs))
    return srt_path

def escape_for_drawtext(text):
    """Escape text for ffmpeg drawtext filter."""
    # Remove/replace problematic characters
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("=", "\\=")
    text = text.replace("%", "\\%")
    text = text.replace("[", "\\[")
    text = text.replace("]", "\\]")
    text = text.replace(",", "\\,")
    text = text.replace(";", "\\;")
    # Remove any other non-printable or problematic chars
    text = "".join(c for c in text if c.isprintable() or c.isspace())
    return text.strip()

def burn(video_path, translation, voiceover_path, output_dir):
    out_path = os.path.join(output_dir, "final.mp4")

    # Build drawtext filters
    filters = []
    for seg in translation["segments"]:
        start, end = seg["start"], seg["end"]
        text = escape_for_drawtext(seg["text"])
        if not text:
            continue

        # Break long lines
        if len(text) > 50:
            words = text.split()
            mid = len(words) // 2
            text = "\\n".join([" ".join(words[:mid]), " ".join(words[mid:])])

        filter_str = (
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='{text}':fontcolor=white:fontsize=28:"
            f"borderw=2:bordercolor=black:"
            f"x=(w-text_w)/2:y=h*0.82:"
            f"enable='between(t\\,{start}\\,{end})'"
        )
        filters.append(filter_str)

    if not filters:
        # No valid subtitles, just merge video + voiceover
        cmd = [
            "ffmpeg", "-y", "-i", video_path, "-i", voiceover_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-shortest", out_path
        ]
    else:
        vf = ",".join(filters)
        cmd = [
            "ffmpeg", "-y", "-i", video_path, "-i", voiceover_path,
            "-vf", vf, "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-shortest", out_path
        ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"  ffmpeg drawtext failed, trying subtitle overlay fallback...")
        # Fallback: use SRT subtitle file instead of drawtext
        srt_path = generate_srt(translation, output_dir)
        cmd_fallback = [
            "ffmpeg", "-y", "-i", video_path, "-i", voiceover_path,
            "-vf", f"subtitles={srt_path}:force_style='FontName=DejaVu Sans,FontSize=28,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=0,Alignment=2,MarginV=50'",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-shortest", out_path
        ]
        subprocess.run(cmd_fallback, check=True, capture_output=True)
        os.remove(srt_path)

    return out_path
