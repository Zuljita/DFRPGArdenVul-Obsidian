import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "vault_automation.py"
SPEC = importlib.util.spec_from_file_location("vault_automation", MODULE_PATH)
va = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = va
SPEC.loader.exec_module(va)

import unittest

SUMMARY = """---
title: "Discord Summary 2026-W23"
tags:
  - discord-summary
  - canonical-source
---

## Source
- Private Discord weekly digest

## Navigation
- Previous Discord Summary: Discord Summary 2026-W22

# Weekly Knowledge Base: Arden Vul

**Summary**
The company focused on the hunt for Kerbog Khan and conducted experiments in town this week.

**Uvash Edzuson**
* Brewed a Potion of Fire Resistance and prepared for the assault on the Khan.

**Vaelitharon "Vael" Sunshadow**
* Conducted an experiment involving a goat, a laser pistol, and a Potion of Fire Resistance; the goat survived, but $500 and one potion were lost.
* Purchased a goat for $500 and utilized a Delver's periscope to scout ahead.

**Lore & Discoveries**
* Akla-Chah confirmed the Varumani are Rudishva constructs created for security and labor.
"""

NORMAL = """---
title: Some NPC
tags:
  - npc
---

# Some NPC

## Summary
A reasonably long summary paragraph that comfortably clears the minimum chunk character threshold used by the indexer for vault notes.

## Notes
Another reasonably long section of prose so that the section split behaves exactly as it did before the summary-aware change landed in the chunker.
"""


class SummaryChunkingTests(unittest.TestCase):
    def test_detects_discord_summary(self):
        self.assertTrue(va._is_discord_summary(SUMMARY))
        self.assertFalse(va._is_discord_summary(NORMAL))

    def test_summary_splits_into_focused_sections(self):
        chunks = va.chunk_markdown_for_rag(SUMMARY)
        sections = [s for s, _ in chunks]
        # Per-character and per-topic bold labels become their own sections.
        self.assertIn('Vaelitharon "Vael" Sunshadow', sections)
        self.assertIn("Lore & Discoveries", sections)
        # No giant catch-all: the whole body must not collapse into one chunk.
        self.assertGreaterEqual(len(chunks), 5)

    def test_goat_experiment_isolated_in_vael_chunk(self):
        chunks = dict(va.chunk_markdown_for_rag(SUMMARY))
        vael = chunks['Vaelitharon "Vael" Sunshadow']
        self.assertIn("goat", vael.lower())
        self.assertIn("laser pistol", vael.lower())
        # The goat experiment should NOT bleed into unrelated sections.
        self.assertNotIn("goat", chunks["Lore & Discoveries"].lower())

    def test_normal_note_chunking_unchanged(self):
        # Summary-aware splitting must not alter non-summary files.
        chunks = va.chunk_markdown_for_rag(NORMAL)
        sections = [s for s, _ in chunks]
        self.assertIn("Summary", sections)
        self.assertIn("Notes", sections)
        self.assertEqual(len(chunks), 2)


if __name__ == "__main__":
    unittest.main()
