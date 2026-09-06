import os
import json

def translate_hardened(transcript: dict, output_dir: str, robustness: str = "standard") -> dict:
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    from openai import OpenAI
    client = OpenAI(api_key=openai_key)

    ru_segments = [seg for seg in transcript.get("segments", []) if seg["text"].strip()]
    full_ru = " ".join(seg["text"].strip() for seg in ru_segments)

    rules = load_rules()

    if robustness == "free":
        print("  [Mode: FREE] Google Translate only")
        final = translate_google_only(ru_segments)
    elif robustness == "basic":
        print("  [Mode: BASIC] GPT-4o-mini single pass")
        final = translate_gpt4o_mini(client, ru_segments, full_ru)
    elif robustness == "standard":
        print("  [Mode: STANDARD] GPT-4o contextual + speaker detection")
        final = translate_gpt4o_contextual(client, ru_segments, full_ru)
    elif robustness in ("hardened", "maximum"):
        print("  [Mode: HARDENED] Dual translation + back-check + rules")
        trans1 = translate_gpt4o_contextual(client, ru_segments, full_ru)
        trans2 = translate_gpt4o_literal(client, ru_segments, full_ru)
        back = back_translate_check(client, trans1["full_text"], full_ru)
        final = resolve_translations(trans1, trans2, back, ru_segments)
        final["back_translation_score"] = back["similarity_score"]
    else:
        final = translate_gpt4o_contextual(client, ru_segments, full_ru)

    final = apply_rules(final, rules)

    variants = {
        "robustness": robustness,
        "rules_applied": [r["id"] for r in rules["rules"]],
        "final": final
    }
    if robustness in ("hardened", "maximum"):
        variants["method_1_contextual"] = trans1
        variants["method_2_literal"] = trans2
        variants["back_translation"] = back

    with open(os.path.join(output_dir, "translation_variants.json"), "w", encoding="utf-8") as f:
        json.dump(variants, f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "original_russian.txt"), "w", encoding="utf-8") as f:
        f.write(full_ru)

    return final

def load_rules() -> dict:
    rules_path = os.path.join(os.path.dirname(__file__), "rules.json")
    if os.path.exists(rules_path):
        with open(rules_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"rules": []}

def apply_rules(translation: dict, rules: dict) -> dict:
    for rule in rules.get("rules", []):
        if rule.get("severity") != "critical":
            continue
        incorrect = rule.get("pattern_en_incorrect", "")
        correct = rule.get("pattern_en_correct", "")

        for seg in translation.get("segments", []):
            text = seg.get("text", "")
            if incorrect.lower() in text.lower() and correct.lower() not in text.lower():
                seg["text"] = text.replace(incorrect, correct).replace(incorrect.capitalize(), correct.capitalize())
                seg["rule_applied"] = rule["id"]
                print(f"    [RULE {rule['id']}] Fixed: '{incorrect}' -> '{correct}'")
                rule["applied_count"] = rule.get("applied_count", 0) + 1

    translation["full_text"] = " ".join(s["text"] for s in translation.get("segments", []))
    return translation

def parse_segments_response(response_text: str, fallback_segments: list) -> list:
    """Parse OpenAI JSON response, handling various formats."""
    try:
        data = json.loads(response_text)
        # Try different possible structures
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "segments" in data and isinstance(data["segments"], list):
                return data["segments"]
            if "text" in data and isinstance(data["text"], str):
                # Single text response — split by timing
                return [{"start": s["start"], "end": s["end"], "text": data["text"], "speaker": "Naran"} for s in fallback_segments]
    except json.JSONDecodeError:
        pass

    # Fallback: use original segments with placeholder text
    print("    Warning: Could not parse translation response, using fallback")
    return [{"start": s["start"], "end": s["end"], "text": s["text"], "speaker": "Naran"} for s in fallback_segments]

def translate_google_only(ru_segments: list) -> dict:
    from deep_translator import GoogleTranslator
    translator = GoogleTranslator(source="ru", target="en")
    segments = []
    for seg in ru_segments:
        txt = seg["text"].strip()
        try:
            en = translator.translate(txt)
        except Exception:
            en = txt
        segments.append({"start": seg["start"], "end": seg["end"], "text": en, "speaker": "Naran"})
    return {"full_text": " ".join(s["text"] for s in segments), "segments": segments}

def translate_gpt4o_mini(client, ru_segments, full_ru):
    prompt = "Translate this Russian text to English. Preserve all negation exactly.\n\nRussian:\n" + full_ru + "\n\nReturn a JSON object with a 'segments' array. Each segment must have: start (number), end (number), text (string), speaker (string)."
    response = client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
        temperature=0.1, max_tokens=4000, response_format={"type": "json_object"}
    )
    segments = parse_segments_response(response.choices[0].message.content.strip(), ru_segments)
    return {"full_text": " ".join(s.get("text", "") for s in segments), "segments": segments}

def translate_gpt4o_contextual(client, ru_segments, full_ru):
    prompt = """Translate Russian to English. PRESERVE ALL NEGATION EXACTLY.
Rules:
1. "не встречал" = "did NOT meet" (never "met")
2. "армян нет" = "there are NO Armenians" (never "Armenians are")
3. "не упоминаются" = "are NOT mentioned"
4. Keep argument structure intact

Russian:
""" + full_ru + """

Return a JSON object with a 'segments' array. Each segment must have: start (number), end (number), text (string), speaker (string)."""
    response = client.chat.completions.create(
        model="gpt-4o", messages=[
            {"role": "system", "content": "Precise translator. NEVER flip negations."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1, max_tokens=4000, response_format={"type": "json_object"}
    )
    segments = parse_segments_response(response.choices[0].message.content.strip(), ru_segments)
    return {"full_text": " ".join(s.get("text", "") for s in segments), "segments": segments}

def translate_gpt4o_literal(client, ru_segments, full_ru):
    prompt = "Literal translation. Word-for-word. Do NOT reframe.\n\nRussian:\n" + full_ru + "\n\nReturn a JSON object with a 'segments' array. Each segment must have: start (number), end (number), text (string), speaker (string)."
    response = client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
        temperature=0.1, max_tokens=4000, response_format={"type": "json_object"}
    )
    segments = parse_segments_response(response.choices[0].message.content.strip(), ru_segments)
    return {"full_text": " ".join(s.get("text", "") for s in segments), "segments": segments}

def back_translate_check(client, english_text, original_russian):
    prompt = "Translate this English back to Russian literally:\n\n" + english_text + "\n\nReturn ONLY Russian."
    response = client.chat.completions.create(
        model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}],
        temperature=0.1, max_tokens=2000
    )
    back_ru = response.choices[0].message.content.strip()
    orig_words = set(original_russian.lower().split())
    back_words = set(back_ru.lower().split())
    overlap = len(orig_words & back_words) / len(orig_words) if orig_words else 0.0
    return {"back_russian": back_ru, "similarity_score": round(overlap, 3)}

def resolve_translations(trans1, trans2, back_check, ru_segments):
    final_segments = []
    for i, seg1 in enumerate(trans1["segments"]):
        seg2 = trans2["segments"][i] if i < len(trans2["segments"]) else seg1
        text1, text2 = seg1.get("text", ""), seg2.get("text", "")
        negation_words = ["not", "never", "no", "nothing", "nobody", "nowhere"]
        has_neg1 = any(n in text1.lower() for n in negation_words)
        has_neg2 = any(n in text2.lower() for n in negation_words)
        if has_neg2 and not has_neg1:
            final_segments.append({**seg1, "text": text2, "translation_confidence": "low_flagged"})
        else:
            final_segments.append({**seg1, "translation_confidence": "high"})
    full = " ".join(s["text"] for s in final_segments)
    return {"full_text": full, "segments": final_segments}
