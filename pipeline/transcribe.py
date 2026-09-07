import whisper
import json
import os
import re

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

def segments_overlap(seg1, seg2, threshold=0.5):
    """Check if two segments overlap by more than threshold ratio."""
    start = max(seg1["start"], seg2["start"])
    end = min(seg1["end"], seg2["end"])
    if start >= end:
        return False
    overlap = end - start
    seg1_duration = seg1["end"] - seg1["start"]
    seg2_duration = seg2["end"] - seg2["start"]
    return overlap > seg1_duration * threshold or overlap > seg2_duration * threshold

def transcribe(audio_path: str, output_dir: str) -> dict:
    model = whisper.load_model(MODEL)

    # Pass 1: Transcribe with auto language detection (no language lock)
    print("  [Pass 1] Auto language detection...")
    result_auto = model.transcribe(audio_path, word_timestamps=True)
    auto_lang = result_auto.get("language", "unknown")
    print(f"  Auto-detected language: {auto_lang}")

    # Pass 2: Always run English transcription to catch embedded English segments
    print("  [Pass 2] English transcription...")
    result_en = model.transcribe(audio_path, language="en", word_timestamps=True)

    # Pass 3: Always run Russian transcription for completeness
    print("  [Pass 3] Russian transcription...")
    result_ru = model.transcribe(audio_path, language="ru", word_timestamps=True)

    # Start with auto-detected segments as base
    all_segments = []

    # Add auto-detected segments with language detection
    for seg in result_auto.get("segments", []):
        text = seg.get("text", "").strip()
        if not text:
            continue
        lang = detect_segment_language(text)
        seg["detected_language"] = lang
        if lang == "ru":
            seg["text"] = fix_transcription(text)
        all_segments.append(seg)

    # Add English segments from Pass 2 that don't overlap with existing segments
    auto_texts = set(s["text"].strip().lower() for s in all_segments)
    en_added = 0
    for en_seg in result_en.get("segments", []):
        en_text = en_seg["text"].strip()
        if not en_text:
            continue
        # Check if this segment is mostly English
        words = en_text.split()
        ascii_words = [w for w in words if w.isascii() and len(w) > 2]
        if len(ascii_words) <= len(words) * 0.4:
            continue  # Skip if not mostly English

        # Check if this exact text already exists
        if en_text.lower() in auto_texts:
            continue

        # Check overlap with existing segments
        overlaps = False
        for existing in all_segments:
            if segments_overlap(en_seg, existing):
                overlaps = True
                break

        if not overlaps:
            en_seg["detected_language"] = "en"
            all_segments.append(en_seg)
            en_added += 1

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
    print(f"  Transcription: {ru_count} Russian, {en_count} English segments (added {en_added} from English pass)")

    return result
