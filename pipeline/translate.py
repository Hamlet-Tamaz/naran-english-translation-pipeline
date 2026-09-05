import os
import json
import time

def translate(transcript: dict, output_dir: str) -> dict:
    """Translate Russian transcript to English using OpenAI GPT-4."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        # Build the full Russian text
        full_ru = " ".join(seg["text"].strip() for seg in transcript.get("segments", []) if seg["text"].strip())

        # Translate in one call for consistency
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise translator. Translate the following Russian text to natural, conversational English. Preserve the tone and meaning exactly. Do not add explanations or notes."
                },
                {
                    "role": "user",
                    "content": full_ru
                }
            ],
            temperature=0.3,
            max_tokens=2000
        )

        translated_full = response.choices[0].message.content.strip()

        # Now split the translated text back into segments matching original timing
        # Use proportional word count per segment
        ru_segments = [seg for seg in transcript.get("segments", []) if seg["text"].strip()]
        total_ru_words = sum(len(seg["text"].split()) for seg in ru_segments)

        en_words = translated_full.split()
        segments_en = []
        word_idx = 0

        for seg in ru_segments:
            seg_ru_words = len(seg["text"].split())
            ratio = seg_ru_words / total_ru_words if total_ru_words > 0 else 1 / len(ru_segments)
            en_word_count = max(1, round(len(en_words) * ratio))

            seg_en_words = en_words[word_idx:word_idx + en_word_count]
            word_idx += en_word_count

            segments_en.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": " ".join(seg_en_words)
            })

        # Handle any remaining words
        if word_idx < len(en_words) and segments_en:
            segments_en[-1]["text"] += " " + " ".join(en_words[word_idx:])

    except Exception as e:
        print(f"OpenAI translation failed ({e}), falling back to Google Translate...")
        segments_en = google_translate_fallback(transcript)
        translated_full = " ".join(s["text"] for s in segments_en)

    result = {"full_text": translated_full, "segments": segments_en}
    out = os.path.join(output_dir, "translation.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result

def google_translate_fallback(transcript: dict) -> list:
    from deep_translator import GoogleTranslator
    translator = GoogleTranslator(source="ru", target="en")
    segments_en = []
    for seg in transcript.get("segments", []):
        txt = seg["text"].strip()
        if not txt:
            continue
        try:
            translated = translator.translate(txt)
        except Exception:
            translated = txt
        segments_en.append({"start": seg["start"], "end": seg["end"], "text": translated})
        time.sleep(0.3)  # Rate limit
    return segments_en
