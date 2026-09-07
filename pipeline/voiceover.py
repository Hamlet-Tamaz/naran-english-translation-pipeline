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
# Minimum gap we ever allow when a stretched segment needs the room (ms)
MIN_GAP_MS = 50
# Maximum speed-up factor — beyond this we shrink the gap / allow slight
# overlap, but NEVER cut spoken audio. Every spoken portion must be complete.
MAX_SPEEDUP = 1.8

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

def build_atempo_chain(speed: float) -> str:
    """Build an ffmpeg atempo filter chain. Each atempo accepts 0.5-2.0,
    so chain multiple filters for larger factors."""
    filters = []
    s = speed
    while s > 2.0:
        filters.append("atempo=2.0")
        s /= 2.0
    filters.append(f"atempo={s:.4f}")
    return ",".join(filters)

def stretch_to_fit(raw_path: str, target_ms: int, output_path: str) -> int:
    """Time-stretch audio (pitch-preserving, ffmpeg atempo) so it fits
    within target_ms WITHOUT cutting anything. Returns new duration in ms."""
    audio = AudioSegment.from_mp3(raw_path)
    dur_ms = len(audio)
    if dur_ms <= target_ms or target_ms <= 0:
        if raw_path != output_path:
            audio.export(output_path, format="mp3", bitrate="192k")
        return dur_ms

    speed = dur_ms / target_ms
    if speed > MAX_SPEEDUP:
        speed = MAX_SPEEDUP

    chain = build_atempo_chain(speed)
    cmd = [
        "ffmpeg", "-y", "-i", raw_path,
        "-filter:a", chain,
        "-b:a", "192k",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    new_dur_ms = len(AudioSegment.from_mp3(output_path))
    return new_dur_ms

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

        raw_path = os.path.join(output_dir, f"voice_raw_{i:03d}.mp3")
        seg_path = os.path.join(output_dir, f"voice_seg_{i:03d}.mp3")
        generate_for_speaker(text, speaker, raw_path, api_key)

        raw_audio = AudioSegment.from_mp3(raw_path)
        raw_ms = len(raw_audio)
        position_ms = int(seg["start"] * 1000)

        # Calculate allocated window (with gap before next segment)
        if i < len(segments) - 1:
            next_start_ms = int(segments[i + 1]["start"] * 1000)
            allocated_end_ms = next_start_ms - GAP_MS
            hard_end_ms = next_start_ms  # absolute boundary (0 gap)
        else:
            allocated_end_ms = total_duration_ms
            hard_end_ms = total_duration_ms

        allocated_ms = allocated_end_ms - position_ms

        if raw_ms <= allocated_ms:
            # Fits naturally — use as-is
            final_audio = raw_audio
            final_ms = raw_ms
        else:
            # Too long — quicken the speech to fit. NEVER cut.
            needed_speed = raw_ms / allocated_ms if allocated_ms > 0 else MAX_SPEEDUP + 1
            if needed_speed <= MAX_SPEEDUP:
                final_ms = stretch_to_fit(raw_path, allocated_ms, seg_path)
                print(f"  [{speaker}] quickened {needed_speed:.2f}x ({raw_ms/1000:.2f}s -> {final_ms/1000:.2f}s)")
            else:
                # Even max speedup won't fit in the window with a full gap.
                # Priority: complete speech > gap. Shrink gap, then allow
                # slight overlap as a last resort — but never cut audio.
                min_gap_end_ms = hard_end_ms - MIN_GAP_MS
                target_ms = max(min_gap_end_ms - position_ms, 500)
                final_ms = stretch_to_fit(raw_path, target_ms, seg_path)
                if position_ms + final_ms > hard_end_ms:
                    print(f"  [{speaker}] WARN: speech complete but overlaps next segment by {(position_ms + final_ms - hard_end_ms)/1000:.2f}s")
                else:
                    print(f"  [{speaker}] quickened {MAX_SPEEDUP:.2f}x + gap shrunk ({raw_ms/1000:.2f}s -> {final_ms/1000:.2f}s)")
            final_audio = AudioSegment.from_mp3(seg_path)

        base_audio = base_audio.overlay(final_audio, position=position_ms)
        if os.path.exists(raw_path):
            os.remove(raw_path)
        if os.path.exists(seg_path):
            os.remove(seg_path)
        print(f"  [{speaker}] {text[:45]}... @ {seg['start']:.1f}s ({final_ms/1000:.2f}s)")

    base_audio.export(path, format="mp3", bitrate="192k")
    total_duration = get_audio_duration(path)
    print(f"  Voiceover: {total_duration:.2f}s, {GAP_MS}ms gaps (speech time-stretched, never cut)")
    return path, total_duration
