"""Persistent speaker voice bank + user attribution corrections.

Two complementary mechanisms, both stored in the repo so every pipeline run
(and the dashboard) sees the same state:

1. speaker-bank/profiles.json — persistent VOICE PROFILES.
   Each named speaker (starting with Naran, the host) accumulates an
   averaged acoustic embedding (x-vector) built from cluster embeddings the
   user confirmed via the dashboard. On later runs, clusters whose embedding
   matches a profile are named from the bank FIRST — before GPT-4o naming —
   so Naran is always credited to Naran, on every video, without re-labeling.

2. processed/<video>/corrections.json — per-video ATTRIBUTION RULES.
   Time-range rules created in the dashboard ("0:00-2:34 is Naran").
   Applied as a hard override AFTER acoustic naming (and again after
   translation, in case the GPT text fallback relabeled segments), so saved
   corrections guide every future reprocessing of that video.

The bank only grows from user-confirmed attributions — never from automatic
naming — so a GPT mislabel can never poison a voice profile.
"""

import json
import math
import os
from datetime import datetime, timezone

BANK_PATH = os.path.join("speaker-bank", "profiles.json")

# Cosine similarity threshold for accepting a cluster -> profile match.
# pyannote/embedding x-vectors: same speaker across videos of one channel
typically scores 0.6-0.9; different speakers on clean speech score < 0.5.
MATCH_THRESHOLD = 0.55


# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------

def _norm(v):
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return -1.0
    return sum(x * y for x, y in zip(a, b))


def average_vectors(vectors):
    """Mean of embedding vectors, re-normalized."""
    if not vectors:
        return []
    dims = len(vectors[0])
    acc = [0.0] * dims
    n = 0
    for v in vectors:
        if len(v) != dims:
            continue
        for i, x in enumerate(v):
            acc[i] += x
        n += 1
    if n == 0:
        return []
    return _norm([x / n for x in acc])


# ---------------------------------------------------------------------------
# Voice bank
# ---------------------------------------------------------------------------

def load_bank(path=BANK_PATH):
    """Returns {"profiles": {name: {embedding, samples, videos, updated_at}}}."""
    if not os.path.exists(path):
        return {"profiles": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if "profiles" not in data or not isinstance(data["profiles"], dict):
            return {"profiles": {}}
        return data
    except Exception as e:
        print(f"  Speaker bank: could not read {path}: {e}")
        return {"profiles": {}}


def save_bank(bank, path=BANK_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=2)


def merge_into_profile(bank, name, vectors, video_id=None):
    """Merge embedding vectors into a speaker's profile (running average).
    vectors: list of embedding lists from user-confirmed clusters."""
    if not vectors:
        return False
    profiles = bank.setdefault("profiles", {})
    prof = profiles.get(name)
    if prof and prof.get("embedding"):
        merged = average_vectors([prof["embedding"]] * max(prof.get("samples", 1), 1) + list(vectors))
        samples = prof.get("samples", 1) + len(vectors)
        videos = sorted(set(prof.get("videos", []) + ([video_id] if video_id else [])))
    else:
        merged = average_vectors(list(vectors))
        samples = len(vectors)
        videos = [video_id] if video_id else []
    if not merged:
        return False
    profiles[name] = {
        "embedding": [round(x, 6) for x in merged],
        "samples": samples,
        "videos": videos,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return True


def match_clusters(cluster_embeddings, bank, threshold=MATCH_THRESHOLD):
    """Match diarization clusters to bank profiles by cosine similarity.
    cluster_embeddings: {cluster_id: [floats]} (from diarize.compute_cluster_embeddings)
    Returns {cluster_id: (profile_name, score)} for matches >= threshold.
    Each profile matches at most one cluster (best score wins ties)."""
    profiles = (bank or {}).get("profiles", {})
    if not cluster_embeddings or not profiles:
        return {}

    # score every (cluster, profile) pair, then assign greedily best-first
    pairs = []
    for cid, emb in cluster_embeddings.items():
        for name, prof in profiles.items():
            score = _cosine(_norm(emb), prof.get("embedding", []))
            if score >= threshold:
                pairs.append((score, cid, name))
    pairs.sort(reverse=True)

    matches = {}
    used_profiles = set()
    for score, cid, name in pairs:
        if cid in matches or name in used_profiles:
            continue
        matches[cid] = (name, round(score, 3))
        used_profiles.add(name)
    return matches


# ---------------------------------------------------------------------------
# Per-video attribution rules (user corrections)
# ---------------------------------------------------------------------------

def corrections_path(video_id, processed_dir="processed"):
    return os.path.join(processed_dir, video_id, "corrections.json")


def load_corrections(video_id, processed_dir="processed"):
    """Returns the rule list for a video, or [] if none/invalid.
    Rule: {"id", "start", "end", "speaker", "note", "created_at", "updated_at"}"""
    path = corrections_path(video_id, processed_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        rules = data.get("rules", [])
        return [r for r in rules
                if isinstance(r, dict) and "start" in r and "end" in r and "speaker" in r]
    except Exception as e:
        print(f"  Corrections: could not read {path}: {e}")
        return []


def apply_corrections(segments, rules):
    """Hard-override segment speakers from time-range rules.

    A segment inherits a rule's speaker when its MIDPOINT falls inside the
    rule's [start, end] range. Rules apply in list order — later rules win
    where ranges overlap. Returns (segments, relabeled_count)."""
    if not segments or not rules:
        return segments, 0
    ordered = sorted(rules, key=lambda r: (r.get("start", 0), r.get("end", 0)))
    relabeled = 0
    for seg in segments:
        mid = (seg.get("start", 0) + seg.get("end", 0)) / 2.0
        winner = None
        for r in ordered:
            if r.get("start", 0) - 1e-6 <= mid <= r.get("end", 0) + 1e-6:
                winner = r  # keep scanning: later rule overrides
        if winner and seg.get("speaker") != winner["speaker"]:
            seg["speaker"] = winner["speaker"]
            relabeled += 1
    return segments, relabeled
