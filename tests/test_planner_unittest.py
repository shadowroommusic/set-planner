from __future__ import annotations

import json
import unittest

from shadow_set_planner.keys import key_move, parse_key
from shadow_set_planner.model import Track, parse_tracks
from shadow_set_planner.recommend import bpm_match, energy_match, genre_match, suggest_from_payload, suggest_next
from shadow_set_planner.timing import format_duration, plan_from_payload, plan_set, segment_for
from shadow_set_planner import mcp_server


def make_track(
    identifier: str,
    bpm: float | None = None,
    key: str | None = None,
    genres: "tuple[str, ...]" = (),
    energy: float | None = None,
    duration: int | None = None,
    a: int | None = None,
    b: int | None = None,
) -> Track:
    cues = []
    if a is not None:
        cues.append({"name": "A", "position_ms": a})
    if b is not None:
        cues.append({"name": "B", "position_ms": b})
    return parse_tracks(
        [
            {
                "id": identifier,
                "title": identifier,
                "bpm": bpm,
                "key": key,
                "genres": list(genres),
                "energy": energy,
                "duration_ms": duration,
                "cues": cues,
            }
        ]
    )[0]


def full_track(identifier: str, length: int = 300_000, bpm: float = 128.0, key: str = "8A") -> Track:
    return make_track(identifier, bpm=bpm, key=key, duration=length, a=0, b=length)


class KeyTests(unittest.TestCase):
    def test_parse_camelot_and_musical_keys(self) -> None:
        self.assertEqual(parse_key("8A"), "8A")
        self.assertEqual(parse_key("8a"), "8A")
        self.assertEqual(parse_key(" 11B "), "11B")
        self.assertEqual(parse_key("A minor"), "8A")
        self.assertEqual(parse_key("Am"), "8A")
        self.assertEqual(parse_key("C"), "8B")
        self.assertEqual(parse_key("C major"), "8B")
        self.assertEqual(parse_key("G#m"), "1A")
        self.assertEqual(parse_key("Db"), "3B")
        self.assertIsNone(parse_key(None))
        self.assertIsNone(parse_key("not a key"))

    def test_camelot_relationships(self) -> None:
        self.assertEqual(key_move("8A", "8A")["relation"], "same")
        self.assertEqual(key_move("8A", "9A")["relation"], "adjacent")
        self.assertEqual(key_move("8A", "7A")["relation"], "adjacent")
        self.assertEqual(key_move("8A", "8B")["relation"], "relative")
        self.assertEqual(key_move("8A", "3A")["relation"], "energy-boost")
        self.assertEqual(key_move("8A", "3B")["relation"], "distant")
        self.assertGreater(key_move("8A", "9A")["score"], key_move("8A", "3B")["score"])
        self.assertEqual(key_move("8A", None)["relation"], "unknown")


class SegmentTests(unittest.TestCase):
    def test_full_cues_produce_a_clean_segment(self) -> None:
        segment = segment_for(make_track("t1", bpm=128.0, duration=300_000, a=1_000, b=181_000))
        self.assertEqual(segment["duration_ms"], 180_000)
        self.assertEqual(segment["source"], "cue A to cue B")
        self.assertEqual(segment["bars"], 96.0)
        self.assertEqual(segment["warnings"], [])

    def test_missing_b_cue_runs_to_the_track_end_with_a_warning(self) -> None:
        segment = segment_for(make_track("t1", duration=300_000, a=1_000))
        self.assertEqual(segment["duration_ms"], 299_000)
        self.assertEqual(segment["source"], "cue A to track end")
        self.assertTrue(any("no B cue" in warning for warning in segment["warnings"]))

    def test_missing_cues_are_reported(self) -> None:
        segment = segment_for(make_track("t1", duration=300_000))
        self.assertEqual(segment["duration_ms"], 300_000)
        self.assertEqual(segment["source"], "full track")
        self.assertTrue(any("no A cue" in warning for warning in segment["warnings"]))

    def test_cue_b_before_cue_a_falls_back_to_the_whole_track(self) -> None:
        segment = segment_for(make_track("t1", duration=300_000, a=200_000, b=100_000))
        self.assertEqual(segment["duration_ms"], 300_000)
        self.assertEqual(segment["source"], "full track")
        self.assertTrue(any("is not after cue A" in warning for warning in segment["warnings"]))

    def test_cue_b_beyond_the_track_is_clamped(self) -> None:
        segment = segment_for(make_track("t1", duration=300_000, a=1_000, b=400_000))
        self.assertEqual(segment["end_ms"], 300_000)
        self.assertTrue(any("past the track end" in warning for warning in segment["warnings"]))

    def test_loop_cue_a_defines_the_segment(self) -> None:
        track = parse_tracks(
            [
                {
                    "id": "loop",
                    "title": "Loop",
                    "duration_ms": 300_000,
                    "cues": [{"name": "A", "position_ms": 1_000, "end_ms": 5_000, "kind": "loop"}],
                }
            ]
        )[0]
        segment = segment_for(track)
        self.assertEqual(segment["duration_ms"], 4_000)
        self.assertEqual(segment["source"], "loop A")

    def test_off_grid_segment_gets_a_phrasing_warning(self) -> None:
        segment = segment_for(make_track("t1", bpm=128.0, duration=300_000, a=0, b=62_812))
        self.assertTrue(any("whole bar" in warning for warning in segment["warnings"]))

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(0), "0:00")
        self.assertEqual(format_duration(870_000), "14:30")
        self.assertEqual(format_duration(3_723_000), "1:02:03")


class PlanTests(unittest.TestCase):
    def test_overlaps_shorten_the_total_runtime(self) -> None:
        tracks = [full_track("t1"), full_track("t2"), full_track("t3")]
        report = plan_set(tracks, default_overlap_ms=15_000)
        self.assertEqual(report["summary"]["sum_of_segments_ms"], 900_000)
        self.assertEqual(report["summary"]["total_duration_ms"], 870_000)
        self.assertEqual(report["summary"]["total_duration"], "14:30")
        self.assertEqual(report["summary"]["overlap_saved_ms"], 30_000)
        self.assertEqual([entry["play_start_ms"] for entry in report["timeline"]], [0, 285_000, 570_000])
        self.assertEqual(report["timeline"][0]["overlap_out_ms"], 15_000)
        self.assertEqual(report["timeline"][1]["overlap_in_ms"], 15_000)

    def test_transition_overrides_are_used_and_clamped(self) -> None:
        tracks = [full_track("t1"), full_track("t2")]
        report = plan_set(tracks, [{"from": "t1", "to": "t2", "overlap_ms": 400_000}], default_overlap_ms=1_000)
        transition = report["transitions"][0]
        self.assertEqual(transition["overlap_ms"], 299_999)
        self.assertTrue(any("clamped" in warning for warning in transition["warnings"]))

    def test_tempo_and_harmony_warnings_are_reported(self) -> None:
        tracks = [full_track("t1", bpm=128.0, key="8A"), full_track("t2", bpm=140.0, key="3B")]
        report = plan_set(tracks)
        warnings = " ".join(report["transitions"][0]["warnings"])
        self.assertIn("tempo changes", warnings)
        self.assertIn("distant", warnings)
        self.assertGreater(report["summary"]["warning_count"], 0)

    def test_missing_cues_reduce_the_confidence_summary(self) -> None:
        tracks = [full_track("t1"), make_track("t2", duration=240_000, a=1_000)]
        report = plan_set(tracks)
        self.assertEqual(report["summary"]["tracks_with_full_cues"], 1)
        self.assertEqual(report["summary"]["tracks_missing_cues"], 1)
        self.assertTrue(any("no B cue" in warning for warning in report["warnings"]))

    def test_invalid_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            plan_set([])
        with self.assertRaises(ValueError):
            plan_set([full_track("t1")], default_overlap_ms=-1)
        with self.assertRaises(ValueError):
            plan_set([full_track("t1"), full_track("t2")], [{"from": "t1", "overlap_ms": 1_000}])

    def test_plan_from_payload_reads_json_shapes(self) -> None:
        payload = {
            "tracks": [
                {"id": "a", "title": "A", "duration_ms": 300_000, "cues": [{"name": "A", "position_ms": 0}, {"name": "B", "position_ms": 300_000}]},
                {"id": "b", "title": "B", "duration_ms": 300_000, "cues": [{"name": "A", "position_ms": 0}, {"name": "B", "position_ms": 300_000}]},
            ],
            "transitions": [{"from": "a", "to": "b", "overlap_ms": 30_000}],
        }
        report = plan_from_payload(payload)
        self.assertEqual(report["summary"]["total_duration_ms"], 570_000)


class RecommendationTests(unittest.TestCase):
    def test_bpm_component_handles_half_and_double_time(self) -> None:
        score, reason, known, _ = bpm_match(128.0, 64.0)
        self.assertEqual(score, 1.0)
        self.assertIn("half-time match", reason)
        self.assertTrue(known)
        self.assertEqual(bpm_match(128.0, 256.0)[0], 1.0)
        self.assertIn("double-time match", bpm_match(128.0, 256.0)[1])
        self.assertLess(bpm_match(128.0, 138.0)[0], 1.0)

    def test_genre_and_energy_reasons(self) -> None:
        score, reason, known, _ = genre_match(("techno", "melodic techno"), ("melodic techno", "progressive house"))
        self.assertGreater(score, 0)
        self.assertIn("shared genres", reason)
        self.assertTrue(known)
        energy_score, energy_reason, _, _ = energy_match(6, 7)
        self.assertEqual(energy_score, 1.0)
        self.assertIn("energy lift +1", energy_reason)

    def test_harmonic_neighbour_outranks_a_distant_key(self) -> None:
        current = make_track("current", bpm=128.0, key="8A", genres=("techno",), energy=6, duration=300_000)
        neighbour = make_track("neighbour", bpm=128.0, key="9A", genres=("techno",), energy=6, duration=300_000)
        distant = make_track("distant", bpm=128.0, key="3B", genres=("techno",), energy=6, duration=300_000)
        report = suggest_next(current, [distant, neighbour])
        self.assertEqual(report["suggestions"][0]["id"], "neighbour")
        self.assertGreater(report["suggestions"][0]["score"], report["suggestions"][1]["score"])
        self.assertIn("camelot 8A → 9A", report["suggestions"][0]["reasons"][1])

    def test_current_track_and_excluded_ids_are_skipped(self) -> None:
        current = make_track("current", bpm=128.0, key="8A")
        other = make_track("other", bpm=128.0, key="8A")
        report = suggest_next(current, [current, other], exclude_ids=("other",))
        self.assertEqual(report["suggestions"], [])
        self.assertEqual(report["candidate_count"], 0)

    def test_min_score_filters_weak_candidates(self) -> None:
        current = make_track("current", bpm=128.0, key="8A", genres=("techno",), energy=6)
        strong = make_track("strong", bpm=128.0, key="8A", genres=("techno",), energy=6)
        weak = make_track("weak", bpm=100.0, key="3B", genres=("ambient",), energy=1)
        report = suggest_next(current, [strong, weak], min_score=0.9)
        self.assertEqual([item["id"] for item in report["suggestions"]], ["strong"])

    def test_unknown_metadata_is_reported_but_still_scored(self) -> None:
        current = make_track("current", bpm=None, key=None, energy=None)
        candidate = make_track("candidate", bpm=128.0, key="8A", energy=5)
        report = suggest_next(current, [candidate])
        suggestion = report["suggestions"][0]
        self.assertTrue(any("bpm unknown" in reason for reason in suggestion["reasons"]))
        self.assertTrue(any("key unknown" in reason for reason in suggestion["reasons"]))
        self.assertGreater(suggestion["score"], 0)

    def test_suggest_from_payload_accepts_ids(self) -> None:
        payload = {
            "current": {"id": "a", "title": "A", "bpm": 128, "key": "8A", "genres": ["techno"], "energy": 6},
            "pool": [
                {"id": "b", "title": "B", "bpm": 128, "key": "9A", "genres": ["techno"], "energy": 7},
                {"id": "c", "title": "C", "bpm": 174, "key": "3B", "genres": ["drum and bass"], "energy": 9},
            ],
            "exclude_ids": ["c"],
        }
        report = suggest_from_payload(payload, limit=3)
        self.assertEqual([item["id"] for item in report["suggestions"]], ["b"])


class ParsingTests(unittest.TestCase):
    def test_tracks_parse_from_a_bare_list_and_reject_duplicate_ids(self) -> None:
        tracks = parse_tracks([{"id": "one", "title": "One", "genre": "House, Techno"}])
        self.assertEqual(tracks[0].genres, ("House", "Techno"))
        with self.assertRaises(ValueError):
            parse_tracks([{"id": "one", "title": "One"}, {"id": "one", "title": "Again"}])
        with self.assertRaises(ValueError):
            parse_tracks({"not_tracks": []})

    def test_cue_aliases_and_positions_are_normalized(self) -> None:
        track = parse_tracks([{"id": "x", "title": "X", "cues": [{"name": "intro", "position_ms": 1000}, {"name": "outro", "position_ms": 2000}]}])[0]
        self.assertEqual(track.cue_a.position_ms, 1000)
        self.assertEqual(track.cue_b.position_ms, 2000)


class McpProtocolTests(unittest.TestCase):
    """The server must answer the way any MCP client expects, not just Codex."""

    def test_ping_and_negotiation_methods_return_empty_results(self) -> None:
        for method, expected in (
            ("ping", {}),
            ("resources/list", {"resources": []}),
            ("resources/templates/list", {"resourceTemplates": []}),
            ("prompts/list", {"prompts": []}),
            ("logging/setLevel", {}),
        ):
            reply = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": {}})
            self.assertEqual(reply["result"], expected, method)
            self.assertNotIn("error", reply)

    def test_tool_failure_is_reported_with_is_error(self) -> None:
        reply = mcp_server.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "plan_set", "arguments": {}}}
        )
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("plan_set needs", reply["result"]["content"][0]["text"])

    def test_plan_set_tool_call_round_trip(self) -> None:
        payload = {
            "tracks": [
                {
                    "id": "a",
                    "title": "A",
                    "duration_ms": 300_000,
                    "cues": [{"name": "A", "position_ms": 0}, {"name": "B", "position_ms": 300_000}],
                }
            ]
        }
        reply = mcp_server.handle(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "plan_set", "arguments": {"set": payload, "default_overlap_ms": 16000}}}
        )
        result = json.loads(reply["result"]["content"][0]["text"])
        self.assertEqual(result["summary"]["total_duration"], "5:00")


if __name__ == "__main__":
    unittest.main()
