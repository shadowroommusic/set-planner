# Internals

Maintainer notes for `set-planner`. The user-facing docs live in [../README.md](../README.md).

## Recommendation score

`suggest_next` ranks candidates with four weighted components:

| Component | Weight | Rule |
| --- | --- | --- |
| bpm | 0.35 | Full score within 0.8%; half-time and double-time ratios count as a match. |
| key | 0.25 | Same key 1.0, adjacent on the Camelot wheel 0.85, relative major/minor 0.7, +7 energy boost 0.6, distant 0.2. |
| genre | 0.20 | Jaccard overlap of normalised genre tokens. |
| energy | 0.20 | Steady or +1 is perfect, small steps slightly less, large jumps are penalised. |

Every suggestion carries `reasons`, a four-component `breakdown` and `cautions`. Unknown metadata
scores neutrally instead of blocking a suggestion.

## Input normalisation

- `cues` accepts `A`/`B`, `intro`/`outro`, `in`/`out`, `start`/`end`, and loop cues with `end_ms`.
- `key` accepts Camelot (`8A`) or musical notation (`A minor`, `Am`, `C`, `G#m`, `Db`).
- `genres` accepts a list or a comma-separated string.
- `transitions` is optional; `--overlap-ms` provides the default overlap.

## Plan output

- `timeline`: per track `start_ms`, `end_ms`, `duration_ms`, `bars`, `play_start`, `play_end`, cue
  in/out points and the in/out overlaps.
- `transitions`: overlap, bpm change (%), Camelot move, warnings.
- `summary`: `total_duration`, `sum_of_segments_ms`, `overlap_saved_ms`.
- `warnings`: missing A/B cues, cue B before cue A, cue B past the end, overlap longer than the
  shorter segment, tempo jumps needing sync, harmonically distant moves, off-grid segments.

## Tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
