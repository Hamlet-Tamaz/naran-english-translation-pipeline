import subprocess
import os

def get_video_dimensions(video_path: str) -> tuple:
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
        return 1080, 1920

def get_video_duration(video_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except Exception:
        return 60.0

def format_ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

def scale_timestamps(segments: list, voiceover_duration: float) -> list:
    """Scale all segment timings proportionally to fit within voiceover duration."""
    if not segments:
        return segments

    original_end = max(seg["end"] for seg in segments)
    if original_end <= 0 or voiceover_duration <= 0:
        return segments

    # If voiceover is longer than original, no scaling needed (just clamp)
    # If voiceover is shorter, scale down proportionally
    scale = min(1.0, voiceover_duration / original_end)

    scaled = []
    for seg in segments:
        new_start = seg["start"] * scale
        new_end = min(seg["end"] * scale, voiceover_duration)
        # Ensure end > start
        if new_end <= new_start:
            new_end = new_start + 0.5
        s = dict(seg)
        s["start"] = new_start
        s["end"] = new_end
        scaled.append(s)

    return scaled

def build_ass(translation, output_dir, video_width, video_height, voiceover_duration):
    font_size = max(22, min(36, int(video_height * 0.022)))
    label_size = max(16, int(font_size * 0.65))
    margin_v = max(80, int(video_height * 0.08))
    margin_lr = max(30, int(video_width * 0.04))

    header = f"""[Script Info]
Title: Naran Pipeline Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Naran,DejaVu Sans,{font_size},&H00FFFFFF,&H00808080,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,2,{margin_lr},{margin_lr},{margin_v},1
Style: Other,DejaVu Sans,{font_size},&H0000FFFF,&H00808080,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,2,{margin_lr},{margin_lr},{margin_v},1
Style: Label,DejaVu Sans,{label_size},&H00FFFFFF,&H00808080,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,1,0,2,{margin_lr},{margin_lr},{margin_v + font_size + 8},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogues = []
    segments = translation.get("segments", [])

    # Scale timestamps to fit voiceover
    segments = scale_timestamps(segments, voiceover_duration)

    for seg in segments:
        start = seg["start"]
        end = seg["end"]
        text = seg.get("text", "").strip()
        speaker = seg.get("speaker", "Naran")

        if not text:
            continue

        style = "Naran" if speaker == "Naran" else "Other"

        # Speaker label
        label = speaker if speaker == "Naran" else "Commenter"
        label_text = f"({label})"

        # Karaoke the main text
        words = text.split()
        if len(words) > 1:
            duration = end - start
            word_duration = duration / len(words)
            karaoke_parts = []
            for word in words:
                cs = max(1, int(word_duration * 100))
                safe_word = word.replace("{", "\\{").replace("}", "\\}")
                karaoke_parts.append(f"{{\\k{cs}}}{safe_word}")
            karaoke_text = " ".join(karaoke_parts)
        else:
            karaoke_text = text.replace("{", "\\{").replace("}", "\\}")

        start_ass = format_ass_time(start)
        end_ass = format_ass_time(end)

        # Label dialogue (appears above, no karaoke)
        safe_label = label_text.replace("{", "\\{").replace("}", "\\}")
        dialogues.append(f"Dialogue: 0,{start_ass},{end_ass},Label,,0,0,0,,{safe_label}")

        # Main text dialogue
        dialogues.append(f"Dialogue: 0,{start_ass},{end_ass},{style},,0,0,0,,{karaoke_text}")

    ass_content = header + "\n".join(dialogues)
    ass_path = os.path.join(output_dir, "subtitles.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    return ass_path

def burn(video_path, translation, voiceover_path, voiceover_duration, output_dir):
    out_path = os.path.join(output_dir, "final.mp4")
    width, height = get_video_dimensions(video_path)
    video_duration = get_video_duration(video_path)

    # Build ASS with scaled timestamps
    ass_path = build_ass(translation, output_dir, width, height, voiceover_duration)

    # Pad voiceover to match video duration so full video plays
    padded_vo = os.path.join(output_dir, "voiceover_padded.m4a")
    if voiceover_duration < video_duration:
        pad_sec = video_duration - voiceover_duration
        cmd_pad = [
            "ffmpeg", "-y",
            "-i", voiceover_path,
            "-af", f"apad=pad_dur={pad_sec}",
            "-c:a", "aac", "-b:a", "192k",
            padded_vo
        ]
        subprocess.run(cmd_pad, check=True, capture_output=True)
        audio_input = padded_vo
    else:
        audio_input = voiceover_path

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", audio_input,
        "-vf", f"ass={ass_path}",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(video_duration),
        out_path
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"  Subtitles burned successfully: {out_path}")
    except subprocess.CalledProcessError as e:
        print(f"  ffmpeg subtitle burn failed: {e}")
        print(f"  stderr: {e.stderr.decode() if e.stderr else 'N/A'}")
        # Fallback
        cmd_fallback = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_input,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(video_duration),
            out_path
        ]
        subprocess.run(cmd_fallback, check=True, capture_output=True)
        print(f"  Fallback: video + voiceover only")
    finally:
        if os.path.exists(ass_path):
            os.remove(ass_path)
        if os.path.exists(padded_vo) and padded_vo != voiceover_path:
            os.remove(padded_vo)

    return out_path
