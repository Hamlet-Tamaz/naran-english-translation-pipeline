import os
import subprocess
from pydub import AudioSegment

# Voice mapping: each speaker gets a distinct OpenAI voice
VOICE_MAP = {
    "Naran": "onyx",      # Deep, authoritative male
    "Kamran": "echo",     # Slightly different male voice
    "Commenter": "fable",  # British male — distinct from both
}

def generate_for_speaker(text: str, speaker: str, output_path: str, api_key: str):
    """Generate TTS for a specific speaker using their assigned voice."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    voice = VOICE_MAP.get(speaker, "onyx")
    response = client.audio.speech.create(
        model="tts-1",
        voice=voice,
        input=text,
        response_format="mp3"
    )
    response.stream_to_file(output_path)
    return output_path

def get_audio_duration(audio_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())

def generate(translation: dict, output_dir: str) -> tuple:
    """Generate per-speaker voiceovers and stitch with proper gaps using pydub."""
    path = os.path.join(output_dir, "voiceover.mp3")
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set.")

    segments = translation.get("segments", [])
    if not segments:
        raise RuntimeError("No segments to voice.")

    # Calculate total duration needed (based on last segment end)
    total_duration_ms = int(max(seg["end"] for seg in segments) * 1000) + 5000  # +5s buffer

    # Start with silence
    base_audio = AudioSegment.silent(duration=total_duration_ms)

    for i, seg in enumerate(segments):
        speaker = seg.get("speaker", "Naran")
        text = seg["text"].strip()
        if not text:
            continue

        seg_path = os.path.join(output_dir, f"voice_seg_{i:03d}.mp3")
        generate_for_speaker(text, speaker, seg_path, api_key)

        # Load segment and position it
        segment_audio = AudioSegment.from_mp3(seg_path)
        position_ms = int(seg["start"] * 1000)

        # Overlay at correct position
        base_audio = base_audio.overlay(segment_audio, position=position_ms)

        # Cleanup
        os.remove(seg_path)
        print(f"  [{speaker}] {text[:50]}... → {len(segment_audio)/1000:.2f}s @ {seg['start']:.1f}s")

    # Export
    base_audio.export(path, format="mp3", bitrate="192k")
    total_duration = get_audio_duration(path)
    print(f"  Voiceover stitched: {total_duration:.2f}s total")
    return path, total_duration
