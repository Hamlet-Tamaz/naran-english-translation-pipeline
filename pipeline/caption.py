import os

def generate(translation, output_dir):
    text = translation["full_text"]
    segments = translation.get("segments", [])

    speakers = {}
    for seg in segments:
        sp = seg.get("speaker", "Naran")
        speakers[sp] = speakers.get(sp, 0) + 1

    speaker_list = []
    if "Naran" in speakers:
        speaker_list.append("• Naran Hangai — Host commentary")
    if "Other" in speakers:
        speaker_list.append("• Various commentators — Historical claims and arguments quoted for context")

    speaker_section = "\n".join(speaker_list) if speaker_list else "• Naran Hangai — Host commentary"

    flow_parts = []
    current = None
    for seg in segments[:6]:
        sp = seg.get("speaker", "Naran")
        if sp != current:
            label = "Naran" if sp == "Naran" else "Commenter"
            flow_parts.append(f"{label}: {seg['text'][:60]}...")
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
