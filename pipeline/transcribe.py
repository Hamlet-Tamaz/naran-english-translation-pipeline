import whisper
import json
import os

MODEL = "base"

def transcribe(audio_path: str, output_dir: str) -> dict:
    model = whisper.load_model(MODEL)
    result = model.transcribe(audio_path, language="ru", word_timestamps=True)

    base = os.path.splitext(os.path.basename(audio_path))[0].replace("_audio", "")
    out = os.path.join(output_dir, f"{base}_transcript.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result
