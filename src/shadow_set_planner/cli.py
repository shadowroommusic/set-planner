from __future__ import annotations

import argparse
import json
from pathlib import Path

from .model import parse_tracks, to_json
from .recommend import suggest_next
from .timing import plan_from_payload


def dump(value: object, output: str | None) -> None:
    text = json.dumps(to_json(value), ensure_ascii=False, indent=2) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")


def load_json(path: str) -> object:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="shadow-set-planner",
        description="Time a DJ set from cue A/B data and suggest what to play next.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Lay out an ordered set: segment lengths, overlaps and total runtime.")
    plan.add_argument("--input", required=True, help="JSON file with a 'tracks' array and optional 'transitions'.")
    plan.add_argument("--overlap-ms", type=int, default=0, help="Default transition overlap in milliseconds.")
    plan.add_argument("--output", help="Write the JSON report to this file instead of stdout.")
    suggest = commands.add_parser("suggest", help="Rank the next tracks for a library.")
    suggest.add_argument("--library", required=True, help="JSON file with a 'tracks' array.")
    suggest.add_argument("--current", required=True, help="id of the track that is playing now.")
    suggest.add_argument("--limit", type=int, default=5, help="How many suggestions to return (default 5).")
    suggest.add_argument("--min-score", type=float, default=0.0, help="Drop suggestions below this score.")
    suggest.add_argument("--exclude", action="append", default=[], help="Track id to skip; repeat for more.")
    suggest.add_argument("--output", help="Write the JSON report to this file instead of stdout.")
    args = parser.parse_args()

    if args.command == "plan":
        dump(plan_from_payload(load_json(args.input), default_overlap_ms=args.overlap_ms), args.output)
        return 0

    tracks = parse_tracks(load_json(args.library))
    current = next((track for track in tracks if track.id == args.current), None)
    if current is None:
        raise SystemExit(f"no track with id {args.current!r} in {args.library}")
    dump(
        suggest_next(current, tracks, limit=args.limit, exclude_ids=tuple(args.exclude), min_score=args.min_score),
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
