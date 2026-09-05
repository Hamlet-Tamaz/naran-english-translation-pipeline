import os
from gtts import gTTS

def generate(text: str, output_dir: str) -> str:
    path = os.path.join(output_dir, "voiceover.mp3")
    api_key = os.environ.get("OPENAI_API_KEY")

    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            response = client.audio.speech.create(
                model="tts-1", voice="alloy", input=text, response_format="mp3"
            )
            response.stream_to_file(path)
            print("  Voiceover: OpenAI TTS")
            return path
        except Exception as e:
            print(f"  OpenAI TTS failed ({e}), using gTTS fallback...")
    else:
        print("  OPENAI_API_KEY not set, using gTTS...")

    speech = text.replace("(", ",").replace(")", ",")
    tts = gTTS(text=speech, lang="en", slow=False)
    tts.save(path)
    return path
