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
from diarize import diarize_audio, pause_heuristic_diarization, compare_methods

def get_next_version(output_dir: str, video_id: str) -> int:
    versions_file = os.path.join(output_dir, video_id, "versions.json")
    if os.path.exists(versions_file):
        with open(versions_file) as f:
            data = json.load(f)
        versions = data.get("versions", [])
        return max(v["number"] for v in versions) + 1 if versions else 1
    return 1

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
    base_dir = os.path.join(args.output_dir, video_id)
    os.makedirs(base_dir, exist_ok=True)

    version = get_next_version(args.output_dir, video_id)
    out_dir = os.path.join(base_dir, f"v{version}")
    os.makedirs(out_dir, exist_ok=True)

    print(f"Processing: {video_id} → v{version}")
    print("  [1/6] Extracting audio...")
    audio = extract_audio(video_path, out_dir)

    print("  [2/6] Transcribing Russian...")
    transcript = transcribe(audio, out_dir)

    print("  [3/6] Translating to English (GPT-4o + speaker detection)...")
    translation = translate(transcript, out_dir)

    print("  [4/6] Running alternative speaker detection...")
    # Pause heuristic (always runs)
    pause_diarization = pause_heuristic_diarization(transcript)

    # pyannote.audio (if HF_TOKEN available)
    pyannote_diarization = diarize_audio(audio, out_dir)

    # Compare methods
    comparison = compare_methods(
        translation.get("segments", []),
        pyannote_diarization,
        pause_diarization
    )
    comp_path = os.path.join(out_dir, "speaker_comparison.json")
    with open(comp_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, ensure_ascii=False, indent=2)
    print(f"  Speaker comparison saved: {comp_path}")

    print("  [5/6] Generating voiceover...")
    voiceover_path, voiceover_duration = gen_voiceover(translation, out_dir)

    print("  [6/6] Burning subtitles & rendering...")
    final = burn(video_path, translation, voiceover_path, voiceover_duration, out_dir)

    print("  Generating caption...")
    gen_caption(translation, out_dir)

    # Update versions.json
    versions_file = os.path.join(base_dir, "versions.json")
    versions_data = {"versions": []}
    if os.path.exists(versions_file):
        with open(versions_file) as f:
            versions_data = json.load(f)

    versions_data["versions"].append({
        "number": version,
        "folder": f"v{version}",
        "created_at": "auto",  # GitHub Actions will set this
        "speakers_found": sorted(list(set(s.get("speaker", "Naran") for s in translation.get("segments", [])))),
        "voiceover_duration": voiceover_duration
    })

    with open(versions_file, "w") as f:
        json.dump(versions_data, f, indent=2)

    meta = {
        "video_id": video_id,
        "version": version,
        "original": video_path,
        "output_dir": out_dir,
        "final_video": final,
        "voiceover_duration": voiceover_duration,
        "status": "completed"
    }
    with open(os.path.join(out_dir, "metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Done! v{version} → {out_dir}/")

if __name__ == "__main__":
    main()
