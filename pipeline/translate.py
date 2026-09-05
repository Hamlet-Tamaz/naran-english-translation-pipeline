import os
import json
import time

def translate(transcript: dict, output_dir: str) -> dict:
    segments_en = []
    openai_key = os.environ.get("OPENAI_API_KEY")

    if openai_key:
        try:
            segments_en = openai_translate_with_speakers(transcript, openai_key)
            print("  Translation: OpenAI GPT-4o-mini + speaker detection")
        except Exception as e:
            print(f"  OpenAI speaker detection failed ({e}), using simple translation...")
            try:
                segments_en = openai_translate_simple(transcript, openai_key)
                print("  Translation: OpenAI GPT-4o-mini (no speakers)")
            except Exception as e2:
                print(f"  OpenAI simple also failed ({e2}), falling back to Google...")
                segments_en = []
    else:
        print("  OPENAI_API_KEY not set, falling back to Google Translate...")

    if not segments_en:
        segments_en = google_translate_fallback(transcript)
        print("  Translation: Google Translate (fallback, no speakers)")

    full_text = " ".join(s["text"] for s in segments_en)
    result = {"full_text": full_text, "segments": segments_en}

    out = os.path.join(output_dir, "translation.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result

def openai_translate_with_speakers(transcript: dict, api_key: str) -> list:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    ru_segments = []
    for seg in transcript.get("segments", []):
        if seg["text"].strip():
            ru_segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip()
            })

    prompt = f"""You are analyzing a Russian transcript from an educational video by Naran Hangai. The host discusses historical claims about Armenia, frequently quoting or responding to arguments from other people. There may be MULTIPLE different commentators quoted.

Here is the transcript divided into timed segments:
{json.dumps(ru_segments, ensure_ascii=False, indent=2)}

Your task:
1. Identify EACH distinct speaker. There may be 1-4 different people. Look for:
   - "Naran" — the host. He introduces topics, says "let's check", "I found", "now let's see", "they tell us", gives analysis and debunking
   - "Commenter1", "Commenter2", etc. — people he quotes or responds to. Look for phrases like "some say", "they claim", "according to X", or when he introduces an opposing view before debunking it. Each DISTINCT opposing view or quoted source should be a separate commenter.
   - If the same quoted argument reappears, assign it to the SAME commenter number
2. Translate each segment to natural, conversational English
3. Return a JSON object with this exact structure:
{{
  "segments": [
    {{"speaker": "Naran", "text": "English translation", "start": 0.0, "end": 5.2}},
    {{"speaker": "Commenter1", "text": "English translation", "start": 5.2, "end": 10.1}},
    ...
  ]
}}

Guidelines:
- Naran is the host who debunks claims. He usually speaks the majority of the video.
- Commenter1, Commenter2, etc. are distinct people whose arguments he quotes and then refutes.
- If you cannot distinguish between commenters, use "Commenter1" for all non-Naran speech.
- Preserve all content — don't skip any text.
- Make the English natural and conversational.
- Keep segments roughly the same length as the original."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a precise translator and transcript editor. Always respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=4000,
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content.strip())
    segments = result.get("segments", [])

    original_count = len(ru_segments)
    if len(segments) < original_count * 0.3 or len(segments) > original_count * 3:
        raise ValueError(f"Segment count mismatch: got {len(segments)}, expected ~{original_count}")

    # Normalize speaker names
    for seg in segments:
        sp = seg.get("speaker", "Naran")
        if sp.lower() in ("naran", "host", "speaker"):
            seg["speaker"] = "Naran"
        elif "commenter" in sp.lower():
            seg["speaker"] = sp  # Keep as Commenter1, Commenter2, etc.
        else:
            seg["speaker"] = "Naran"

    return segments

def openai_translate_simple(transcript: dict, api_key: str) -> list:
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
            "text": " ".join(seg_en_words),
            "speaker": "Naran"
        })

    if word_idx < len(en_words) and segments_en:
        segments_en[-1]["text"] += " " + " ".join(en_words[word_idx:])

    return segments_en

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
        segments_en.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": translated,
            "speaker": "Naran"
        })
        time.sleep(0.3)
    return segments_en
