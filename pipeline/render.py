import argparse
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extract import extract_audio
from transcribe import transcribe
from translate import translate
from voiceover import generate as gen_voiceover
from subtitle import burn
from caption import generate as gen_caption

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default="processed")
    args = parser.parse_args()
    video_path = args.input
    if not os.path.exists(video_path):
        print(f"Video not found: {video_path}")
        sys.exit(1)
    video_id = Path(video_path).stem
    out_dir = os.path.join(args.output_dir, video_id)
    os.makedirs(out_dir, exist_ok=True)
    print(f"Processing: {video_id}")
    print("  [1/5] Extracting audio...")
    audio = extract_audio(video_path, out_dir)
    print("  [2/5] Transcribing Russian...")
    transcript = transcribe(audio, out_dir)
    print("  [3/5] Translating to English...")
    translation = translate(transcript, out_dir)
    print("  [4/5] Generating voiceover...")
    voiceover = gen_voiceover(translation["full_text"], out_dir)
    print("  [5/5] Burning subtitles & rendering...")
    final = burn(video_path, translation, voiceover, out_dir)
    print("  Generating caption...")
    gen_caption(translation, out_dir)
    meta = {
        "video_id": video_id,
        "original": video_path,
        "output_dir": out_dir,
        "final_video": final,
        "status": "completed"
    }
    with open(os.path.join(out_dir, "metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"Done! Output: {out_dir}/")

if __name__ == "__main__":
    main()
