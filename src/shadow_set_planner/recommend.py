from __future__ import annotations

import math
import re
import unicodedata

from .keys import key_move
from .model import Track, to_json

BPM_WEIGHT = 0.35
KEY_WEIGHT = 0.25
GENRE_WEIGHT = 0.2
ENERGY_WEIGHT = 0.2


def _tokens(values: "tuple[str, ...]") -> "set[str]":
    tokens: "set[str]" = set()
    for value in values:
        normalized = unicodedata.normalize("NFKC", str(value)).casefold()
        for token in re.split(r"[^0-9a-z\u4e00-\u9fff]+", normalized):
            if token:
                tokens.add(token)
    return tokens


def bpm_match(current_bpm: "float | None", candidate_bpm: "float | None") -> "tuple[float, str, bool, str | None]":
    if not current_bpm or not candidate_bpm:
        return 0.4, "bpm unknown; verify by ear", False, "tag the bpm to get a reliable tempo score"
    ratio = candidate_bpm / current_bpm
    distance, factor = min((abs(math.log2(ratio / candidate)), candidate) for candidate in (1.0, 2.0, 0.5))
    percent = (2 ** distance - 1) * 100
    score = 1.0 if percent <= 0.8 else max(0.0, 1 - (percent - 0.8) / 7.2)
    label = {1.0: "tempo match", 2.0: "double-time match", 0.5: "half-time match"}[factor]
    caution = None
    if factor == 1.0 and percent > 3:
        caution = f"{percent:.1f}% tempo change; use pitch or tempo sync"
    reason = f"{label}: {current_bpm:g} → {candidate_bpm:g} bpm ({percent:.1f}% apart)"
    return round(score, 3), reason, True, caution


def genre_match(current_genres: "tuple[str, ...]", candidate_genres: "tuple[str, ...]") -> "tuple[float, str, bool, str | None]":
    left, right = _tokens(current_genres), _tokens(candidate_genres)
    if not left or not right:
        return 0.5, "genres unknown; judge this one by ear", False, None
    shared = left & right
    union = left | right
    score = len(shared) / len(union) if union else 0.0
    if shared:
        reason = "shared genres: " + ", ".join(sorted(shared))
    else:
        reason = "no shared genre tag"
    caution = None if shared else "genre tags do not overlap; check the vibe manually"
    return round(score, 3), reason, True, caution


def energy_match(current_energy: "float | None", candidate_energy: "float | None") -> "tuple[float, str, bool, str | None]":
    if current_energy is None or candidate_energy is None:
        return 0.5, "energy unknown; judge this one by ear", False, None
    delta = candidate_energy - current_energy
    rounded = int(round(delta))
    score = {0: 1.0, 1: 1.0, -1: 0.85, 2: 0.7, -2: 0.6}.get(rounded, max(0.2, 0.55 - abs(delta) * 0.1))
    if rounded == 0:
        label = "steady energy"
    elif rounded > 0:
        label = f"energy lift +{delta:g}"
    else:
        label = f"energy drop {delta:g}"
    caution = "large energy change; make sure it fits the arc" if abs(delta) >= 3 else None
    return round(score, 3), f"{label} ({current_energy:g} → {candidate_energy:g})", True, caution


def score_candidate(current: Track, candidate: Track) -> dict:
    components = [
        ("bpm", BPM_WEIGHT, bpm_match(current.bpm, candidate.bpm)),
        ("key", KEY_WEIGHT, _key_component(current, candidate)),
        ("genre", GENRE_WEIGHT, genre_match(current.genres, candidate.genres)),
        ("energy", ENERGY_WEIGHT, energy_match(current.energy, candidate.energy)),
    ]
    total_weight = 0.0
    weighted = 0.0
    breakdown: "dict[str, float]" = {}
    reasons: "list[str]" = []
    cautions: "list[str]" = []
    for name, weight, (score, reason, known, caution) in components:
        weighted += score * weight
        total_weight += weight
        breakdown[name] = score
        reasons.append(reason)
        if caution:
            cautions.append(caution)
    score = weighted / total_weight if total_weight else 0.0
    return {
        "id": candidate.id,
        "title": candidate.title,
        "artist": candidate.artist,
        "bpm": candidate.bpm,
        "key": candidate.key,
        "genres": list(candidate.genres),
        "energy": candidate.energy,
        "score": round(score, 3),
        "breakdown": breakdown,
        "reasons": reasons,
        "cautions": cautions,
    }


def _key_component(current: Track, candidate: Track) -> "tuple[float, str, bool, str | None]":
    move = key_move(current.key, candidate.key)
    caution = None
    if move["relation"] == "distant":
        caution = "harmonically distant; mix through a break or use a key shift"
    elif move["relation"] == "energy-boost":
        caution = "+7 semitone energy boost; it works but changes the mood"
    known = move["relation"] != "unknown"
    return move["score"], move["reason"], known, caution


def suggest_next(
    current: Track,
    pool: "list[Track]",
    limit: int = 5,
    exclude_ids: "tuple[str, ...]" = (),
    min_score: float = 0.0,
) -> dict:
    """Rank candidate tracks for the next slot with an explicit reason for each score."""
    excluded = set(exclude_ids) | {current.id}
    scored = [score_candidate(current, candidate) for candidate in pool if candidate.id not in excluded]
    scored = [item for item in scored if item["score"] >= min_score]
    scored.sort(key=lambda item: (-item["score"], item["id"]))
    return {
        "schema_version": 1,
        "mode": "read-only-recommendation",
        "current": {
            "id": current.id,
            "title": current.title,
            "bpm": current.bpm,
            "key": current.key,
            "genres": list(current.genres),
            "energy": current.energy,
        },
        "candidate_count": len(scored),
        "suggestions": scored[:limit],
        "weights": {"bpm": BPM_WEIGHT, "key": KEY_WEIGHT, "genre": GENRE_WEIGHT, "energy": ENERGY_WEIGHT},
        "notes": [
            "Scores blend bpm (half and double time count), Camelot distance, genre overlap and energy change.",
            "Every suggestion lists its reasons so you can disagree with the maths.",
        ],
    }


def suggest_from_payload(payload: dict, limit: int = 5, min_score: float = 0.0) -> dict:
    from .model import parse_tracks

    if not isinstance(payload, dict):
        raise ValueError("the payload must be an object")
    current_raw = payload.get("current")
    pool_raw = payload.get("pool")
    if current_raw is None or pool_raw is None:
        raise ValueError("the payload needs 'current' and 'pool'")
    current = parse_tracks([current_raw])[0]
    pool = parse_tracks(pool_raw)
    exclude_ids = tuple(str(item) for item in (payload.get("exclude_ids") or []))
    return to_json(suggest_next(current, pool, limit=limit, exclude_ids=exclude_ids, min_score=min_score))
