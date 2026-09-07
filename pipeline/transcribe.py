import whisper
import json
import os
import re
import subprocess

MODEL = "base"

TRANSCRIPTION_FIXES = [
    (r'\bСус\b', 'Иисус'),
    (r'\bСуса\b', 'Иисуса'),
    (r'\bСусский\b', 'Иисус'),
    (r'\bСус Христос\b', 'Иисус Христос'),
    (r'\bРусалима\b', 'Иерусалима'),
    (r'\bИрусалим\b', 'Иерусалим'),
    (r'\bармений\b', 'армян'),
    (r'\bарминин\b', 'армянин'),
    (r'\bарминь\b', 'Армения'),
    (r'\bарминьи\b', 'Армении'),
    (r'\bарминьей\b', 'Арменией'),
    (r'\bарминьского\b', 'армянского'),
    (r'\bарминьскую\b', 'армянскую'),
    (r'\bарминьских\b', 'армянских'),
    (r'\bарминьской\b', 'армянской'),
    (r'\bарминьские\b', 'армянские'),
    (r'\bарминьский\b', 'армянский'),
    (r'\bарминьским\b', 'армянским'),
    (r'\bарминьскими\b', 'армянскими'),
    (r'\bарминьскому\b', 'армянскому'),
    (r'\bарминьское\b', 'армянское'),
    (r'\bарминьском\b', 'армянском'),
    (r'\bарминьсков\b', 'армянсков'),
    (r'\bарминьскою\b', 'армянскою'),
    (r'\bарминьск\b', 'армянск'),
]

def fix_transcription(text: str) -> str:
    for pattern, replacement in TRANSCRIPTION_FIXES:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

def detect_segment_language(text: str) -> str:
    words = text.split()
    if not words:
        return "ru"
    cyrillic_chars = sum(1 for c in text if '\u0400' <= c <= '\u04FF')
    latin_chars = sum(1 for c in text if c.isascii() and c.isalpha())
    if latin_chars > cyrillic_chars * 2:
        return "en"
    return "ru"

def get_audio_duration(audio_path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())

def extract_tail_audio(audio_path: str, start_time: float, output_path: str):
    """Extract tail portion of audio for separate transcription."""
    cmd = [
        "ffmpeg", "-y", "-i", audio_path,
        "-ss", str(start_time),
        "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)

def transcribe(audio_path: str, output_dir: str) -> dict:
    model = whisper.load_model(MODEL)

    # Pass 1: Auto language detection
    print("  [Pass 1] Auto language detection...")
    result_auto = model.transcribe(audio_path, word_timestamps=True)
    auto_lang = result_auto.get("language", "unknown")
    print(f"  Auto-detected language: {auto_lang}")

    all_segments = []
    for seg in result_auto.get("segments", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        lang = detect_segment_language(text)
        seg["detected_language"] = lang
        if lang == "ru":
            seg["text"] = fix_transcription(text)
        all_segments.append(seg)

    # Check if we missed tail audio
    audio_duration = get_audio_duration(audio_path)
    last_seg_end = max((s["end"] for s in all_segments), default=0)
    missing_tail = audio_duration - last_seg_end

    print(f"  Audio duration: {audio_duration:.1f}s, Last segment ends: {last_seg_end:.1f}s, Missing: {missing_tail:.1f}s")

    # Pass 2: If >5s missing at tail, extract and transcribe separately
    if missing_tail > 5:
        print(f"  [Pass 2] Transcribing missing tail ({missing_tail:.1f}s) with English...")
        tail_path = os.path.join(output_dir, "tail_audio.wav")
        extract_tail_audio(audio_path, last_seg_end - 2, tail_path)  # Start 2s before last segment for overlap

        result_tail = model.transcribe(tail_path, language="en", word_timestamps=True)

        tail_segments_added = 0
        for seg in result_tail.get("segments", []):
            text = seg.get("text", "").strip()
            if not text:
                continue
            # Adjust timestamps to absolute
            seg["start"] += last_seg_end - 2
            seg["end"] += last_seg_end - 2

            # Check if mostly English
            words = text.split()
            ascii_words = [w for w in words if w.isascii() and len(w) > 2]
            if len(ascii_words) > len(words) * 0.3:
                seg["detected_language"] = "en"
                all_segments.append(seg)
                tail_segments_added += 1
                print(f"    [ENGLISH TAIL] [{seg['start']:.1f}-{seg['end']:.1f}] {text[:60]}...")

        if os.path.exists(tail_path):
            os.remove(tail_path)

        print(f"  Added {tail_segments_added} segments from tail transcription")

    # Sort by timestamp
    all_segments.sort(key=lambda s: s["start"])

    # Build result
    result = {
        "text": " ".join(s["text"] for s in all_segments),
        "segments": all_segments,
        "language": "multilingual"
    }

    base = os.path.splitext(os.path.basename(audio_path))[0].replace("_audio", "")
    out = os.path.join(output_dir, f"{base}_transcript.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    ru_count = len([s for s in all_segments if s.get("detected_language") == "ru"])
    en_count = len([s for s in all_segments if s.get("detected_language") == "en"])
    print(f"  Transcription: {ru_count} Russian, {en_count} English segments")

    return result
