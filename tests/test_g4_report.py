"""G4 端到端报告（DoD E1 / E2 / E3 + 门控事实）：机器事实不靠注释自称。"""
from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import g4_report  # noqa: E402
import gate  # noqa: E402
from src import schema  # noqa: E402
from src.world.atlas import new_atlas  # noqa: E402
from src.world.game import (  # noqa: E402
    apply_effects, from_save, new_game, to_save, train,
)
from src.world.scripts import all_scripts, effects_of  # noqa: E402
from src.world.save import FORBIDDEN_KEYS, decode, encode  # noqa: E402

G4_SOURCES = (
    "src/world/atlas.py", "src/world/evolution.py", "src/world/scripts.py",
    "src/world/save.py", "src/world/game.py", "tools/g4_report.py",
)


class TestG4Report(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)
        cls.report = g4_report.run(cls.tables, "G4-demo")

    def test_all_three_dod_machine_facts(self):
        report = self.report
        self.assertTrue(report["complete"])
        self.assertTrue(report["atlas"]["complete"])
        self.assertEqual(report["atlas"]["species_covered"],
                         report["atlas"]["species_total"])
        self.assertEqual(report["atlas"]["trivial_regions"], ["r7"])
        self.assertFalse(report["counter_proof"]["complete"])
        self.assertTrue(report["save"]["roundtrip"])
        self.assertTrue(report["save"]["restored_ok"])
        self.assertTrue(report["game"]["world_untouched"])
        self.assertTrue(report["game"]["display_changed"])
        self.assertLessEqual(report["scripts"]["total"], 20)

    def test_survey_covers_every_chunk(self):
        self.assertEqual(self.report["survey"]["chunks"],
                         self.report["survey"]["expected_chunks"])
        self.assertEqual(self.report["survey"]["chunks"], 100)
        self.assertEqual(len(self.report["survey"]["surveyed_regions"]), 7)

    def test_generated_keys_are_all_rejected(self):
        self.assertEqual(set(self.report["save"]["rejected_generated_keys"]),
                         set(FORBIDDEN_KEYS))

    def test_run_is_deterministic_and_pure(self):
        before = copy.deepcopy(self.tables)
        self.assertEqual(g4_report.run(self.tables, "G4-demo"), self.report)
        self.assertEqual(self.tables, before)

    def test_other_seeds_also_complete(self):
        for seed in ("another-seed", "G3-autoplayer", "12345"):
            report = g4_report.run(self.tables, seed)
            self.assertTrue(report["complete"], seed)
            self.assertTrue(report["atlas"]["complete"], seed)

    def test_cli_prints_json_and_exits_zero(self):
        result = subprocess.run([sys.executable, "tools/g4_report.py", "G4-demo"],
                                cwd=ROOT, capture_output=True, text=True,
                                timeout=120)
        self.assertEqual(result.returncode, 0,
                         f"{result.stdout} {result.stderr}")
        payload = json.loads(result.stdout)
        self.assertTrue(payload["complete"])
        self.assertTrue(payload["save"]["roundtrip"])


class TestSingleMutationEntry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = schema.load_all(ROOT)

    def test_apply_effects_changes_only_display_fields(self):
        game = new_game(self.tables, "effects-test")
        effects = effects_of(all_scripts())
        after = apply_effects(game, effects)
        self.assertEqual(after.world, game.world)
        self.assertEqual(after.progress, game.progress)
        self.assertEqual(after.atlas, game.atlas)
        self.assertEqual(after.party, game.party)
        self.assertEqual(after.world_seed, game.world_seed)
        self.assertNotEqual(after.flags, game.flags)
        self.assertNotEqual(after.notes, game.notes)
        self.assertNotEqual(after.log, game.log)

    def test_apply_effects_rejects_unknown_effect_and_bad_input(self):
        game = new_game(self.tables, "effects-test")
        with self.assertRaises(ValueError):
            apply_effects(game, ("not-an-effect",))
        with self.assertRaises(ValueError):
            apply_effects("not-a-game", ())

    def test_train_changes_only_party(self):
        game = new_game(self.tables, "effects-test")
        trained = train(game, 0)
        self.assertEqual(trained.world, game.world)
        self.assertEqual(trained.progress, game.progress)
        self.assertEqual(trained.atlas, game.atlas)
        self.assertEqual(trained.flags, game.flags)
        self.assertEqual(trained.notes, game.notes)
        self.assertEqual(trained.log, game.log)
        self.assertEqual(trained.party[0].level, game.party[0].level + 1)
        with self.assertRaises(ValueError):
            train(game, 5)

    def test_to_save_projection_and_from_save(self):
        world, state, atlas, _, _, _ = g4_report._walk(self.tables, "G4-demo")
        game = new_game(self.tables, "G4-demo", state, atlas)
        save = to_save(game, self.tables)
        prefixes = {flag.split(":", 1)[0] for flag in save.flags}
        self.assertTrue({"region", "ability", "atlas", "milestone"} <= prefixes)
        text = encode(save)
        for key in FORBIDDEN_KEYS:
            self.assertNotIn(key, text)
        restored = from_save(decode(text), self.tables)
        self.assertEqual(restored.progress.surveyed_regions,
                         state.surveyed_regions)
        self.assertEqual(restored.progress.abilities, state.abilities)
        self.assertEqual(restored.party, game.party)
        self.assertEqual(restored.atlas, new_atlas())


class TestG4GateFacts(unittest.TestCase):
    def test_g4_sources_have_no_assert(self):
        offenders = []
        for rel in G4_SOURCES:
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
            offenders += [f"{rel}:{n.lineno}" for n in ast.walk(tree)
                          if isinstance(n, ast.Assert)]
        self.assertEqual(offenders, [])

    def test_zero_table_and_snapshot_changes(self):
        self.assertEqual(gate.check_golden_snapshot(ROOT), [])
        schema.verify_manifest(ROOT)  # 不抛即证明三表哈希与登记值一致
        self.assertEqual(gate.run(ROOT), [])


if __name__ == "__main__":
    unittest.main()
