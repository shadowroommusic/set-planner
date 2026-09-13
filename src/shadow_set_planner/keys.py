from __future__ import annotations

import re
import unicodedata

# Camelot wheel: number + A (minor) / B (major).
CAMELOT_TO_MUSICAL = {
    "1A": ("Ab", "minor"),
    "1B": ("B", "major"),
    "2A": ("Eb", "minor"),
    "2B": ("F#", "major"),
    "3A": ("Bb", "minor"),
    "3B": ("Db", "major"),
    "4A": ("F", "minor"),
    "4B": ("Ab", "major"),
    "5A": ("C", "minor"),
    "5B": ("Eb", "major"),
    "6A": ("G", "minor"),
    "6B": ("Bb", "major"),
    "7A": ("D", "minor"),
    "7B": ("F", "major"),
    "8A": ("A", "minor"),
    "8B": ("C", "major"),
    "9A": ("E", "minor"),
    "9B": ("G", "major"),
    "10A": ("B", "minor"),
    "10B": ("D", "major"),
    "11A": ("F#", "minor"),
    "11B": ("A", "major"),
    "12A": ("C#", "minor"),
    "12B": ("E", "major"),
}

ENHARMONIC = {
    "cb": "B",
    "b#": "C",
    "e#": "F",
    "fb": "E",
    "g#": "Ab",
    "d#": "Eb",
    "a#": "Bb",
    "db": "C#",
    "gb": "F#",
    "ab": "Ab",
}

MUSICAL_TO_CAMELOT = {}
for _camelot, (_note, _mode) in CAMELOT_TO_MUSICAL.items():
    MUSICAL_TO_CAMELOT.setdefault((_note, _mode), _camelot)
    MUSICAL_TO_CAMELOT.setdefault((ENHARMONIC.get(_note.casefold(), _note), _mode), _camelot)

CAMELOT_RE = re.compile(r"^(1[0-2]|[1-9])\s*([ab])$")
MUSICAL_RE = re.compile(r"^([a-g](?:#|b)?)\s*(min|minor|m|maj|major|)$")


def parse_key(value: "str | None") -> "str | None":
    """Return Camelot notation (e.g. '8A') for Camelot or musical key input."""
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    if not text:
        return None
    text = text.replace("♯", "#").replace("♭", "b").replace("sharp", "#").replace("flat", "b")
    compact = text.replace(" ", "").replace("-", "").replace("_", "")
    camelot = CAMELOT_RE.match(compact)
    if camelot:
        return f"{int(camelot.group(1))}{camelot.group(2).upper()}"
    musical = MUSICAL_RE.match(compact)
    if not musical:
        return None
    note, quality = musical.group(1), musical.group(2)
    note = f"{note[0].upper()}{note[1:]}"
    note = ENHARMONIC.get(note.casefold(), note)
    mode = "minor" if quality in {"m", "min", "minor"} else "major"
    return MUSICAL_TO_CAMELOT.get((note, mode))


def key_move(source: "str | None", target: "str | None") -> dict:
    """Describe how compatible two keys are on the Camelot wheel."""
    left, right = parse_key(source), parse_key(target)
    if left is None or right is None:
        missing = "source" if left is None else "target"
        return {
            "relation": "unknown",
            "score": 0.4,
            "steps": None,
            "from": source,
            "to": target,
            "reason": f"key unknown ({missing}); beatmatch by ear or tag it first",
        }
    left_number, left_letter = int(left[:-1]), left[-1]
    right_number, right_letter = int(right[:-1]), right[-1]
    steps = (right_number - left_number) % 12
    same_letter = left_letter == right_letter
    if left == right:
        relation, score = "same", 1.0
    elif same_letter and steps in (1, 11):
        relation, score = "adjacent", 0.85
    elif same_letter and steps == 7:
        relation, score = "energy-boost", 0.6
    elif not same_letter and steps == 0:
        relation, score = "relative", 0.7
    elif same_letter and steps == 2:
        relation, score = "two-step", 0.55
    else:
        relation, score = "distant", 0.2
    return {
        "relation": relation,
        "score": score,
        "steps": steps,
        "from": left,
        "to": right,
        "reason": f"camelot {left} → {right} ({relation.replace('-', ' ')})",
    }


def key_musical_name(camelot: "str | None") -> "str | None":
    if camelot is None:
        return None
    entry = CAMELOT_TO_MUSICAL.get(camelot.upper())
    if entry is None:
        return None
    note, mode = entry
    return f"{note} {mode}"
