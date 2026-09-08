import argparse
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extract import extract_audio
from transcribe import transcribe
from translate_hardened import translate_hardened
from voiceover import generate as gen_voiceover
from subtitle import burn
from caption import generate as gen_caption
from diarize import (
    diarize_audio, assign_acoustic_speakers, smooth_speaker_labels,
    name_clusters_gpt4o, pause_heuristic_diarization, compare_methods,
    compute_cluster_embeddings,
)
from speaker_bank import load_bank, match_clusters, load_corrections, apply_corrections

CANONICAL_SPEAKERS = ("Naran", "Kamran", "Other Speaker")

def analyze_speakers(audio_path: str, transcript: dict, out_dir: str, robustness: str, video_id: str) -> None:
    """Acoustic-first speaker analysis. Mutates transcript segments in place.

    pyannote decides WHO speaks WHEN; smoothing removes label flapping;
    the persistent VOICE BANK recognizes known voices (Naran first) across
    videos; GPT-4o names any remaining clusters using the structure prior;
    saved USER RULES (corrections.json) override everything.
    Falls back to GPT-4o text detection (inside translate_hardened) if
    diarization is unavailable."""
    segments = transcript.get("segments", [])
    if not segments:
        return
    if robustness not in ("standard", "hardened", "maximum"):
        return

    turns = diarize_audio(audio_path, out_dir)
    if not turns:
        print("  Acoustic diarization unavailable — translation will use GPT-4o text detection fallback")
        return

    segments = assign_acoustic_speakers(segments, turns)
    segments = smooth_speaker_labels(segments, min_block_s=3.0)

    # Persistent voice profiles: recognize confirmed speakers (Naran first)
    # from past videos BEFORE asking GPT-4o to name clusters.
    embeddings = compute_cluster_embeddings(audio_path, turns, out_dir)
    bank = load_bank()
    bank_matches = match_clusters(embeddings, bank) if embeddings else {}

    name_map = name_clusters_gpt4o(segments, out_dir)
    for cid, (pname, score) in bank_matches.items():
        name_map[cid] = pname  # voice bank is authoritative — it only
                               # contains user-confirmed voices
    if bank_matches:
        summary = {cid: f"{pname} ({score})" for cid, (pname, score) in bank_matches.items()}
        print(f"  Voice-bank matches: {summary}")

    for seg in segments:
        seg["speaker"] = name_map.get(seg.get("speaker"), "Naran")

    # User-saved attribution rules override any automatic naming.
    rules = load_corrections(video_id)
    if rules:
        segments, relabeled = apply_corrections(segments, rules)
        print(f"  Attribution rules: {len(rules)} saved rule(s) applied, {relabeled} segments relabeled")

    counts = {}
    for seg in segments:
        counts[seg["speaker"]] = counts.get(seg["speaker"], 0) + 1
    print(f"  Speakers (acoustic, smoothed, named): {counts}")
    transcript["segments"] = segments

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
    parser.add_argument("--robustness", default="standard", choices=["free", "basic", "standard", "hardened", "maximum"])
    args = parser.parse_args()

    video_path = args.input
    robustness = args.robustness
    if not os.path.exists(video_path):
        print(f"Video not found: {video_path}")
        sys.exit(1)

    video_id = Path(video_path).stem
    base_dir = os.path.join(args.output_dir, video_id)
    os.makedirs(base_dir, exist_ok=True)

    version = get_next_version(args.output_dir, video_id)
    out_dir = os.path.join(base_dir, f"v{version}")
    os.makedirs(out_dir, exist_ok=True)

    print(f"Processing: {video_id} → v{version} [robustness: {robustness}]")
    print("  [1/5] Extracting audio...")
    audio = extract_audio(video_path, out_dir)

    print("  [2/5] Transcribing Russian...")
    transcript = transcribe(audio, out_dir)

    print("  [2.5/5] Analyzing speakers (acoustic diarization)...")
    analyze_speakers(audio, transcript, out_dir, robustness, video_id)

    print("  [3/5] Translating...")
    translation = translate_hardened(transcript, out_dir, robustness)

    # Re-apply saved attribution rules post-translation: when diarization is
    # unavailable, translate_hardened's GPT text fallback assigns speakers
    # itself and would have overwritten the rule-based labels. User rules
    # always win; re-save translation.json so artifacts agree with the video.
    # apply_text=True: rules carrying text_override also merge their covered
    # segments into one with the user's edited English text.
    post_rules = load_corrections(video_id)
    if post_rules:
        translation["segments"], relabeled = apply_corrections(translation.get("segments", []), post_rules, apply_text=True)
        if relabeled:
            with open(os.path.join(out_dir, "translation.json"), "w", encoding="utf-8") as f:
                json.dump(translation, f, ensure_ascii=False, indent=2)
            print(f"  Attribution rules re-applied after translation ({relabeled} segments)")

    print("  [4/5] Generating voiceover...")
    voiceover_path, voiceover_duration = gen_voiceover(translation, out_dir)

    print("  [5/5] Burning subtitles & rendering...")
    final = burn(video_path, translation, voiceover_path, voiceover_duration, out_dir)

    print("  Generating caption...")
    gen_caption(translation, out_dir)

    # Write speaker comparison report (raw acoustic turns were saved by
    # analyze_speakers to diarization.json during step 2.5)
    if robustness in ("standard", "hardened", "maximum"):
        pause_diarization = pause_heuristic_diarization(transcript)
        raw_turns = []
        diar_path = os.path.join(out_dir, "diarization.json")
        if os.path.exists(diar_path):
            with open(diar_path) as f:
                raw_turns = json.load(f).get("turns", [])
        comparison = compare_methods(translation.get("segments", []), raw_turns, pause_diarization)
        with open(os.path.join(out_dir, "speaker_comparison.json"), "w", encoding="utf-8") as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)

    versions_file = os.path.join(base_dir, "versions.json")
    versions_data = {"versions": []}
    if os.path.exists(versions_file):
        with open(versions_file) as f:
            versions_data = json.load(f)

    versions_data["versions"].append({
        "number": version,
        "folder": f"v{version}",
        "robustness": robustness,
        "speakers_found": sorted(list(set(s.get("speaker", "Naran") for s in translation.get("segments", [])))),
        "voiceover_duration": voiceover_duration,
        "back_translation_score": translation.get("back_translation_score", 0)
    })
    with open(versions_file, "w") as f:
        json.dump(versions_data, f, indent=2)

    meta = {
        "video_id": video_id,
        "version": version,
        "robustness": robustness,
        "output_dir": out_dir,
        "final_video": final,
        "voiceover_duration": voiceover_duration,
        "back_translation_score": translation.get("back_translation_score", 0),
        "status": "completed"
    }
    with open(os.path.join(out_dir, "metadata.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Done! v{version} [{robustness}] → {out_dir}/")

if __name__ == "__main__":
    main()
