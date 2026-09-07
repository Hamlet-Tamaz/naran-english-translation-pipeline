import os
import json

def diarize_audio(audio_path: str, output_dir: str) -> list:
    """Run pyannote.audio speaker diarization. Returns list of {start, end, speaker}.
    Requires HF_TOKEN env var for model download."""

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        print("  Diarization: HF_TOKEN not set, skipping pyannote.audio")
        return []

    try:
        from huggingface_hub import login
        from pyannote.audio import Pipeline

        # Login to Hugging Face
        login(token=hf_token)

        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")

        print("  Running pyannote.audio diarization...")
        diarization = pipeline(audio_path)

        segments = []
        speaker_map = {}
        speaker_counter = 1

        for turn, _, speaker in diarization.itertracks(yield_label=True):
            if speaker not in speaker_map:
                speaker_map[speaker] = f"Speaker{speaker_counter}"
                speaker_counter += 1

            segments.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": speaker_map[speaker]
            })

        # Save raw diarization
        out = os.path.join(output_dir, "diarization.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"segments": segments, "speaker_map": speaker_map}, f, indent=2)

        print(f"  Diarization: {len(segments)} segments, {len(speaker_map)} speakers")
        return segments

    except Exception as e:
        print(f"  Diarization failed: {e}")
        return []

def pause_heuristic_diarization(transcript: dict, pause_threshold: float = 1.5) -> list:
    """Detect speaker changes based on long pauses between words."""
    segments = []
    current_speaker = "Speaker1"
    speaker_counter = 1

    for i, seg in enumerate(transcript.get("segments", [])):
        if i > 0:
            prev_end = transcript["segments"][i-1]["end"]
            pause = seg["start"] - prev_end
            if pause > pause_threshold:
                speaker_counter += 1
                current_speaker = f"Speaker{speaker_counter}"

        segments.append({
            "start": seg["start"],
            "end": seg["end"],
            "speaker": current_speaker,
            "text": seg.get("text", "")
        })

    return segments

def compare_methods(gpt4o_segments: list, diarization_segments: list, pause_segments: list) -> dict:
    """Compare speaker detection methods and return analysis."""

    gpt4o_speakers = set(s.get("speaker", "Naran") for s in gpt4o_segments)
    diarization_speakers = set(s.get("speaker", "Naran") for s in diarization_segments) if diarization_segments else set()
    pause_speakers = set(s.get("speaker", "Naran") for s in pause_segments)

    comparison = {
        "gpt4o": {
            "method": "GPT-4o text analysis",
            "speakers_found": sorted(list(gpt4o_speakers)),
            "segment_count": len(gpt4o_segments),
            "cost": "~$0.05 per video",
            "pros": ["Understands context", "Knows Naran vs Kamran", "Handles quoted text"],
            "cons": ["Misses acoustic cues", "May miss 3rd speaker if text is ambiguous"]
        },
        "pyannote": {
            "method": "pyannote.audio (acoustic)",
            "speakers_found": sorted(list(diarization_speakers)),
            "segment_count": len(diarization_segments),
            "cost": "$0 (local, requires HF_TOKEN)",
            "pros": ["Detects actual voice changes", "No text ambiguity", "Finds all acoustic speakers"],
            "cons": ["Requires HF_TOKEN", "Heavy model (~1.2GB)", "Cannot distinguish same-voice quotes"]
        },
        "pause_heuristic": {
            "method": "Pause-based heuristic",
            "speakers_found": sorted(list(pause_speakers)),
            "segment_count": len(pause_segments),
            "cost": "$0",
            "pros": ["Instant, no API", "Detects natural pauses", "Lightweight"],
            "cons": ["False positives on breaths", "Misses rapid speaker switches", "No semantic understanding"]
        },
        "recommendation": "GPT-4o primary for Naran/Kamran context. pyannote.audio as validation when HF_TOKEN available."
    }

    return comparison
