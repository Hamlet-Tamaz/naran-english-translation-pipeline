import os
import json
import time
from typing import List, Dict

def translate_hardened(transcript: dict, output_dir: str) -> dict:
    """Run multiple translation methods and cross-check for accuracy."""
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    from openai import OpenAI
    client = OpenAI(api_key=openai_key)

    ru_segments = [seg for seg in transcript.get("segments", []) if seg["text"].strip()]
    full_ru = " ".join(seg["text"].strip() for seg in ru_segments)

    print("  [HARDEN] Method 1: GPT-4o with full context...")
    trans1 = translate_gpt4o_contextual(client, ru_segments, full_ru)

    print("  [HARDEN] Method 2: GPT-4o-mini literal...")
    trans2 = translate_gpt4o_literal(client, ru_segments, full_ru)

    print("  [HARDEN] Method 3: Back-translation check...")
    back_check = back_translate_check(client, trans1["full_text"], full_ru)

    print("  [HARDEN] Cross-comparing and resolving discrepancies...")
    final = resolve_translations(trans1, trans2, back_check, ru_segments)

    # Save all variants for review
    variants = {
        "method_1_contextual": trans1,
        "method_2_literal": trans2,
        "back_translation_score": back_check["similarity_score"],
        "back_translation_russian": back_check["back_russian"],
        "final": final
    }
    with open(os.path.join(output_dir, "translation_variants.json"), "w", encoding="utf-8") as f:
        json.dump(variants, f, ensure_ascii=False, indent=2)

    return final

def translate_gpt4o_contextual(client, ru_segments, full_ru):
    """GPT-4o with full context awareness — understands arguments and implications."""
    prompt = f"""You are translating a Russian educational video about Armenian history to English.

CRITICAL RULES:
1. Preserve the EXACT logical structure of arguments. If someone says "X is not in Y, therefore X didn't exist," you MUST keep that implication.
2. Do not soften, generalize, or reframe arguments. Translate what is ACTUALLY said.
3. Distinguish between:
   - Claims being presented (e.g., "They say Jesus never met Armenians")
   - Counter-arguments (e.g., "But this ignores historical sources")
4. If a statement implies non-existence from absence of mention, preserve that implication.

Russian transcript:
{full_ru}

Return JSON:
{{"segments": [{{"speaker": "Naran", "text": "...", "start": 0.0, "end": 5.0}}]}}"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "Precise historical translator. Preserve argument logic exactly."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.1,
        max_tokens=4000,
        response_format={"type": "json_object"}
    )
    result = json.loads(response.choices[0].message.content.strip())
    segments = result.get("segments", [])
    full = " ".join(s["text"] for s in segments)
    return {"full_text": full, "segments": segments}

def translate_gpt4o_literal(client, ru_segments, full_ru):
    """GPT-4o-mini literal translation — word-for-word accuracy check."""
    prompt = f"""Translate this Russian text to English literally and precisely.
Do NOT reframe arguments. Do NOT add interpretation.
Translate EXACTLY what is said, preserving all logical implications.

Russian:
{full_ru}

Return JSON: {{"segments": [{{"speaker": "Naran", "text": "...", "start": 0.0, "end": 5.0}}]}}"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=4000,
        response_format={"type": "json_object"}
    )
    result = json.loads(response.choices[0].message.content.strip())
    segments = result.get("segments", [])
    full = " ".join(s["text"] for s in segments)
    return {"full_text": full, "segments": segments}

def back_translate_check(client, english_text, original_russian):
    """Translate English back to Russian and compare with original."""
    prompt = f"""Translate this English text back to Russian. Be as literal as possible.

English:
{english_text}

Return ONLY the Russian translation, nothing else."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2000
    )
    back_ru = response.choices[0].message.content.strip()

    # Simple similarity: word overlap ratio
    orig_words = set(original_russian.lower().split())
    back_words = set(back_ru.lower().split())
    if orig_words:
        overlap = len(orig_words & back_words) / len(orig_words)
    else:
        overlap = 0.0

    return {
        "back_russian": back_ru,
        "similarity_score": round(overlap, 3),
        "original_word_count": len(orig_words),
        "back_word_count": len(back_words)
    }

def resolve_translations(trans1, trans2, back_check, ru_segments):
    """Compare two translations and pick the best, flagging discrepancies."""
    segs1 = trans1["segments"]
    segs2 = trans2["segments"]

    # Use contextual (trans1) as base — it's better at argument structure
    # But check each segment against literal (trans2) for key phrase accuracy
    final_segments = []

    for i, seg1 in enumerate(segs1):
        if i < len(segs2):
            seg2 = segs2[i]
            # If literal translation contains key phrases contextual missed, flag it
            text1 = seg1["text"]
            text2 = seg2["text"]

            # Check for critical implication phrases
            implication_phrases = ["didn't exist", "never existed", "not real", "fabricated", "made up"]
            has_implication_1 = any(p in text1.lower() for p in implication_phrases)
            has_implication_2 = any(p in text2.lower() for p in implication_phrases)

            if has_implication_2 and not has_implication_1:
                # Literal caught an implication contextual missed — use literal for this segment
                print(f"    [FLAG] Segment {i}: Literal caught implication contextual missed. Using literal.")
                final_segments.append({**seg1, "text": text2, "translation_confidence": "low_flagged"})
            else:
                final_segments.append({**seg1, "translation_confidence": "high"})
        else:
            final_segments.append({**seg1, "translation_confidence": "high"})

    full = " ".join(s["text"] for s in final_segments)
    return {"full_text": full, "segments": final_segments, "back_translation_score": back_check["similarity_score"]}
