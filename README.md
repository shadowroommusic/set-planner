# Set Planner

An MCP server for the maths a DJ normally does in their head: **how long will this set run**, and
**what should I play next**?

[中文说明](README.zh-CN.md) · License: [AGPL-3.0](LICENSE)

## Features

- **Set timing.** Turns cue A/B points into per-track segments, transition overlaps, phrasing
  warnings and one total runtime.
- **Next-track suggestions.** Ranks candidates by bpm (half/double time included), key
  compatibility, genre overlap and energy change — and explains every score.
- **Nothing is opened.** It works purely on the track JSON you give it; no audio files, no
  Rekordbox/Serato databases.
- **Explainable.** Each suggestion comes with reasons, a score breakdown and cautions; each plan
  comes with explicit warnings instead of silent guesses.

## Requirements

| | |
| --- | --- |
| OS | macOS, Linux or Windows |
| Python | 3.9 or newer |
| Runtime deps | none |

## Install

### As a Codex plugin

```sh
codex plugin marketplace add shadowroommusic/set-planner
codex plugin add set-planner@shadowroom
```

### In any other MCP client

```json
{
  "mcpServers": {
    "set-planner": {
      "command": "python3",
      "args": ["mcp_server.py"],
      "cwd": "/path/to/set-planner"
    }
  }
}
```

### CLI only

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/shadow-set-planner --help
```

## Input format

```json
{
  "tracks": [
    {
      "id": "track-1",
      "title": "Warehouse Tool",
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

`cues` accepts `A`/`B`, `intro`/`outro`, `in`/`out`, `start`/`end` and loop cues with `end_ms`;
`key` accepts Camelot (`8A`) or musical notation (`A minor`, `Am`, `G#m`, `Db`); `genres` accepts a
list or a comma-separated string; `transitions` is optional.

## Tools

| Tool | What it does |
| --- | --- |
| `plan_set` | Time an ordered set (`{"set": {...}, "default_overlap_ms": 16000}` or `{"input_path": "…"}`) |
| `suggest_next` | Rank what to play next (`{"current": {...}, "pool": [...]}` or `{"library_path": "…", "current_id": "…"}`) |

CLI equivalents: `shadow-set-planner plan` and `shadow-set-planner suggest`.

## Usage

```sh
# time an ordered set (16 second blends here)
.venv/bin/shadow-set-planner plan --input set.json --overlap-ms 16000 --output plan.json

# what should follow the track that is playing now?
.venv/bin/shadow-set-planner suggest --library library.json --current track-1 --limit 5
```

`plan` reports a `timeline` (segments, play positions, cue points, overlaps), `transitions`,
a `summary` (total runtime, segment sum, time saved by blending) and `warnings`. `suggest` reports
ranked candidates with `reasons`, `breakdown` and `cautions`.

## Safety

- Read-only and offline: no audio files or vendor databases are touched.
- All input comes from the JSON you provide; plans and suggestions are just files (or stdout).

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| “missing A/B cues” warnings | Add `cues` for the track, or plan without it (it falls back to full length). |
| Suggestions look flat | Give tracks `energy`/`genres` metadata; unknown metadata is scored neutrally by design. |
| Tempo jumps flagged | That warning means Beat Sync or pitch adjustment is needed at the transition. |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Implementation notes live in
[docs/internals.md](docs/internals.md).

## License

AGPL-3.0 — see [LICENSE](LICENSE).
