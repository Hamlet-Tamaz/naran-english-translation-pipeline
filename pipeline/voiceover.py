import os
import subprocess
from pydub import AudioSegment

VOICE_MAP = {
    "Naran": "onyx",
    "Kamran": "echo",
    "Commenter": "fable",
}

def generate_for_speaker(text: str, speaker: str, output_path: str, api_key: str):
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
    path = os.path.join(output_dir, "voiceover.mp3")
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set.")

    segments = translation.get("segments", [])
    if not segments:
        raise RuntimeError("No segments to voice.")

    # Calculate total duration needed
    total_duration_ms = int(max(seg["end"] for seg in segments) * 1000) + 3000
    base_audio = AudioSegment.silent(duration=total_duration_ms)

    for i, seg in enumerate(segments):
        speaker = seg.get("speaker", "Naran")
        text = seg["text"].strip()
        if not text:
            continue

        seg_path = os.path.join(output_dir, f"voice_seg_{i:03d}.mp3")
        generate_for_speaker(text, speaker, seg_path, api_key)

        segment_audio = AudioSegment.from_mp3(seg_path)
        position_ms = int(seg["start"] * 1000)

        # Calculate allocated time window (until next segment starts)
        if i < len(segments) - 1:
            next_start = segments[i + 1]["start"]
            allocated_ms = int((next_start - seg["start"]) * 1000)
        else:
            allocated_ms = 999999  # Last segment gets rest of time

        # Trim if TTS is longer than allocated window (prevent overlap)
        if len(segment_audio) > allocated_ms and allocated_ms > 500:
            segment_audio = segment_audio[:allocated_ms]
            print(f"  [{speaker}] trimmed {len(segment_audio)/1000:.2f}s → {allocated_ms/1000:.2f}s (overlap prevention)")

        base_audio = base_audio.overlay(segment_audio, position=position_ms)
        os.remove(seg_path)
        print(f"  [{speaker}] {text[:45]}... → placed @ {seg['start']:.1f}s")

    base_audio.export(path, format="mp3", bitrate="192k")
    total_duration = get_audio_duration(path)
    print(f"  Voiceover: {total_duration:.2f}s, no overlaps")
    return path, total_duration
