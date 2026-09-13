# Set Planner

This independent Shadow Producers plugin does the maths a DJ normally does in their head:

1. **Time the set** — turn cue A/B data into per-track segment durations, transition overlaps, phrasing warnings and one total runtime.
2. **Pick the next track** — rank candidates by bpm (half and double time included), Camelot distance, genre overlap and energy change, and explain every score.

It never opens an audio file or a vendor database. It works purely on the track JSON you give it, so it is safe to run against an exported library.

## JSON input

```json
{
  "tracks": [
    {
      "id": "track-1",
      "title": "Warehouse Tool",
      "artist": "Someone",
      "bpm": 128,
      "key": "8A",
      "genres": ["techno", "melodic techno"],
      "energy": 6,
      "duration_ms": 360000,
      "cues": [
        { "name": "A", "position_ms": 15000 },
        { "name": "B", "position_ms": 210000 }
      ]
    }
  ],
  "transitions": [
    { "from": "track-1", "to": "track-2", "overlap_ms": 16000 }
  ]
}
```

- `cues` accepts `A`/`B` as well as `intro`/`outro`, `in`/`out`, `start`/`end`, and a `loop` cue with `end_ms`.
- `key` accepts Camelot (`8A`) or musical notation (`A minor`, `Am`, `C`, `G#m`, `Db`).
- `genres` accepts a list or a comma-separated string.
- `transitions` is optional; `--overlap-ms` sets the default for every transition.

## Commands

```sh
python3 -m venv .venv
.venv/bin/pip install -e .

# Time an ordered set (16 second blends by default in this example)
.venv/bin/shadow-set-planner plan --input set.json --overlap-ms 16000 --output plan.json

# What should follow the track that is playing now?
.venv/bin/shadow-set-planner suggest --library library.json --current track-1 --limit 5
```

## What the plan reports

- `timeline`: per track the segment (`start_ms`, `end_ms`, `duration_ms`, `bars`), where it plays in the set (`play_start`, `play_end`), its cue in/out points and the overlaps in and out.
- `transitions`: overlap used, bpm change in percent, Camelot move and any warning.
- `summary`: `total_duration` (h:mm) plus `sum_of_segments_ms` and `overlap_saved_ms`, so you can see exactly how much time the blends saved.
- `warnings`: missing A/B cues, cue B before cue A, cue B past the track end, overlaps longer than the shorter segment, tempo jumps that need a pitch/tempo sync, harmonically distant moves and segments that are off the bar grid.

## How the recommendation score works

| Component | Weight | Notes |
| --- | --- | --- |
| bpm | 0.35 | Full score within 0.8%. Half-time and double-time ratios count as a match. |
| key | 0.25 | Same key 1.0, adjacent on the Camelot wheel 0.85, relative major/minor 0.7, +7 energy boost 0.6, distant 0.2. |
| genre | 0.20 | Jaccard overlap of normalized genre tokens. |
| energy | 0.20 | Steady or +1 is perfect, small steps slightly less, large jumps are penalised. |

Every suggestion carries `reasons` (why it scored that way), `breakdown` (the four component scores) and `cautions` (what to watch out for). Unknown metadata never blocks a suggestion; it is reported and scored neutrally.

## MCP

`.mcp.json` exposes two read-only tools:

- `plan_set` — `{"set": {...}, "default_overlap_ms": 16000}` or `{"input_path": "/path/set.json"}`.
- `suggest_next` — `{"current": {...}, "pool": [...]}` or `{"library_path": "/path/library.json", "current_id": "track-1"}`.

## Tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## License

MIT for this plugin, with no runtime dependency.
