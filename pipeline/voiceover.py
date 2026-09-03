from gtts import gTTS
import os

def generate(text: str, output_dir: str) -> str:
    speech = text.replace("(", ",").replace(")", ",")
    path = os.path.join(output_dir, "voiceover.mp3")
    tts = gTTS(text=speech, lang="en", slow=False)
    tts.save(path)
    return path
