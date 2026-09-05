import subprocess
import os
import srt
from datetime import timedelta

def wrap_text(text: str, max_line_len: int = 32, max_lines: int = 2) -> str:
    """Wrap text into lines of max_line_len chars, max max_lines lines."""
    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        if len(current_line) + len(word) + 1 <= max_line_len:
            current_line = (current_line + " " + word).strip()
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
            if len(lines) >= max_lines - 1:
                # Only allow one more line, then truncate with ellipsis
                break

    if current_line and len(lines) < max_lines:
        lines.append(current_line)

    # If we broke early due to length, append ellipsis to last line
    if len(lines) >= max_lines and current_line and current_line not in lines:
        lines[-1] = lines[-1].rstrip(".") + "..."

    return "\n".join(lines)

def generate_srt(translation, output_dir):
    """Generate a properly wrapped SRT file."""
    subs = []
    for i, seg in enumerate(translation["segments"], 1):
        start = timedelta(seconds=seg["start"])
        end = timedelta(seconds=seg["end"])
        wrapped = wrap_text(seg["text"].strip())
        if wrapped:
            subs.append(srt.Subtitle(index=i, start=start, end=end, content=wrapped))

    srt_path = os.path.join(output_dir, "subtitles.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt.compose(subs))
    return srt_path

def get_video_dimensions(video_path: str) -> tuple:
    """Get video width and height using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=s=x:p=0",
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        w, h = result.stdout.strip().split("x")
        return int(w), int(h)
    except Exception:
        return 1080, 1920  # Default to typical vertical video

def burn(video_path, translation, voiceover_path, output_dir):
    out_path = os.path.join(output_dir, "final.mp4")

    # Generate clean SRT with wrapped text
    srt_path = generate_srt(translation, output_dir)

    # Get video dimensions to calculate relative font size
    width, height = get_video_dimensions(video_path)

    # Calculate font size: ~5% of video height, min 20, max 36
    font_size = max(20, min(36, int(height * 0.048)))

    # Margin from bottom: ~8% of height
    margin_v = max(30, int(height * 0.08))

    # Build subtitle style string for ffmpeg force_style
    # Alignment: 2 = bottom center
    # MarginV: vertical margin from bottom edge
    # Outline + Shadow for readability
    style = (
        f"FontName=DejaVu Sans,"
        f"FontSize={font_size},"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"Outline=2,"
        f"Shadow=0,"
        f"Alignment=2,"
        f"MarginV={margin_v},"
        f"MarginL=40,"
        f"MarginR=40,"
        f"WrapStyle=0,"
        f"BorderStyle=1"
    )

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", voiceover_path,
        "-vf", f"subtitles={srt_path}:force_style='{style}'",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  Subtitles burned successfully: {out_path}")
    except subprocess.CalledProcessError as e:
        print(f"  ffmpeg subtitle burn failed: {e}")
        print(f"  stderr: {e.stderr.decode() if e.stderr else 'N/A'}")
        # Fallback: just merge video + voiceover without subtitles
        cmd_fallback = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", voiceover_path,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            out_path
        ]
        subprocess.run(cmd_fallback, check=True, capture_output=True)
        print(f"  Fallback: video + voiceover only (no subtitles)")
    finally:
        # Clean up SRT file
        if os.path.exists(srt_path):
            os.remove(srt_path)

    return out_path
