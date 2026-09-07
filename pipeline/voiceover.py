import os
import subprocess
from pydub import AudioSegment

# Canonical voice map — each speaker gets ONE permanent voice
VOICE_MAP = {
    "Naran": "onyx",           # Deep male — host
    "Kamran": "echo",          # Different male — commenter being debunked
    "Other Speaker": "fable",  # Distinct voice for quoted sources
    "Commenter": "nova",       # Fallback for generic commenters
    "Commenter1": "nova",
    "Commenter2": "shimmer",
}

# Gap between speaker transitions (ms)
GAP_MS = 200

def get_voice_for_speaker(speaker: str) -> str:
    """Return the canonical voice for a speaker. Never changes."""
    canonical = speaker.strip()
    if canonical in VOICE_MAP:
        return VOICE_MAP[canonical]
    # Handle numbered commenters
    if canonical.startswith("Commenter"):
        num = canonical.replace("Commenter", "")
        voices = ["nova", "shimmer", "fable"]
        return voices[int(num) % len(voices)] if num.isdigit() else "nova"
    # Handle numbered speakers
    if canonical.startswith("Speaker") and canonical[7:].isdigit():
        num = int(canonical[7:])
        voices = ["onyx", "echo", "fable", "nova", "shimmer"]
        return voices[num % len(voices)]
    # Default fallback
    return VOICE_MAP.get("Other Speaker", "fable")

def generate_for_speaker(text: str, speaker: str, output_path: str, api_key: str):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    voice = get_voice_for_speaker(speaker)
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

    # Log voice assignments for audit
    voice_assignments = {}
    for seg in segments:
        sp = seg.get("speaker", "Naran")
        voice = get_voice_for_speaker(sp)
        voice_assignments[sp] = voice
    print(f"  Voice assignments: {voice_assignments}")

    last_end = max(seg["end"] for seg in segments)
    total_duration_ms = int(last_end * 1000) + 5000
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

        # Calculate allocated window (with gap before next segment)
        if i < len(segments) - 1:
            next_start_ms = int(segments[i + 1]["start"] * 1000)
            allocated_end_ms = next_start_ms - GAP_MS
        else:
            allocated_end_ms = total_duration_ms

        allocated_ms = allocated_end_ms - position_ms

        # Trim or fade if segment is too long
        if len(segment_audio) > allocated_ms + 2000 and allocated_ms > 1000:
            segment_audio = segment_audio[:int(allocated_ms)]
            print(f"  [{speaker}] trimmed {len(segment_audio)/1000:.2f}s -> {allocated_ms/1000:.2f}s")
        elif len(segment_audio) > allocated_ms:
            fade_ms = min(300, len(segment_audio) - allocated_ms)
            if fade_ms > 50:
                segment_audio = segment_audio[:allocated_ms + fade_ms].fade_out(fade_ms)
                print(f"  [{speaker}] faded out last {fade_ms}ms")

        base_audio = base_audio.overlay(segment_audio, position=position_ms)
        os.remove(seg_path)
        print(f"  [{speaker}] {text[:45]}... @ {seg['start']:.1f}s ({len(segment_audio)/1000:.2f}s)")

    base_audio.export(path, format="mp3", bitrate="192k")
    total_duration = get_audio_duration(path)
    print(f"  Voiceover: {total_duration:.2f}s, {GAP_MS}ms gaps")
    return path, total_duration
