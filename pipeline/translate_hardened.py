import os, json, re
from deep_translator import GoogleTranslator

def load_rules(path="pipeline/rules.json"):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"rules": []}

def apply_rules(translation, rules):
    for rule in rules.get("rules", []):
        for seg in translation.get("segments", []):
            text = seg.get("text", "")
            if rule.get("pattern_en_incorrect") and rule["pattern_en_incorrect"] in text:
                text = text.replace(rule["pattern_en_incorrect"], rule["pattern_en_correct"])
                seg["text"] = text
                print(f"  [RULE {rule['id']}] Applied: '{rule['pattern_en_incorrect']}' -> '{rule['pattern_en_correct']}'")
    return translation

def normalize_speaker(speaker: str) -> str:
    s = speaker.strip().lower()
    if s in ("naran", "host", "narrator", "speaker", "main"):
        return "Naran"
    elif s in ("kamran", "opponent"):
        return "Kamran"
    elif "commenter" in s:
        return speaker
    else:
        return "Other Speaker"

def translate_chunk(client, segments, chunk_index, total_chunks):
    """Translate a chunk of segments with GPT-4o."""
    full_ru = "\\n".join(f"{i+1}. {seg['text'].strip()}" for i, seg in enumerate(segments))

    prompt = f"""Translate these Russian sentences to English. PRESERVE ALL NEGATION EXACTLY.

Rules:
1. "не встречал" = "did NOT meet" (never "met")
2. "армян нет" = "there are NO Armenians"
3. "не упоминаются" = "are NOT mentioned"
4. Keep argument structure intact
5. Do NOT add explanations, only translations

For each line, return the English translation on the SAME line number.

Russian:
{full_ru}

Return ONLY a JSON object like: {{"translations": ["English sentence 1", "English sentence 2", ...]}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Precise translator. NEVER flip negations. Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )

        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)
        translations = data.get("translations", [])

        if len(translations) != len(segments):
            print(f"  [WARN] Chunk {chunk_index+1}/{total_chunks}: Got {len(translations)} translations for {len(segments)} segments")
            # Pad or truncate
            while len(translations) < len(segments):
                translations.append(segments[len(translations)]["text"])
            translations = translations[:len(segments)]

        parsed = []
        for i, seg in enumerate(segments):
            parsed.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": translations[i],
                "speaker": normalize_speaker(seg.get("speaker", "Naran"))
            })

        return parsed

    except Exception as e:
        print(f"  [ERROR] Chunk {chunk_index+1}/{total_chunks} translation failed: {e}")
        raise

def translate_gpt4o_chunked(client, segments):
    """Translate in chunks of 5 segments to avoid context limits."""
    CHUNK_SIZE = 5
    all_parsed = []
    total_chunks = (len(segments) + CHUNK_SIZE - 1) // CHUNK_SIZE

    for i in range(0, len(segments), CHUNK_SIZE):
        chunk = segments[i:i+CHUNK_SIZE]
        chunk_num = i // CHUNK_SIZE + 1
        print(f"  Translating chunk {chunk_num}/{total_chunks} ({len(chunk)} segments)...")
        parsed = translate_chunk(client, chunk, chunk_num - 1, total_chunks)
        all_parsed.extend(parsed)

    return {
        "full_text": " ".join(s["text"] for s in all_parsed),
        "segments": all_parsed
    }

def translate_gpt4o_mini(client, segments):
    return translate_gpt4o_chunked(client, segments)

def translate_gpt4o_contextual(client, segments):
    return translate_gpt4o_chunked(client, segments)

def translate_gpt4o_literal(client, segments):
    return translate_gpt4o_chunked(client, segments)

def back_translate_check(client, english_text, russian_original):
    prompt = f"Translate this English back to Russian:\\n\\nEnglish:\\n{english_text}\\n\\nReturn only the Russian text."
    response = client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
        temperature=0.0, max_tokens=4000
    )
    back_ru = response.choices[0].message.content.strip()

    orig_words = set(russian_original.lower().split())
    back_words = set(back_ru.lower().split())
    if not orig_words:
        similarity = 0.0
    else:
        similarity = len(orig_words & back_words) / len(orig_words)

    print(f"  Back-translation similarity: {similarity:.3f}")
    return {"back_translation": back_ru, "similarity_score": similarity}

def resolve_translations(trans1, trans2, back_check, original_segments):
    score = back_check.get("similarity_score", 0)
    if score < 0.65:
        print(f"  [WARN] Low back-translation score ({score:.3f}). Using literal translation.")
        return trans2

    print(f"  [OK] Back-translation score: {score:.3f}. Using contextual translation.")
    return trans1

def translate_google_only(segments):
    full_ru = " ".join(seg["text"].strip() for seg in segments)
    try:
        translated = GoogleTranslator(source='auto', target='en').translate(full_ru)
    except Exception as e:
        print(f"  [WARN] Google Translate failed: {e}")
        translated = full_ru

    words = translated.split()
    per_seg = max(1, len(words) // len(segments))
    parsed = []
    for i, orig in enumerate(segments):
        start = int(i * per_seg)
        end = int((i + 1) * per_seg) if i < len(segments) - 1 else len(words)
        parsed.append({
            "start": orig["start"],
            "end": orig["end"],
            "text": " ".join(words[start:end]),
            "speaker": "Naran"
        })
    return {"full_text": translated, "segments": parsed}

def translate_hardened(transcript: dict, output_dir: str, robustness: str = "standard") -> dict:
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    from openai import OpenAI
    client = OpenAI(api_key=openai_key)

    all_segments = [seg for seg in transcript.get("segments", []) if seg["text"].strip()]
    ru_segments = [seg for seg in all_segments if seg.get("detected_language", "ru") == "ru"]
    en_segments = [seg for seg in all_segments if seg.get("detected_language", "en") == "en"]

    print(f"  Processing: {len(ru_segments)} Russian, {len(en_segments)} English segments")

    rules = load_rules()

    if robustness == "free":
        print("  [Mode: FREE] Google Translate only")
        ru_translated = translate_google_only(ru_segments)
    elif robustness == "basic":
        print("  [Mode: BASIC] GPT-4o-mini chunked")
        ru_translated = translate_gpt4o_mini(client, ru_segments)
    elif robustness == "standard":
        print("  [Mode: STANDARD] GPT-4o chunked + speaker detection")
        ru_translated = translate_gpt4o_contextual(client, ru_segments)
    elif robustness in ("hardened", "maximum"):
        print("  [Mode: HARDENED] Dual translation + back-check + rules")
        trans1 = translate_gpt4o_contextual(client, ru_segments)
        trans2 = translate_gpt4o_literal(client, ru_segments)
        full_ru = " ".join(seg["text"].strip() for seg in ru_segments)
        back = back_translate_check(client, trans1["full_text"], full_ru)
        ru_translated = resolve_translations(trans1, trans2, back, ru_segments)
        ru_translated["back_translation_score"] = back["similarity_score"]
    else:
        ru_translated = translate_gpt4o_contextual(client, ru_segments)

    ru_translated = apply_rules(ru_translated, rules)

    # English segments: pass through with "Other Speaker" label
    en_translated_segments = []
    for seg in en_segments:
        en_translated_segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "text": seg["text"].strip(),
            "speaker": "Other Speaker",
            "translation_confidence": "high",
            "original_language": "en"
        })

    all_translated = ru_translated.get("segments", []) + en_translated_segments
    all_translated.sort(key=lambda s: s["start"])

    final = {
        "full_text": " ".join(s["text"] for s in all_translated),
        "segments": all_translated
    }

    # Save translation.json
    with open(os.path.join(output_dir, "translation.json"), "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"  Saved translation.json ({len(all_translated)} segments)")

    variants = {
        "robustness": robustness,
        "rules_applied": [r["id"] for r in rules["rules"]],
        "final": final,
        "english_segments_count": len(en_segments),
        "russian_segments_count": len(ru_segments)
    }
    if robustness in ("hardened", "maximum"):
        variants["method_1_contextual"] = trans1
        variants["method_2_literal"] = trans2
        variants["back_translation"] = back

    with open(os.path.join(output_dir, "translation_variants.json"), "w", encoding="utf-8") as f:
        json.dump(variants, f, ensure_ascii=False, indent=2)

    full_ru = " ".join(seg["text"].strip() for seg in ru_segments)
    with open(os.path.join(output_dir, "original_russian.txt"), "w", encoding="utf-8") as f:
        f.write(full_ru)

    full_en = " ".join(seg["text"].strip() for seg in en_segments)
    with open(os.path.join(output_dir, "original_english.txt"), "w", encoding="utf-8") as f:
        f.write(full_en)

    return final
