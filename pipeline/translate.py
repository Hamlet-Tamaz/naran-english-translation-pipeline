from deep_translator import GoogleTranslator
import json
import os

def translate(transcript: dict, output_dir: str) -> dict:
    translator = GoogleTranslator(source="ru", target="en")
    segments_en = []
    for seg in transcript.get("segments", []):
        txt = seg["text"].strip()
        if txt:
            translated = translator.translate(txt)
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
