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

def format_ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds - int(seconds)) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

def build_ass(translation, output_dir, video_width, video_height):
    font_size = max(26, min(40, int(video_height * 0.02)))
    margin_v = max(100, int(video_height * 0.10))
    margin_lr = max(40, int(video_width * 0.05))

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

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    dialogues = []
    for seg in translation.get("segments", []):
        start = seg["start"]
        end = seg["end"]
        text = seg.get("text", "").strip()
        speaker = seg.get("speaker", "Naran")

        if not text:
            continue

        style = "Naran" if speaker == "Naran" else "Other"

        words = text.split()
        if len(words) > 1:
            duration = end - start
            word_duration = duration / len(words)
            karaoke_parts = []
            for word in words:
                cs = max(1, int(word_duration * 100))
                safe_word = word.replace("{", "\{").replace("}", "\}")
                karaoke_parts.append(f"{{\k{cs}}}{safe_word}")
            karaoke_text = " ".join(karaoke_parts)
        else:
            karaoke_text = text.replace("{", "\{").replace("}", "\}")

        start_ass = format_ass_time(start)
        end_ass = format_ass_time(end)
        dialogue = f"Dialogue: 0,{start_ass},{end_ass},{style},,0,0,0,,{karaoke_text}"
        dialogues.append(dialogue)

    ass_content = header + "\n".join(dialogues)
    ass_path = os.path.join(output_dir, "subtitles.ass")
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    return ass_path

def burn(video_path, translation, voiceover_path, output_dir):
    out_path = os.path.join(output_dir, "final.mp4")
    width, height = get_video_dimensions(video_path)
    ass_path = build_ass(translation, output_dir, width, height)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", voiceover_path,
        "-vf", f"ass={ass_path}",
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
        print(f"  Fallback: video + voiceover only")
    finally:
        if os.path.exists(ass_path):
            os.remove(ass_path)

    return out_path
