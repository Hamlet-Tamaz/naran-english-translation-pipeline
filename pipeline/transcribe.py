import whisper
import json
import os
import re

MODEL = "base"

# Common Whisper Russian transcription errors to fix
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

def transcribe(audio_path: str, output_dir: str) -> dict:
    model = whisper.load_model(MODEL)
    result = model.transcribe(audio_path, word_timestamps=True)

    if "segments" in result:
        for seg in result["segments"]:
            text = seg.get("text", "").strip()
            lang = detect_segment_language(text)
            seg["detected_language"] = lang

            if lang == "ru":
                original = text
                fixed = fix_transcription(original)
                if fixed != original:
                    print(f"  [TRANSCRIBE FIX] '{original.strip()}' -> '{fixed.strip()}'")
                seg["text"] = fixed
            else:
                seg["text"] = text
                print(f"  [ENGLISH SEGMENT] {seg['start']:.1f}s-{seg['end']:.1f}s: {text[:60]}...")

        if "text" in result:
            result["text"] = fix_transcription(result["text"])

    base = os.path.splitext(os.path.basename(audio_path))[0].replace("_audio", "")
    out = os.path.join(output_dir, f"{base}_transcript.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    ru_segments = [s for s in result.get("segments", []) if s.get("detected_language") == "ru"]
    en_segments = [s for s in result.get("segments", []) if s.get("detected_language") == "en"]
    print(f"  Transcription: {len(ru_segments)} Russian, {len(en_segments)} English segments")

    return result
