import os

def generate(translation, output_dir):
    text = translation["full_text"]
    segments = translation.get("segments", [])

    # Collect unique speakers
    speaker_counts = {}
    for seg in segments:
        sp = seg.get("speaker", "Naran")
        speaker_counts[sp] = speaker_counts.get(sp, 0) + 1

    speaker_list = []
    if "Naran" in speaker_counts:
        speaker_list.append("• Naran Hangai — Host & historical analysis")

    commenters = sorted([k for k in speaker_counts if k != "Naran"])
    for i, c in enumerate(commenters, 1):
        speaker_list.append(f"• {c} — Historical claims and arguments quoted for context")

    if not speaker_list:
        speaker_list = ["• Naran Hangai — Host commentary"]

    speaker_section = "\n".join(speaker_list)

    # Build flow summary with speaker transitions
    flow_parts = []
    current = None
    for seg in segments[:8]:
        sp = seg.get("speaker", "Naran")
        label = "Naran" if sp == "Naran" else sp
        if sp != current or len(flow_parts) < 3:
            flow_parts.append(f"{label}: {seg['text'][:70]}...")
            current = sp
    flow_text = "\n".join(flow_parts) if flow_parts else text[:300]

    caption = f"""📜 Historical Fact-Check: Armenia in the Bible

🎙️ SPEAKERS:
{speaker_section}

📝 FLOW:
{flow_text}

🎙️ English voiceover narrates the original Russian analysis

🧭 FULL CONTEXT:
{text[:400]}...

📚 Sources shown: Encyclopaedia Iranica, BibleHub, BibleGateway, 1611 KJV first edition

🤝 Original content: @naran_hangai
🌍 Translated & narrated for educational purposes

#Armenia #BibleHistory #KingJamesBible #Ararat #Urartu #HistoricalLinguistics #NaranHangai #EducationalContent
"""

    path = os.path.join(output_dir, "caption.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(caption)
    return caption
