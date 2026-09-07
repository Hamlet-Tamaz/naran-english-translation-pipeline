import os

def generate(translation, output_dir):
    text = translation["full_text"]
    segments = translation.get("segments", [])

    speaker_counts = {}
    for seg in segments:
        sp = seg.get("speaker", "Naran")
        speaker_counts[sp] = speaker_counts.get(sp, 0) + 1

    speaker_list = []
    if "Naran" in speaker_counts:
        speaker_list.append("• Naran Hangai — Host & historical analysis")
    if "Kamran" in speaker_counts:
        speaker_list.append("• Kamran — Recurring commenter whose claims are debunked")
    if "Other Speaker" in speaker_counts:
        speaker_list.append("• Other Speaker — Quoted historical sources & references")
    # Handle any CommenterN or SpeakerN labels
    for sp in sorted(speaker_counts.keys()):
        if sp.startswith("Commenter") and sp not in ("Commenter",):
            speaker_list.append(f"• {sp} — Additional quoted source")
        elif sp.startswith("Speaker") and sp[7:].isdigit() and sp not in ("Speaker1", "Speaker2"):
            speaker_list.append(f"• {sp} — Detected speaker")

    if not speaker_list:
        speaker_list = ["• Naran Hangai — Host commentary"]

    speaker_section = "\n".join(speaker_list)

    # Build flow showing speaker transitions
    flow_parts = []
    current = None
    for seg in segments[:10]:  # Show first 10 segments for flow preview
        sp = seg.get("speaker", "Naran")
        label = sp
        if sp != current or len(flow_parts) < 4:
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
