import os

def generate(text: str, output_dir: str) -> str:
    """Generate English voiceover with OpenAI TTS (male voice: onyx)."""
    path = os.path.join(output_dir, "voiceover.mp3")
    api_key = os.environ.get("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set. Cannot generate voiceover.")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        # onyx = deeper male voice; echo = younger male; fable = British male
        response = client.audio.speech.create(
            model="tts-1",
            voice="onyx",
            input=text,
            response_format="mp3"
        )
        response.stream_to_file(path)
        print("  Voiceover: OpenAI TTS (onyx — male)")
        return path
    except Exception as e:
        print(f"  OpenAI TTS failed ({e})")
        raise
