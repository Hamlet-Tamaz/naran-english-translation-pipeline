import os
import json

# ---------------------------------------------------------------------------
# Robust speaker pipeline
#
# Philosophy:
#   1. ACOUSTICS decide WHO speaks WHEN (pyannote diarization).
#      Same voice anywhere in the video = same cluster = same voiceover voice.
#   2. SMOOTHING removes label flapping (hysteresis: no sub-3s speaker runs,
#      single-segment spikes are reverted to the surrounding speaker).
#   3. GPT-4o only NAMES the acoustic clusters (Naran / Kamran / Other Speaker)
#      using the video's known structure as a prior:
#      Naran intro -> Kamran speaks (middle) -> Naran rebuts -> Other Speaker
#      (English) at the end. A cluster heard at both the start AND after the
#      middle block is Naran both times.
# ---------------------------------------------------------------------------


def diarize_audio(audio_path: str, output_dir: str) -> list:
    """Run pyannote.audio speaker diarization. Returns list of
    {start, end, speaker} with raw acoustic cluster ids (CLUSTER_0, ...).
    Requires HF_TOKEN env var for model download."""

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        print("  Diarization: HF_TOKEN not set, skipping pyannote.audio")
        return []

    try:
        from huggingface_hub import login
        from pyannote.audio import Pipeline

        login(token=hf_token)

        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")

        print("  Running pyannote.audio diarization...")
        diarization = pipeline(audio_path)

        turns = []
        cluster_map = {}

        for turn, _, speaker in diarization.itertracks(yield_label=True):
            if speaker not in cluster_map:
                cluster_map[speaker] = f"CLUSTER_{len(cluster_map)}"
            turns.append({
                "start": round(turn.start, 2),
                "end": round(turn.end, 2),
                "speaker": cluster_map[speaker]
            })

        # Merge adjacent turns of the same cluster
        turns = merge_adjacent_turns(turns)

        out = os.path.join(output_dir, "diarization.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"turns": turns, "cluster_map": cluster_map}, f, indent=2)

        counts = {}
        for t in turns:
            counts[t["speaker"]] = counts.get(t["speaker"], 0) + 1
        print(f"  Diarization: {len(turns)} turns, clusters: {counts}")
        return turns

    except Exception as e:
        print(f"  Diarization failed: {e}")
        return []


def merge_adjacent_turns(turns: list, max_gap_s: float = 0.3) -> list:
    """Merge consecutive turns of the same cluster separated by < max_gap_s."""
    if not turns:
        return turns
    merged = [dict(turns[0])]
    for t in turns[1:]:
        prev = merged[-1]
        if t["speaker"] == prev["speaker"] and t["start"] - prev["end"] <= max_gap_s:
            prev["end"] = t["end"]
        else:
            merged.append(dict(t))
    return merged


def assign_acoustic_speakers(whisper_segments: list, turns: list) -> list:
    """Assign each Whisper segment the acoustic cluster with maximum
    temporal overlap. Segments keep all their fields; 'speaker' becomes
    the cluster id."""
    for seg in whisper_segments:
        best_cluster = None
        best_overlap = 0.0
        for t in turns:
            overlap = min(seg["end"], t["end"]) - max(seg["start"], t["start"])
            if overlap > best_overlap:
                best_overlap = overlap
                best_cluster = t["speaker"]
        seg["speaker"] = best_cluster or "CLUSTER_0"
    return whisper_segments


def smooth_speaker_labels(segments: list, min_block_s: float = 3.0) -> list:
    """Hysteresis smoothing — don't be eager to switch speakers.

    Pass 1 (despike): a segment whose neighbors on BOTH sides share the same
    speaker, and which is shorter than min_block_s, reverts to that speaker.

    Pass 2 (short-run absorption): iteratively merge any run of consecutive
    same-speaker segments whose total duration < min_block_s into its longer
    neighbor. Repeats until stable.
    """
    if not segments:
        return segments

    segs = segments  # mutate in place
    eps = 1e-6

    # Pass 1: despike
    for i in range(1, len(segs) - 1):
        prev_sp = segs[i - 1].get("speaker")
        next_sp = segs[i + 1].get("speaker")
        cur_sp = segs[i].get("speaker")
        dur = segs[i]["end"] - segs[i]["start"]
        if cur_sp != prev_sp and prev_sp == next_sp and dur < min_block_s + eps:
            segs[i]["speaker"] = prev_sp

    # Pass 2: absorb short runs
    def get_runs():
        runs = []
        for s in segs:
            sp = s.get("speaker")
            dur = s["end"] - s["start"]
            if runs and runs[-1]["speaker"] == sp:
                runs[-1]["duration"] += dur
                runs[-1]["count"] += 1
            else:
                runs.append({"speaker": sp, "duration": dur, "count": 1})
        return runs

    for _ in range(10):  # iteration cap
        runs = get_runs()
        if len(runs) <= 1:
            break
        # find shortest run at or below threshold
        short_idx = None
        short_dur = min_block_s + eps
        for idx, r in enumerate(runs):
            if r["duration"] < short_dur:
                short_dur = r["duration"]
                short_idx = idx
        if short_idx is None:
            break  # all runs are long enough

        # choose neighbor to absorb into: the longer one; prefer previous on tie
        prev_dur = runs[short_idx - 1]["duration"] if short_idx > 0 else -1
        next_dur = runs[short_idx + 1]["duration"] if short_idx < len(runs) - 1 else -1
        if prev_dur >= next_dur and short_idx > 0:
            target_sp = runs[short_idx - 1]["speaker"]
        else:
            target_sp = runs[short_idx + 1]["speaker"]

        # retag the short run's segments (run order == segment order)
        idx = 0
        for r_i, r in enumerate(runs):
            for _ in range(r["count"]):
                if r_i == short_idx:
                    segs[idx]["speaker"] = target_sp
                idx += 1

    return segs


def name_clusters_gpt4o(segments: list, output_dir: str) -> dict:
    """Map acoustic cluster ids to canonical speaker names using GPT-4o,
    guided by the known video structure. Returns {cluster_id: name}.
    Falls back to structural heuristics if GPT-4o is unavailable."""

    clusters = {}
    for seg in segments:
        sp = seg.get("speaker", "CLUSTER_0")
        c = clusters.setdefault(sp, {"starts": [], "texts": [], "en_chars": 0, "ru_chars": 0})
        c["starts"].append(seg["start"])
        txt = seg.get("text", "")
        c["texts"].append(txt)
        for ch in txt:
            if '\u0400' <= ch <= '\u04FF':
                c["ru_chars"] += 1
            elif ch.isascii() and ch.isalpha():
                c["en_chars"] += 1

    cluster_ids = sorted(clusters.keys(), key=lambda k: min(clusters[k]["starts"]))

    # --- structural heuristic fallback (also used as defaults) ---
    heuristic = {}
    for i, cid in enumerate(cluster_ids):
        c = clusters[cid]
        lang = "en" if c["en_chars"] > c["ru_chars"] else "ru"
        if lang == "en":
            heuristic[cid] = "Other Speaker"
        elif i == 0:
            heuristic[cid] = "Naran"
        else:
            heuristic[cid] = "Kamran"

    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        print("  Cluster naming: no OPENAI_API_KEY, using structural heuristic")
        _save_naming(output_dir, clusters, heuristic, "heuristic-no-key")
        return heuristic

    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)

        cluster_desc = []
        for cid in cluster_ids:
            c = clusters[cid]
            first = min(c["starts"])
            last = max(c["starts"])
            lang = "mostly English" if c["en_chars"] > c["ru_chars"] else "mostly Russian"
            sample = " / ".join(t.strip() for t in c["texts"][:6])[:600]
            cluster_desc.append(
                f'- {cid}: first heard at {first:.1f}s, last heard at {last:.1f}s, '
                f'{lang}. Sample text: "{sample}"'
            )

        prompt = f"""You are labeling speakers in a Naran Hangai video about Armenian history. Acoustic analysis has grouped the audio into voice clusters. Your ONLY job is to give each cluster its canonical name.

KNOWN STRUCTURE OF THIS VIDEO:
1. NARAN (host) opens with an intro in Russian.
2. KAMRAN then speaks in the middle — presenting his nationalist/historical claims (e.g. Armenia is fabricated, not in the Bible).
3. NARAN returns to rebut Kamran's claims point by point.
4. An OTHER SPEAKER closes the video — this part is in ENGLISH.

NAMING RULES:
- A cluster heard at the very START and again AFTER the middle block is the same person = "Naran".
- The middle block presenting claims = "Kamran".
- Any cluster speaking English = "Other Speaker".
- Naran may QUOTE Kamran or historical sources while speaking — the acoustic cluster still belongs to whoever is physically talking. Do not create new names. Use ONLY: "Naran", "Kamran", "Other Speaker".

CLUSTERS:
{chr(10).join(cluster_desc)}

Return ONLY JSON: {{"mapping": {{"CLUSTER_0": "Naran", "CLUSTER_1": "Kamran", ...}}}}"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You map acoustic voice clusters to speaker names. Return only valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        result = json.loads(response.choices[0].message.content.strip())
        mapping = result.get("mapping", {})

        # Validate + fill gaps with heuristic
        final = {}
        for cid in cluster_ids:
            name = mapping.get(cid, heuristic[cid])
            if name not in ("Naran", "Kamran", "Other Speaker"):
                name = heuristic[cid]
            final[cid] = name

        print(f"  Cluster naming (GPT-4o): {final}")
        _save_naming(output_dir, clusters, final, "gpt4o")
        return final

    except Exception as e:
        print(f"  Cluster naming failed: {e}, using structural heuristic")
        _save_naming(output_dir, clusters, heuristic, "heuristic-error")
        return heuristic


def _save_naming(output_dir: str, clusters: dict, mapping: dict, method: str):
    try:
        info = {
            "method": method,
            "mapping": mapping,
            "clusters": {
                cid: {
                    "first_heard": min(c["starts"]),
                    "last_heard": max(c["starts"]),
                    "sample": " ".join(c["texts"])[:200]
                } for cid, c in clusters.items()
            }
        }
        with open(os.path.join(output_dir, "cluster_naming.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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
        "final": {
            "method": "Acoustic diarization + GPT-4o cluster naming",
            "speakers_found": sorted(list(gpt4o_speakers)),
            "segment_count": len(gpt4o_segments),
        },
        "pyannote_raw": {
            "method": "pyannote.audio (acoustic)",
            "speakers_found": sorted(list(diarization_speakers)),
            "segment_count": len(diarization_segments),
        },
        "pause_heuristic": {
            "method": "Pause-based heuristic",
            "speakers_found": sorted(list(pause_speakers)),
            "segment_count": len(pause_segments),
        },
    }

    return comparison
