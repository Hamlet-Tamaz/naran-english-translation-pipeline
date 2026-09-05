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

def burn(video_path, translation, voiceover_path, output_dir):
    out_path = os.path.join(output_dir, "final.mp4")
    filters = []
    for seg in translation["segments"]:
        start, end = seg["start"], seg["end"]
        text = seg["text"].strip().replace("'", "\\'")
        text = text.replace(":", "\\:").replace("=", "\\=")
        if len(text) > 50:
            words = text.split()
            mid = len(words) // 2
            text = "\\n".join([" ".join(words[:mid]), " ".join(words[mid:])])
        filters.append(
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='{text}':fontcolor=white:fontsize=28:borderw=2:bordercolor=black:"
            f"x=(w-text_w)/2:y=h*0.82:enable='between(t\\,{start}\\,{end})'"
        )
    vf = ",".join(filters)
    cmd = [
        "ffmpeg", "-y", "-i", video_path, "-i", voiceover_path,
        "-vf", vf, "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k", "-shortest", out_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
