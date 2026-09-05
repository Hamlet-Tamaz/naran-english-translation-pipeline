import os
import json
import time

def translate(transcript: dict, output_dir: str) -> dict:
    """Translate Russian transcript to English. Priority: Kimi > OpenAI > Google."""
    segments_en = []

    # Try Kimi first (cheapest, user already pays for Allegro)
    kimi_key = os.environ.get("KIMI_API_KEY")
    if kimi_key:
        try:
            segments_en = kimi_translate(transcript, kimi_key)
            print("  Translation: Kimi (Allegro plan)")
        except Exception as e:
            print(f"  Kimi failed ({e}), trying OpenAI...")
            segments_en = []

    # Try OpenAI if Kimi not available or failed
    if not segments_en:
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                segments_en = openai_translate(transcript, openai_key)
                print("  Translation: OpenAI GPT-4o-mini")
            except Exception as e:
                print(f"  OpenAI failed ({e}), falling back to Google...")
                segments_en = []

    # Fallback to Google Translate
    if not segments_en:
        segments_en = google_translate_fallback(transcript)
        print("  Translation: Google Translate (fallback)")

    full_text = " ".join(s["text"] for s in segments_en)
    result = {"full_text": full_text, "segments": segments_en}

    out = os.path.join(output_dir, "translation.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result

def kimi_translate(transcript: dict, api_key: str) -> list:
    """Translate using Kimi API (Moonshot AI)."""
    import requests

    full_ru = " ".join(seg["text"].strip() for seg in transcript.get("segments", []) if seg["text"].strip())

    response = requests.post(
        "https://api.moonshot.cn/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "moonshot-v1-8k",
            "messages": [
                {"role": "system", "content": "You are a precise translator. Translate the following Russian text to natural, conversational English. Preserve the tone and meaning exactly. Do not add explanations or notes."},
                {"role": "user", "content": full_ru}
            ],
            "temperature": 0.3
        },
        timeout=60
    )
    response.raise_for_status()
    translated_full = response.json()["choices"][0]["message"]["content"].strip()

    return split_into_segments(translated_full, transcript)

def openai_translate(transcript: dict, api_key: str) -> list:
    """Translate using OpenAI GPT-4o-mini."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    full_ru = " ".join(seg["text"].strip() for seg in transcript.get("segments", []) if seg["text"].strip())

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a precise translator. Translate the following Russian text to natural, conversational English. Preserve the tone and meaning exactly. Do not add explanations or notes."},
            {"role": "user", "content": full_ru}
        ],
        temperature=0.3,
        max_tokens=2000
    )
    translated_full = response.choices[0].message.content.strip()

    return split_into_segments(translated_full, transcript)

def split_into_segments(translated_full: str, transcript: dict) -> list:
    """Split translated text into segments matching original timing."""
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

    if word_idx < len(en_words) and segments_en:
        segments_en[-1]["text"] += " " + " ".join(en_words[word_idx:])

    return segments_en

def google_translate_fallback(transcript: dict) -> list:
    """Fallback to Google Translate."""
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
        time.sleep(0.3)
    return segments_en
