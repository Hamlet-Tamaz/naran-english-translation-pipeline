from deep_translator import GoogleTranslator
from deep_translator.exceptions import TranslationNotFound
import json
import os
import time

def translate(transcript: dict, output_dir: str) -> dict:
    translator = GoogleTranslator(source="ru", target="en")

    segments_en = []
    for seg in transcript.get("segments", []):
        txt = seg["text"].strip()
        if not txt:
            continue

        # Try translating, with retry on failure
        translated = translate_with_retry(translator, txt)

        segments_en.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": translated
        })

    full_text = " ".join(s["text"] for s in segments_en)
    result = {"full_text": full_text, "segments": segments_en}

    out = os.path.join(output_dir, "translation.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result

def translate_with_retry(translator, text: str, max_retries: int = 3) -> str:
    """Translate text with retry logic and chunking for long texts."""
    for attempt in range(max_retries):
        try:
            return translator.translate(text)
        except TranslationNotFound:
            if attempt < max_retries - 1:
                time.sleep(1)  # Wait before retry
                continue
            # If all retries failed, try splitting into smaller chunks
            if len(text) > 100:
                words = text.split()
                mid = len(words) // 2
                part1 = " ".join(words[:mid])
                part2 = " ".join(words[mid:])
                try:
                    return translator.translate(part1) + " " + translator.translate(part2)
                except:
                    pass
            # Final fallback: return original text with marker
            return f"[TRANSLATION FAILED: {text[:50]}...]"
    return f"[TRANSLATION FAILED: {text[:50]}...]"
