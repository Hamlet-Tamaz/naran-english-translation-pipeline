import os
import subprocess

def generate_srt(segments, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            start = seg["start"]
            end = seg["end"]
            text = seg.get("text", "").strip()
            speaker = seg.get("speaker", "Naran")
            if not text:
                continue
            f.write(f"{i}\n")
            f.write(f"{format_time(start)} --> {format_time(end)}\n")
            f.write(f"({speaker}) {text}\n\n")

def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def wrap_text(text, max_chars=40):
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line) + len(word) + 1 <= max_chars:
            current_line += (" " + word if current_line else word)
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines[:2]

def generate_ass(segments, output_path, video_path):
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0",
        video_path
    ]
    result = subprocess.run(probe_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        parts = result.stdout.strip().split(",")
        video_width = int(parts[0])
        video_height = int(parts[1])
    else:
        video_width = 1080
        video_height = 1920

    font_size = max(18, int(video_height * 0.028))
    margin_lr = int(video_width * 0.06)
    margin_v = int(video_height * 0.08)

    header = f"""[Script Info]
Title: Naran English Subtitles
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{font_size},&H00FFFFFF,&H00808080,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,2,{margin_lr},{margin_lr},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    for seg in segments:
        text = seg.get("text", "").strip()
        speaker = seg.get("speaker", "Naran")
        if not text:
            continue
        lines = wrap_text(text)
        ass_text = "\\N".join(lines)
        start = format_ass_time(seg["start"])
        end = format_ass_time(seg["end"])
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,({speaker})\\N{ass_text}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        for event in events:
            f.write(event + "\n")

def format_ass_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

def burn(video_path, translation, voiceover_path, voiceover_duration, output_dir):
    segments = translation.get("segments", [])
    srt_path = os.path.join(output_dir, "subtitles.srt")
    ass_path = os.path.join(output_dir, "subtitles.ass")
    generate_srt(segments, srt_path)
    generate_ass(segments, ass_path, video_path)

    final_path = os.path.join(output_dir, "final.mp4")
    temp_video = os.path.join(output_dir, "temp_subbed.mp4")

    # Step 1: Burn subtitles — try ass filter first, fallback to SRT
    cmd1 = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"ass={ass_path}",
        "-an",
        temp_video
    ]
    result1 = subprocess.run(cmd1, capture_output=True, text=True)
    if result1.returncode != 0:
        print(f"  [WARN] ASS filter failed, using SRT fallback...")
        print(f"  Error: {result1.stderr[:300]}")
        cmd1_fb = [
            "ffmpeg", "-y", "-i", video_path,
            "-vf", f"subtitles={srt_path}:force_style='FontName=DejaVu Sans,FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H80000000,Outline=2,Shadow=0,Alignment=2,MarginV=80'",
            "-an",
            temp_video
        ]
        subprocess.run(cmd1_fb, check=True, capture_output=True)

    # Step 2: Mix voiceover audio
    cmd2 = [
        "ffmpeg", "-y",
        "-i", temp_video,
        "-i", voiceover_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        final_path
    ]
    subprocess.run(cmd2, check=True, capture_output=True)

    if os.path.exists(temp_video):
        os.remove(temp_video)

    print(f"  Final video: {final_path}")
    return final_path
