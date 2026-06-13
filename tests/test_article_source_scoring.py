import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "vault_automation.py"
SPEC = importlib.util.spec_from_file_location("vault_automation", MODULE_PATH)
va = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = va
SPEC.loader.exec_module(va)


class SourceAwareScoringTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.vault = self.root / "vault"
        for folder in ("notes", "factions", "lore", "sessions"):
            (self.vault / folder).mkdir(parents=True)
        self.patchers = [
            patch.object(va, "ROOT", self.root),
            patch.object(va, "VAULT", self.vault),
        ]
        for p in self.patchers:
            p.start()
        # Per-process caches must be cleared between cases since VAULT is patched.
        va._RECENT_DISCORD_SUMMARIES = None
        va._LATEST_VAULT_SESSION = None
        va._LATEST_SESSION_TEXT = None

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        va._RECENT_DISCORD_SUMMARIES = None
        va._LATEST_VAULT_SESSION = None
        va._LATEST_SESSION_TEXT = None
        self.tempdir.cleanup()

    def _summary(self, week: str, body: str):
        (self.vault / "notes" / f"Discord Summary {week}.md").write_text(
            f"---\ntitle: \"Discord Summary {week}\"\n---\n\n{body}\n", encoding="utf-8"
        )

    def _article(self, folder: str, name: str, body: str) -> Path:
        path = self.vault / folder / f"{name}.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_uncited_recent_summary_adds_bonus(self):
        self._summary("2026-W23", "Akla-Chah revealed the Varumani are Rudishva constructs.")
        path = self._article(
            "factions", "Varumani",
            "---\ntitle: Loyal Varumani\naliases:\n  - Varumani\n---\n# Loyal Varumani\n\n## Summary\nThe Varumani faction.\n",
        )
        score, reasons = va.score_article(path, va.read_text(path))
        joined = " ".join(reasons)
        self.assertIn("unincorporated recent sources", joined)
        self.assertIn("Discord Summary 2026-W23", joined)

    def test_cited_summary_yields_no_source_bonus(self):
        self._summary("2026-W23", "Akla-Chah revealed the Varumani are Rudishva constructs.")
        path = self._article(
            "factions", "Varumani",
            "---\ntitle: Loyal Varumani\naliases:\n  - Varumani\n---\n# Loyal Varumani\n\n"
            "## Summary\nThe Varumani faction. ([[notes/Discord Summary 2026-W23.md|Discord Summary 2026-W23]])\n",
        )
        score, reasons = va.score_article(path, va.read_text(path))
        self.assertNotIn("unincorporated recent sources", " ".join(reasons))

    def test_short_name_not_matched(self):
        # "Set" is below the 4-char floor and must not trigger incidental matches.
        self._summary("2026-W23", "The party fought in the Forum of Set against many foes.")
        path = self._article(
            "factions", "Set",
            "---\ntitle: Set\n---\n# Set\n\n## Summary\nA deity.\n",
        )
        score, reasons = va.score_article(path, va.read_text(path))
        self.assertNotIn("unincorporated recent sources", " ".join(reasons))

    def test_lore_dir_is_scanned_by_article_queue(self):
        self.assertIn("lore", va.ARTICLE_QUEUE_DIRS)
        self._summary("2026-W23", "Akla-Chah revealed the Varumani are Rudishva constructs.")
        self._article(
            "lore", "Varumani",
            "---\ntags:\n  - lore\naliases:\n  - Varumani lore\n---\n# Varumani\n\n## Who\nThe Varumani.\n",
        )
        queue = va.build_article_queue(limit=30)
        self.assertIn("vault/lore/Varumani.md", {item.path for item in queue})


if __name__ == "__main__":
    unittest.main()
