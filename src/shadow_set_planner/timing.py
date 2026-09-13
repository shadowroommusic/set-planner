from __future__ import annotations

from .keys import key_move
from .model import Track, to_json


def format_duration(milliseconds: int) -> str:
    total_seconds = max(0, round(milliseconds / 1000))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def segment_for(track: Track) -> dict:
    """Turn cue A/B into a playable segment, reporting every assumption."""
    warnings: "list[str]" = []
    duration = track.duration_ms
    cue_a, cue_b = track.cue_a, track.cue_b
    start: int | None
    end: int | None

    if cue_a is None:
        start = 0
        warnings.append("no A cue; the segment starts at the beginning of the file")
    else:
        start = cue_a.position_ms

    source = "full track"
    if cue_a is not None and cue_a.kind == "loop" and cue_a.end_ms is not None and cue_b is None:
        end = cue_a.end_ms
        source = "loop A"
    elif cue_b is not None:
        end = cue_b.position_ms
        source = "cue A to cue B" if cue_a is not None else "file start to cue B"
    elif duration is not None:
        end = duration
        if cue_a is not None:
            source = "cue A to track end"
            warnings.append("no B cue; the segment runs to the end of the track")
        else:
            source = "full track"
    else:
        end = None
        warnings.append("no B cue and no duration; this track cannot be timed")

    if duration is not None:
        if start is not None and start > duration:
            warnings.append(f"cue A at {start} ms is past the track end ({duration} ms); using the track start")
            start = 0
        if end is not None and end > duration:
            warnings.append(f"cue B at {end} ms is past the track end ({duration} ms); clamping to {duration} ms")
            end = duration
    if start is not None and start < 0:
        warnings.append(f"cue A at {start} ms is negative; using 0 ms")
        start = 0
    if end is not None and start is not None and end <= start:
        warnings.append(f"cue B ({end} ms) is not after cue A ({start} ms); falling back to the whole track")
        start, end = 0, duration
        source = "full track"

    length = None if end is None or start is None else end - start
    bars = None
    bar_length_ms = None
    if track.bpm:
        bar_length_ms = round(60_000 / track.bpm * 4, 3)
        if length:
            bars = round(length / bar_length_ms, 2)
            deviation = abs(bars - round(bars))
            # Only a deliberate A→B or loop segment can be off the phrasing grid; a
            # fallback to the track end is not a mixing decision the DJ made.
            if source in {"cue A to cue B", "loop A"} and 0.25 < deviation < 0.75:
                warnings.append(f"segment is {bars} bars ({track.bpm} bpm); trimming it to a whole bar keeps phrasing clean")

    return {
        "start_ms": start,
        "end_ms": end,
        "duration_ms": length,
        "bars": bars,
        "bar_length_ms": bar_length_ms,
        "source": source,
        "warnings": warnings,
    }


def _transition_overlap(
    transitions: "dict[tuple[str, str], int]",
    left: Track,
    right: Track,
    default_overlap_ms: int,
    left_segment: dict,
    right_segment: dict,
) -> "tuple[int, list[str]]":
    warnings: "list[str]" = []
    overlap = transitions.get((left.id, right.id), default_overlap_ms)
    if overlap < 0:
        warnings.append(f"negative overlap {overlap} ms was clamped to 0")
        overlap = 0
    limits = [value for value in (left_segment.get("duration_ms"), right_segment.get("duration_ms")) if value]
    if limits and overlap >= min(limits):
        capped = max(0, min(limits) - 1)
        warnings.append(f"overlap {overlap} ms is longer than the shorter segment; clamped to {capped} ms")
        overlap = capped
    return overlap, warnings


def plan_set(
    tracks: "list[Track]",
    transitions: "list[dict] | None" = None,
    default_overlap_ms: int = 0,
) -> dict:
    """Lay out an ordered set: segment length, transitions and total runtime."""
    if default_overlap_ms < 0:
        raise ValueError("default_overlap_ms must not be negative")
    if not tracks:
        raise ValueError("the set needs at least one track")
    overrides: "dict[tuple[str, str], int]" = {}
    for raw in transitions or []:
        if not isinstance(raw, dict):
            raise ValueError("each transition must be an object")
        source, target = raw.get("from"), raw.get("to")
        overlap = raw.get("overlap_ms", raw.get("overlap"))
        if source is None or target is None or overlap is None:
            raise ValueError("a transition needs 'from', 'to' and 'overlap_ms'")
        overrides[(str(source), str(target))] = int(overlap)

    segments = [segment_for(track) for track in tracks]
    overlaps: "list[int]" = [0]
    transitions_report: "list[dict]" = []
    for index in range(len(tracks) - 1):
        left, right = tracks[index], tracks[index + 1]
        overlap, warnings = _transition_overlap(overrides, left, right, default_overlap_ms, segments[index], segments[index + 1])
        bpm_move = None
        if left.bpm and right.bpm:
            change = (right.bpm / left.bpm - 1) * 100
            bpm_move = round(change, 2)
            if abs(change) > 3 and not (0.47 <= right.bpm / left.bpm <= 0.53 or 1.9 <= right.bpm / left.bpm <= 2.1):
                warnings.append(
                    f"tempo changes {left.bpm} → {right.bpm} bpm ({change:+.1f}%); plan a pitch or tempo-sync transition"
                )
        harmony = key_move(left.key, right.key)
        if harmony["relation"] == "distant":
            warnings.append(f"{harmony['reason']}; mix through a break or shift the pitch")
        overlaps.append(overlap)
        transitions_report.append(
            {
                "index": index,
                "from": left.id,
                "from_title": left.describe(),
                "to": right.id,
                "to_title": right.describe(),
                "overlap_ms": overlap,
                "bpm_change_percent": bpm_move,
                "key_move": harmony,
                "warnings": warnings,
            }
        )

    timeline: "list[dict]" = []
    cursor = 0
    for index, track in enumerate(tracks):
        segment = segments[index]
        length = segment["duration_ms"] or 0
        overlap_in = overlaps[index]
        play_start = cursor
        play_end = play_start + length
        timeline.append(
            {
                "index": index,
                "id": track.id,
                "title": track.title,
                "artist": track.artist,
                "bpm": track.bpm,
                "key": track.key,
                "genres": list(track.genres),
                "energy": track.energy,
                "segment": {key: value for key, value in segment.items() if key != "warnings"},
                "play_start_ms": play_start,
                "play_end_ms": play_end,
                "play_start": format_duration(play_start),
                "play_end": format_duration(play_end),
                "cue_in_ms": segment["start_ms"],
                "cue_out_ms": segment["end_ms"],
                "overlap_in_ms": overlap_in,
                "overlap_out_ms": overlaps[index + 1] if index + 1 < len(overlaps) else 0,
                "warnings": segment["warnings"],
            }
        )
        cursor = play_end - (overlaps[index + 1] if index + 1 < len(overlaps) else 0)

    total_duration = timeline[-1]["play_end_ms"] if timeline else 0
    sum_of_segments = sum(segment["duration_ms"] or 0 for segment in segments)
    warning_list: "list[str]" = []
    for entry in timeline:
        warning_list.extend(f"track {entry['index'] + 1} ({entry['title']}): {text}" for text in entry["warnings"])
    for transition in transitions_report:
        warning_list.extend(f"transition {transition['index'] + 1} → {transition['index'] + 2}: {text}" for text in transition["warnings"])

    return {
        "schema_version": 1,
        "mode": "read-only-plan",
        "track_count": len(tracks),
        "default_overlap_ms": default_overlap_ms,
        "timeline": timeline,
        "transitions": transitions_report,
        "summary": {
            "total_duration_ms": total_duration,
            "total_duration": format_duration(total_duration),
            "sum_of_segments_ms": sum_of_segments,
            "overlap_saved_ms": sum_of_segments - total_duration,
            "tracks_with_full_cues": sum(1 for track in tracks if track.cue_a and track.cue_b),
            "tracks_missing_cues": sum(1 for track in tracks if not track.cue_a or not track.cue_b),
            "warning_count": len(warning_list),
        },
        "warnings": warning_list,
        "notes": [
            "No audio file or vendor database was read or written; the plan is pure arithmetic on the cue data you supplied.",
            "Segment length is cue A to cue B when both exist; otherwise the plugin says so in the per-track warnings.",
        ],
    }


def plan_from_payload(payload: dict, default_overlap_ms: int = 0) -> dict:
    from .model import parse_tracks

    if not isinstance(payload, dict):
        raise ValueError("the set payload must be an object")
    tracks = parse_tracks(payload)
    result = plan_set(tracks, payload.get("transitions"), default_overlap_ms=default_overlap_ms)
    return to_json(result)
