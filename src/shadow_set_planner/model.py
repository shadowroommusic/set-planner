from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

CUE_ALIASES = {
    "a": "A",
    "cue a": "A",
    "in": "A",
    "intro": "A",
    "start": "A",
    "b": "B",
    "cue b": "B",
    "out": "B",
    "outro": "B",
    "end": "B",
}


@dataclass(frozen=True)
class CuePoint:
    name: str
    position_ms: int
    end_ms: int | None = None
    kind: str = "cue"

    @property
    def label(self) -> str:
        return CUE_ALIASES.get(self.name.strip().casefold(), self.name.strip().upper())


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artist: str = ""
    bpm: float | None = None
    key: str | None = None
    genres: tuple[str, ...] = field(default_factory=tuple)
    energy: float | None = None
    duration_ms: int | None = None
    cues: tuple[CuePoint, ...] = field(default_factory=tuple)

    @property
    def cue_a(self) -> CuePoint | None:
        for cue in self.cues:
            if cue.label == "A":
                return cue
        return None

    @property
    def cue_b(self) -> CuePoint | None:
        for cue in self.cues:
            if cue.label == "B":
                return cue
        return None

    def describe(self) -> str:
        return f"{self.artist} - {self.title}" if self.artist else self.title


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    number = _optional_float(value)
    return None if number is None else int(round(number))


def parse_cue(raw: Any) -> CuePoint:
    if not isinstance(raw, dict):
        raise ValueError(f"cue must be an object, got {type(raw).__name__}")
    name = str(raw.get("name") or raw.get("label") or raw.get("kind") or "").strip()
    position = raw.get("position_ms", raw.get("position", raw.get("start_ms", raw.get("start"))))
    position_ms = _optional_int(position)
    if position_ms is None:
        raise ValueError(f"cue {name!r} needs a position_ms value")
    end_ms = _optional_int(raw.get("end_ms", raw.get("end")))
    kind = str(raw.get("kind") or "cue").strip().lower()
    if end_ms is not None and kind == "cue":
        kind = "loop"
    return CuePoint(name=name or "CUE", position_ms=position_ms, end_ms=end_ms, kind=kind)


def parse_track(raw: Any, index: int = 0) -> Track:
    if not isinstance(raw, dict):
        raise ValueError(f"track must be an object, got {type(raw).__name__}")
    title = str(raw.get("title") or raw.get("name") or "").strip()
    artist = str(raw.get("artist") or "").strip()
    identifier = raw.get("id") or raw.get("path") or (f"{artist} - {title}".strip(" -") or f"track-{index + 1}")
    genres_raw = raw.get("genres", raw.get("genre"))
    if genres_raw is None:
        genres: "list[str]" = []
    elif isinstance(genres_raw, str):
        genres = [item.strip() for item in genres_raw.split(",") if item.strip()] or ([genres_raw.strip()] if genres_raw.strip() else [])
    else:
        genres = [str(item).strip() for item in genres_raw if str(item).strip()]
    cues_raw = raw.get("cues") or raw.get("cue_points") or []
    cues = tuple(parse_cue(item) for item in cues_raw)
    return Track(
        id=str(identifier),
        title=title or str(identifier),
        artist=artist,
        bpm=_optional_float(raw.get("bpm")),
        key=(str(raw["key"]).strip() if raw.get("key") not in (None, "") else None),
        genres=tuple(genres),
        energy=_optional_float(raw.get("energy")),
        duration_ms=_optional_int(raw.get("duration_ms", raw.get("length_ms"))),
        cues=cues,
    )


def parse_tracks(payload: Any) -> "list[Track]":
    """Accept either a bare list of tracks or an object with a `tracks` array."""
    if isinstance(payload, dict):
        raw_tracks = payload.get("tracks")
        if raw_tracks is None:
            raise ValueError("input object needs a 'tracks' array")
    elif isinstance(payload, list):
        raw_tracks = payload
    else:
        raise ValueError(f"expected a track list or object, got {type(payload).__name__}")
    if not isinstance(raw_tracks, list):
        raise ValueError("'tracks' must be an array")
    tracks = [parse_track(item, index) for index, item in enumerate(raw_tracks)]
    seen: "set[str]" = set()
    for track in tracks:
        if track.id in seen:
            raise ValueError(f"duplicate track id: {track.id!r}")
        seen.add(track.id)
    return tracks


def to_json(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_json(item) for key, item in asdict(value).items()}
    if isinstance(value, (tuple, list)):
        return [to_json(item) for item in value]
    if isinstance(value, dict):
        return {key: to_json(item) for key, item in value.items()}
    if isinstance(value, float):
        return round(value, 3)
    return value
