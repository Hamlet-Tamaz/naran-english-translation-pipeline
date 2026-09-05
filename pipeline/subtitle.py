import subprocess
import os
import srt
from datetime import timedelta

def generate_srt(translation: dict, output_dir: str) -> str:
    """Generate SRT file from translation segments."""
    subs = []
    for i, seg in enumerate(translation["segments"], 1):
        start = timedelta(seconds=seg["start"])
        end = timedelta(seconds=seg["end"])
        subs.append(srt.Subtitle(
            index=i,
            start=start,
            end=end,
            content=seg["text"].strip()
        ))
    srt_content = srt.compose(subs)
    srt_path = os.path.join(output_dir, "subtitles.srt")
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    return srt_path

def burn(video_path: str, translation: dict, voiceover_path: str, output_dir: str) -> str:
    """Burn subtitles and mix audio using ffmpeg only."""
    out_path = os.path.join(output_dir, "final.mp4")
    srt_path = generate_srt(translation, output_dir)

    # Step 1: Mix audio (original at 15% + voiceover at 100%)
    mixed_audio = os.path.join(output_dir, "mixed_audio.aac")
    cmd_mix = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", voiceover_path,
        "-filter_complex",
        "[0:a]volume=0.15[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]",
        "-map", "[aout]",
        "-c:a", "aac", "-b:a", "192k",
        mixed_audio
    ]
    subprocess.run(cmd_mix, check=True, capture_output=True)

    # Step 2: Burn subtitles into video with mixed audio
    # Use drawtext for better control over subtitle styling
    # Build drawtext filter expressions for each segment
    filters = []
    for seg in translation["segments"]:
        start = seg["start"]
        end = seg["end"]
        text = seg["text"].strip().replace("'", "\'")
        # Escape special chars for ffmpeg drawtext
        text = text.replace(":", "\:").replace("=", "\=")
        if len(text) > 50:
            words = text.split()
            mid = len(words) // 2
            text = "\\n".join([" ".join(words[:mid]), " ".join(words[mid:])])

        filter_str = (
            f"drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
            f"text='{text}':"
            f"fontcolor=white:fontsize=28:"
            f"borderw=2:bordercolor=black:"
            f"x=(w-text_w)/2:y=h*0.82:"
            f"enable='between(t\,{start}\,{end})'"
        )
        filters.append(filter_str)

    vf = ",".join(filters)

    cmd_burn = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", mixed_audio,
        "-vf", vf,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path
    ]
    subprocess.run(cmd_burn, check=True, capture_output=True)

    # Cleanup temp files
    for f in [mixed_audio, srt_path]:
        if os.path.exists(f):
            os.remove(f)

    return out_path
