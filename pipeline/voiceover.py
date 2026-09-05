import os
import subprocess
import tempfile

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
    """Generate per-speaker voiceovers and stitch with proper gaps."""
    path = os.path.join(output_dir, "voiceover.mp3")
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set.")

    segments = translation.get("segments", [])
    if not segments:
        raise RuntimeError("No segments to voice.")

    # Generate TTS for each segment
    segment_files = []
    for i, seg in enumerate(segments):
        speaker = seg.get("speaker", "Naran")
        text = seg["text"].strip()
        if not text:
            continue

        seg_path = os.path.join(output_dir, f"voice_seg_{i:03d}.mp3")
        generate_for_speaker(text, speaker, seg_path, api_key)
        duration = get_audio_duration(seg_path)
        segment_files.append({
            "path": seg_path,
            "duration": duration,
            "start": seg["start"],
            "end": seg["end"],
            "speaker": speaker
        })
        print(f"  [{speaker}] {text[:50]}... → {duration:.2f}s")

    # Build ffmpeg concat filter: each segment at its proper timestamp
    # Use adelay to position each clip, then amix
    if len(segment_files) == 1:
        # Just copy the single file
        import shutil
        shutil.copy(segment_files[0]["path"], path)
    else:
        # Build complex filter
        inputs = []
        delays = []
        for i, sf in enumerate(segment_files):
            inputs.extend(["-i", sf["path"]])
            delay_ms = int(sf["start"] * 1000)
            delays.append(f"[{i}]adelay={delay_ms}|{delay_ms}[a{i}]")

        mix_inputs = "".join(f"[a{i}]" for i in range(len(segment_files)))
        mix_filter = f"{mix_inputs}amix=inputs={len(segment_files)}:duration=longest[aout]"

        filter_complex = ";".join(delays + [mix_filter])

        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-c:a", "aac", "-b:a", "192k",
            path
        ]
        subprocess.run(cmd, check=True, capture_output=True)

    # Cleanup segment files
    for sf in segment_files:
        if os.path.exists(sf["path"]):
            os.remove(sf["path"])

    total_duration = get_audio_duration(path)
    print(f"  Voiceover stitched: {total_duration:.2f}s total")
    return path, total_duration
