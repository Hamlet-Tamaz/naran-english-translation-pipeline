import os
import subprocess

def generate(text: str, output_dir: str) -> tuple:
    """Generate English voiceover with OpenAI TTS (male voice: onyx).
    Returns (path, duration_seconds)."""
    path = os.path.join(output_dir, "voiceover.mp3")
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set. Cannot generate voiceover.")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.audio.speech.create(
            model="tts-1",
            voice="onyx",
            input=text,
            response_format="mp3"
        )
        response.stream_to_file(path)
        print("  Voiceover: OpenAI TTS (onyx — male)")
    except Exception as e:
        print(f"  OpenAI TTS failed ({e})")
        raise

    # Measure duration
    duration = get_audio_duration(path)
    print(f"  Voiceover duration: {duration:.2f}s")
    return path, duration

def get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())

def pad_to_duration(audio_path: str, target_duration: float, output_path: str):
    """Pad audio with silence to match target_duration."""
    current = get_audio_duration(audio_path)
    if current >= target_duration:
        # Just copy
        import shutil
        shutil.copy(audio_path, output_path)
        return

    pad_sec = target_duration - current
    cmd = [
        "ffmpeg", "-y",
        "-i", audio_path,
        "-af", f"apad=pad_dur={pad_sec}",
        "-c:a", "aac", "-b:a", "192k",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
