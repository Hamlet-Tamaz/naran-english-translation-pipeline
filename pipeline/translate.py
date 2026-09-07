import os
import json
import time

def translate(transcript: dict, output_dir: str) -> dict:
    segments_en = []
    openai_key = os.environ.get("OPENAI_API_KEY")

    if openai_key:
        try:
            # Use GPT-4o for better speaker nuance detection
            segments_en = openai_translate_with_speakers(transcript, openai_key)
            print("  Translation: OpenAI GPT-4o + speaker detection")
        except Exception as e:
            print(f"  GPT-4o speaker detection failed ({e}), using GPT-4o-mini simple...")
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

    prompt = f"""You are analyzing a Russian transcript from Naran Hangai's educational video about Armenian history. There are TWO recurring characters you must identify:

**NARAN** — The host. He has a shaved head, a mole on his left cheek, and speaks directly to camera. He debunks historical claims using sources like Encyclopaedia Iranica, BibleHub, and the 1611 King James Bible. His style: "Let's check the sources," "They tell us that... but let's see what the texts actually say," "Now let's dispel this myth."

**KAMRAN** — A recurring commenter/character that Naran frequently debunks. Kamran presents nationalist/historical arguments claiming Armenia is fabricated, not in the Bible, etc. Naran quotes Kamran's arguments and then systematically refutes them. Kamran NEVER presents sources — only claims.

**OTHER COMMENTERS** — Occasionally Naran quotes other people (historians, Wikipedia, random internet comments). These are distinct from both Naran and Kamran.

Here is the transcript:
{json.dumps(ru_segments, ensure_ascii=False, indent=2)}

Your task:
1. Identify the speaker for EACH segment. Options: "Naran", "Kamran", or "Commenter"
2. Translate each segment to natural, conversational English
3. Return JSON:
{{
  "segments": [
    {{"speaker": "Naran", "text": "...", "start": 0.0, "end": 5.2}},
    {{"speaker": "Kamran", "text": "...", "start": 5.2, "end": 10.1}},
    ...
  ]
}}

Rules:
- If Naran says "They tell us..." or "Some claim..." followed by a claim, the CLAIM itself is Kamran/Commenter, Naran's rebuttal is Naran
- Naran often uses phrases: "Now let's see," "But wait," "According to [source]," "This is confirmed by"
- Kamran's arguments are usually unsourced nationalist claims
- Preserve all text — don't skip anything
- Keep natural, conversational English"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a precise translator and transcript editor. Always respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=4000,
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content.strip())
    segments = result.get("segments", [])

    # Validate and normalize
    valid_speakers = {"Naran", "Kamran", "Commenter"}
    for seg in segments:
        sp = seg.get("speaker", "Naran")
        if sp not in valid_speakers:
            seg["speaker"] = "Commenter"

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
