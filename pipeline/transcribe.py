import whisper
import json
import os
import re

MODEL = "base"

# Common Whisper Russian transcription errors to fix
TRANSCRIPTION_FIXES = [
    (r'\bСус\b', 'Иисус'),           # Sus -> Jesus
    (r'\bСуса\b', 'Иисуса'),         # Susa -> Jesusa
    (r'\bСусский\b', 'Иисус'),       # Sussky -> Jesus
    (r'\bСус Христос\b', 'Иисус Христос'),  # Sus Christos -> Jesus Christ
    (r'\bРусалима\b', 'Иерусалима'), # Rusalima -> Jerusalem
    (r'\bИрусалим\b', 'Иерусалим'),  # Irusalim -> Jerusalem
    (r'\bармений\b', 'армян'),       # armeniy -> armyan
    (r'\bарминин\b', 'армянин'),     # arminin -> armyanin
    (r'\bарминь\b', 'Армения'),      # armin -> Armenia
    (r'\bарминьи\b', 'Армении'),     # armini -> Armenii
    (r'\bарминьей\b', 'Арменией'),   # arminyey -> Armeniey
    (r'\bарминьского\b', 'армянского'), # arminskogo -> armyanskogo
    (r'\bарминьскую\b', 'армянскую'), # arminskuyu -> armyanskuyu
    (r'\bарминьских\b', 'армянских'), # arminskikh -> armyanskikh
    (r'\bарминьской\b', 'армянской'), # arminskoy -> armyanskoy
    (r'\bарминьские\b', 'армянские'), # arminskie -> armyanskie
    (r'\bарминьский\b', 'армянский'), # arminskiy -> armyanskiy
    (r'\bарминьским\b', 'армянским'), # arminskim -> armyanskim
    (r'\bарминьскими\b', 'армянскими'), # arminskimi -> armyanskimi
    (r'\bарминьскому\b', 'армянскому'), # arminskomu -> armyanskomu
    (r'\bарминьскую\b', 'армянскую'), # arminskuyu -> armyanskuyu
    (r'\bарминьское\b', 'армянское'), # arminskoye -> armyanskoye
    (r'\bарминьской\b', 'армянской'), # arminskoy -> armyanskoy
    (r'\bарминьском\b', 'армянском'), # arminskom -> armyanskom
    (r'\bарминьсков\b', 'армянсков'), # arminskof -> armyanskov
    (r'\bарминьскою\b', 'армянскою'), # arminskoyu -> armyanskoyu
    (r'\bарминьск\b', 'армянск'),    # arminsk -> armyansk
]

def fix_transcription(text: str) -> str:
    """Apply known transcription fixes."""
    for pattern, replacement in TRANSCRIPTION_FIXES:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text

def transcribe(audio_path: str, output_dir: str) -> dict:
    model = whisper.load_model(MODEL)
    result = model.transcribe(audio_path, language="ru", word_timestamps=True)

    # Apply transcription fixes
    if "segments" in result:
        for seg in result["segments"]:
            if "text" in seg:
                original = seg["text"]
                fixed = fix_transcription(original)
                if fixed != original:
                    print(f"  [TRANSCRIBE FIX] '{original.strip()}' -> '{fixed.strip()}'")
                seg["text"] = fixed
        # Also fix full text
        if "text" in result:
            result["text"] = fix_transcription(result["text"])

    base = os.path.splitext(os.path.basename(audio_path))[0].replace("_audio", "")
    out = os.path.join(output_dir, f"{base}_transcript.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result
