import os

def generate(translation: dict, output_dir: str) -> str:
    text = translation["full_text"]
    caption = f"""📜 Historical Fact-Check: Armenia in the Bible

🎙️ English voiceover narrates the original Russian analysis by @naran_hangai

🧭 CONTEXT:
{text[:300]}...

📚 Sources shown: Encyclopaedia Iranica, BibleHub, BibleGateway, 1611 KJV first edition

🤝 Original content: @naran_hangai
🌍 Translated & narrated for educational purposes

#Armenia #BibleHistory #KingJamesBible #Ararat #Urartu #HistoricalLinguistics #NaranHangai #EducationalContent
"""
    path = os.path.join(output_dir, "caption.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(caption)
    return caption
