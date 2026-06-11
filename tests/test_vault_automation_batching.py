import importlib.util
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "vault_automation.py"
SPEC = importlib.util.spec_from_file_location("vault_automation", MODULE_PATH)
va = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = va
SPEC.loader.exec_module(va)


class BatchIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.vault = self.root / "vault"
        self.automation = self.root / "data" / "automation"
        (self.vault / "npcs").mkdir(parents=True)
        (self.automation / "proposals").mkdir(parents=True)
        self.patchers = [
            patch.object(va, "ROOT", self.root),
            patch.object(va, "VAULT", self.vault),
            patch.object(va, "AUTOMATION_DIR", self.automation),
            patch.object(va, "refresh_vault_rag_safely", return_value={"ok": True}),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.tempdir.cleanup()

    def _write_article(self, name):
        path = self.vault / "npcs" / f"{name}.md"
        path.write_text(
            f"---\ntags: [npc]\n---\n\n# {name}\n\n## Notes\n\nExisting.\n",
            encoding="utf-8",
        )
        return path

    def test_article_apply_only_uses_current_batch_and_file_budget(self):
        first = self._write_article("First")
        second = self._write_article("Second")
        legacy = self._write_article("Legacy")
        verifications = [
            {
                "proposal_id": "first",
                "batch_id": "current",
                "verifier_status": "supported",
                "article_path": "vault/npcs/First.md",
                "addition_type": "append_bullet_to_section",
                "target_section": "Notes",
                "proposed_text": "- Current first fact with enough unique words.",
            },
            {
                "proposal_id": "second",
                "batch_id": "current",
                "verifier_status": "supported",
                "article_path": "vault/npcs/Second.md",
                "addition_type": "append_bullet_to_section",
                "target_section": "Notes",
                "proposed_text": "- Current second fact with enough unique words.",
            },
            {
                "proposal_id": "legacy",
                "batch_id": "old",
                "verifier_status": "supported",
                "article_path": "vault/npcs/Legacy.md",
                "addition_type": "append_bullet_to_section",
                "target_section": "Notes",
                "proposed_text": "- Old batch fact must not be applied.",
            },
        ]
        va.write_json(
            self.automation / "proposals" / "article_edit_verifications.json",
            verifications,
        )

        result = va.apply_verified_article_edits(
            apply_changes=True,
            limit=3,
            batch_id="current",
            max_files=1,
        )

        self.assertEqual(result["total_applied"], 1)
        self.assertEqual(result["deferred_file_count"], 1)
        self.assertIn("Current first fact", first.read_text(encoding="utf-8"))
        self.assertNotIn("Current second fact", second.read_text(encoding="utf-8"))
        self.assertNotIn("Old batch fact", legacy.read_text(encoding="utf-8"))

    def test_proposal_writer_stamps_batch(self):
        proposal = va.MetadataEditProposal(
            article_path="vault/npcs/First.md",
            article_title="First",
            article_kind="npc",
            proposal_type="add_tag",
            value="status/known",
            rationale="test",
            sources=[],
        )

        va.write_metadata_edit_report([proposal], batch_id="batch-123")

        payload = json.loads(
            (self.automation / "proposals" / "metadata_edit_proposals.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(payload[0]["batch_id"], "batch-123")

    def test_batch_stamping_covers_every_proposal_dataclass(self):
        proposals = [
            va.EntityLinkProposal(
                source="vault/sessions/Session 1.md",
                entity="First",
                entity_path="vault/npcs/First.md",
                kind="npc",
                mention="First",
                context="First did a thing.",
                status="proposed",
            ),
            va.NewEntityCandidate(
                name="First",
                kind="npc",
                canonical_target_dir="vault/npcs",
                mention_count=1,
                sources=[],
                rationale="test",
                nearest_existing=None,
                nearest_distance=1.0,
            ),
            va.ArticleEditProposal(
                article_path="vault/npcs/First.md",
                article_title="First",
                article_kind="npc",
                article_score=1,
                addition_type="fact",
                target_section="Notes",
                proposed_text="text",
                rationale="test",
                sources=[],
            ),
            va.MetadataEditProposal(
                article_path="vault/npcs/First.md",
                article_title="First",
                article_kind="npc",
                proposal_type="add_tag",
                value="status/known",
                rationale="test",
                sources=[],
            ),
        ]

        va.assign_proposal_batch(proposals, "batch-456")

        for proposal in proposals:
            self.assertEqual(proposal.batch_id, "batch-456")

    def test_historical_verification_does_not_starve_current_batch(self):
        article = self._write_article("First")
        proposal = va.ArticleEditProposal(
            article_path=article.relative_to(self.root).as_posix(),
            article_title="First",
            article_kind="npc",
            article_score=1,
            addition_type="append_bullet_to_section",
            target_section="Notes",
            proposed_text="- A current batch fact.",
            rationale="test",
            sources=[],
            proposal_id="same-id",
            batch_id="current",
        )
        va.write_json(
            self.automation / "proposals" / "article_edit_proposals.json",
            [va.asdict(proposal)],
        )
        va.write_json(
            self.automation / "proposals" / "article_edit_verifications.json",
            [{
                **va.asdict(proposal),
                "batch_id": "old",
                "verifier_status": "supported",
                "verifier_rationale": "old",
                "verifier_evidence": "old",
            }],
        )

        with patch.object(
            va,
            "llm_chat_json",
            return_value={"status": "supported", "rationale": "current", "evidence": "current"},
        ):
            verified = va.verify_article_edit_proposals(limit=3, batch_id="current")

        self.assertEqual(len(verified), 1)
        self.assertEqual(verified[0]["batch_id"], "current")

    def test_negative_legacy_limits_resolve_to_safe_defaults(self):
        config = {"article_edit_apply_limit": -1}
        self.assertEqual(
            va.scheduled_limit(config, "article_edit_apply_limit", 3, 3),
            3,
        )
        self.assertEqual(
            va.scheduled_limit({"entity_link_apply_limit": 100}, "entity_link_apply_limit", 10, 10),
            10,
        )

    def test_import_preview_paths_are_counted_once(self):
        result = {
            "changes": [
                "create vault/sessions/Session 99.md",
                "update vault/sessions/Session 98.md",
                "update vault/sessions/Session 98.md",
            ]
        }
        self.assertEqual(
            va.import_result_files(result),
            {
                "vault/sessions/Session 99.md",
                "vault/sessions/Session 98.md",
            },
        )

    def test_orchestrated_applicators_suppress_nested_rag_publication(self):
        article = self._write_article("First")
        va.write_json(
            self.automation / "proposals" / "article_edit_verifications.json",
            [{
                "proposal_id": "article",
                "batch_id": "batch",
                "verifier_status": "supported",
                "article_path": article.relative_to(self.root).as_posix(),
                "addition_type": "append_bullet_to_section",
                "target_section": "Notes",
                "proposed_text": "- Supported article fact with enough unique words.",
            }],
        )
        va.write_json(
            self.automation / "proposals" / "metadata_edit_verifications.json",
            [{
                "proposal_id": "metadata",
                "batch_id": "batch",
                "verifier_status": "supported",
                "article_path": article.relative_to(self.root).as_posix(),
                "proposal_type": "add_tag",
                "value": "status/known",
            }],
        )
        va.write_json(
            self.automation / "proposals" / "new_entity_verifications.json",
            [{
                "proposal_id": "entity",
                "batch_id": "batch",
                "verifier_status": "confirmed",
                "name": "Second",
                "kind": "NPC",
                "verifier_summary": "A supported new NPC.",
                "sources": [],
            }],
        )

        with patch.object(va, "refresh_vault_rag_safely") as refresh:
            va.apply_verified_article_edits(
                apply_changes=True,
                batch_id="batch",
                publish_rag=False,
            )
            va.apply_verified_metadata_edits(
                apply_changes=True,
                batch_id="batch",
                publish_rag=False,
            )
            va.apply_verified_new_entities(
                apply_changes=True,
                batch_id="batch",
                publish_rag=False,
            )

        refresh.assert_not_called()

    def test_standalone_apply_still_publishes(self):
        article = self._write_article("First")
        va.write_json(
            self.automation / "proposals" / "article_edit_verifications.json",
            [{
                "proposal_id": "article",
                "verifier_status": "supported",
                "article_path": article.relative_to(self.root).as_posix(),
                "addition_type": "append_bullet_to_section",
                "target_section": "Notes",
                "proposed_text": "- Standalone supported fact with enough unique words.",
            }],
        )

        with patch.object(
            va,
            "refresh_vault_rag_safely",
            return_value={"ok": True, "row_count": 1},
        ) as refresh:
            result = va.apply_verified_article_edits(apply_changes=True)

        refresh.assert_called_once_with()
        self.assertEqual(result["vault_rag_refresh"]["row_count"], 1)


class ArchitectureDriftTests(unittest.TestCase):
    def test_current_arden_docs_and_code_do_not_reference_retired_vector_store(self):
        root = MODULE_PATH.parents[1]
        paths = [
            root / "AGENTS.md",
            root / "docs" / "RAG_VAULT_MAINTENANCE.md",
            root / "scripts" / "vault_automation.py",
        ]
        obsolete = "chro" + "ma"
        for path in paths:
            with self.subTest(path=path):
                self.assertNotIn(obsolete, path.read_text(encoding="utf-8").lower())

    def test_runtime_config_has_no_retired_arden_index_keys(self):
        config = json.loads(
            (MODULE_PATH.parents[1] / "config" / "local_sources.json").read_text(
                encoding="utf-8"
            )
        )
        obsolete = "chro" + "ma"
        self.assertFalse([key for key in config if obsolete in key.lower()])


class PolishVerifierTests(unittest.TestCase):
    def test_polish_verifier_approves_supported_revelations(self):
        response = {
            "status": "approved",
            "rationale": "The later session supports the corrected identity.",
            "supported_revelations": ["The apparent merchant is revealed as the magistrate."],
            "unsupported_changes": [],
            "lost_valid_facts": [],
            "relationship_concerns": [],
            "quality_concerns": [],
        }
        with (
            patch.object(va, "load_local_sources", return_value={"llm_model": "writer"}),
            patch.object(va, "llm_chat_json", return_value=response) as verifier,
        ):
            result = va.verify_article_polish(
                "Old identity.",
                "Corrected identity.",
                [{"path": "vault/sessions/Session 60.md", "section": "Recap", "text": "The reveal."}],
                "vault/npcs/Example.md",
                "Example",
                "npc",
            )

        self.assertEqual(result["status"], "approved")
        self.assertEqual(len(result["supported_revelations"]), 1)
        verifier.assert_called_once()

    def test_polish_verifier_rejects_unsupported_change(self):
        response = {
            "status": "rejected",
            "rationale": "The rewrite invents a family relationship.",
            "unsupported_changes": "Claims the NPC is Set's son.",
        }
        with (
            patch.object(va, "load_local_sources", return_value={"llm_model": "writer"}),
            patch.object(va, "llm_chat_json", return_value=response),
        ):
            result = va.verify_article_polish(
                "Original.",
                "Invented.",
                [],
                "vault/npcs/Example.md",
                "Example",
                "npc",
            )

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["unsupported_changes"], ["Claims the NPC is Set's son."])

    def test_polish_verifier_error_fails_closed(self):
        with (
            patch.object(va, "load_local_sources", return_value={"llm_model": "writer"}),
            patch.object(va, "llm_chat_json", side_effect=RuntimeError("offline")),
        ):
            result = va.verify_article_polish(
                "Original.",
                "Rewrite.",
                [],
                "vault/npcs/Example.md",
                "Example",
                "npc",
            )

        self.assertEqual(result["status"], "error")

    def test_queue_rejection_retains_original_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            article = root / "vault" / "npcs" / "Example.md"
            article.parent.mkdir(parents=True)
            original = "---\ntags: [npc]\n---\n\n# Example\n\n## Notes\n\nOriginal.\n"
            rewrite = "---\ntags: [npc]\n---\n\n# Example\n\n## Notes\n\nInvented.\n"
            article.write_text(original, encoding="utf-8")
            automation = root / "data" / "automation"
            item = va.ArticleQueueItem(
                path="vault/npcs/Example.md",
                title="Example",
                kind="npc",
                tags=("npc",),
                score=10,
                reasons=("test",),
                queries=("Example",),
            )
            with (
                patch.object(va, "ROOT", root),
                patch.object(va, "VAULT", root / "vault"),
                patch.object(va, "AUTOMATION_DIR", automation),
                patch.object(va, "build_article_queue", return_value=[item]),
                patch.object(va, "gather_article_research_chunks", return_value=[]),
                patch.object(va, "llm_chat_text", side_effect=[rewrite, rewrite]),
                patch.object(
                    va,
                    "verify_article_polish",
                    return_value={
                        "status": "rejected",
                        "rationale": "unsupported",
                        "supported_revelations": [],
                        "unsupported_changes": ["invented"],
                        "lost_valid_facts": [],
                        "relationship_concerns": [],
                        "quality_concerns": [],
                    },
                ),
            ):
                rc = va.cmd_polish_queue(
                    Namespace(limit=1, apply=True, top_k=1, kinds=None)
                )

            self.assertEqual(rc, 0)
            self.assertEqual(article.read_text(encoding="utf-8"), original)

    def test_queue_approval_writes_rewrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            article = root / "vault" / "npcs" / "Example.md"
            article.parent.mkdir(parents=True)
            original = "---\ntags: [npc]\n---\n\n# Example\n\n## Notes\n\nOriginal.\n"
            rewrite = "---\ntags: [npc]\n---\n\n# Example\n\n## Notes\n\nSupported correction.\n"
            article.write_text(original, encoding="utf-8")
            automation = root / "data" / "automation"
            item = va.ArticleQueueItem(
                path="vault/npcs/Example.md",
                title="Example",
                kind="npc",
                tags=("npc",),
                score=10,
                reasons=("test",),
                queries=("Example",),
            )
            with (
                patch.object(va, "ROOT", root),
                patch.object(va, "VAULT", root / "vault"),
                patch.object(va, "AUTOMATION_DIR", automation),
                patch.object(va, "build_article_queue", return_value=[item]),
                patch.object(va, "gather_article_research_chunks", return_value=[]),
                patch.object(va, "llm_chat_text", side_effect=[rewrite, rewrite]),
                patch.object(
                    va,
                    "verify_article_polish",
                    return_value={
                        "status": "approved",
                        "rationale": "supported",
                        "supported_revelations": ["correction"],
                        "unsupported_changes": [],
                        "lost_valid_facts": [],
                        "relationship_concerns": [],
                        "quality_concerns": [],
                    },
                ),
            ):
                rc = va.cmd_polish_queue(
                    Namespace(limit=1, apply=True, top_k=1, kinds=None)
                )

            self.assertEqual(rc, 0)
            self.assertIn("Supported correction.", article.read_text(encoding="utf-8"))

    def test_queue_verifier_error_fails_job_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            article = root / "vault" / "npcs" / "Example.md"
            article.parent.mkdir(parents=True)
            original = "---\ntags: [npc]\n---\n\n# Example\n\n## Notes\n\nOriginal.\n"
            rewrite = "---\ntags: [npc]\n---\n\n# Example\n\n## Notes\n\nCandidate.\n"
            article.write_text(original, encoding="utf-8")
            item = va.ArticleQueueItem(
                path="vault/npcs/Example.md",
                title="Example",
                kind="npc",
                tags=("npc",),
                score=10,
                reasons=("test",),
                queries=("Example",),
            )
            with (
                patch.object(va, "ROOT", root),
                patch.object(va, "VAULT", root / "vault"),
                patch.object(va, "AUTOMATION_DIR", root / "data" / "automation"),
                patch.object(va, "build_article_queue", return_value=[item]),
                patch.object(va, "gather_article_research_chunks", return_value=[]),
                patch.object(va, "llm_chat_text", side_effect=[rewrite, rewrite]),
                patch.object(
                    va,
                    "verify_article_polish",
                    return_value={
                        "status": "error",
                        "rationale": "verifier offline",
                        "supported_revelations": [],
                        "unsupported_changes": [],
                        "lost_valid_facts": [],
                        "relationship_concerns": [],
                        "quality_concerns": [],
                    },
                ),
            ):
                rc = va.cmd_polish_queue(
                    Namespace(limit=1, apply=True, top_k=1, kinds=None)
                )

            self.assertEqual(rc, 1)
            self.assertEqual(article.read_text(encoding="utf-8"), original)

    def test_polish_rotation_defers_recent_attempts(self):
        with tempfile.TemporaryDirectory() as temp:
            automation = Path(temp) / "data" / "automation"
            now = va.datetime(2026, 6, 10, tzinfo=va.timezone.utc)
            recent = va.ArticleQueueItem(
                path="vault/npcs/Recent.md",
                title="Recent",
                kind="npc",
                tags=(),
                score=20,
                reasons=(),
                queries=(),
            )
            eligible = va.ArticleQueueItem(
                path="vault/npcs/Eligible.md",
                title="Eligible",
                kind="npc",
                tags=(),
                score=10,
                reasons=(),
                queries=(),
            )
            with patch.object(va, "AUTOMATION_DIR", automation):
                va.write_json(
                    va.polish_rotation_path(),
                    {
                        "paths": {
                            recent.path: {
                                "attempted_at": (now - va.timedelta(days=1)).isoformat(),
                                "status": "rejected",
                            }
                        }
                    },
                )
                selected, deferred = va.select_polish_queue(
                    [recent, eligible],
                    limit=1,
                    cooldown_days=7,
                    now=now,
                )

            self.assertEqual([item.path for item in selected], [eligible.path])
            self.assertEqual(deferred, 1)

    def test_polish_rotation_records_all_attempt_outcomes(self):
        with tempfile.TemporaryDirectory() as temp:
            automation = Path(temp) / "data" / "automation"
            attempted_at = va.datetime(2026, 6, 10, tzinfo=va.timezone.utc)
            with patch.object(va, "AUTOMATION_DIR", automation):
                va.update_polish_rotation(
                    [
                        {"path": "vault/npcs/Approved.md", "verification": {"status": "approved"}},
                        {"path": "vault/npcs/Rejected.md", "verification": {"status": "rejected"}},
                        {"path": "vault/npcs/Unchanged.md", "changed": False},
                    ],
                    attempted_at=attempted_at,
                )
                payload = va.load_polish_rotation()

            self.assertEqual(payload["paths"]["vault/npcs/Approved.md"]["status"], "approved")
            self.assertEqual(payload["paths"]["vault/npcs/Rejected.md"]["status"], "rejected")
            self.assertEqual(payload["paths"]["vault/npcs/Unchanged.md"]["status"], "unchanged")


if __name__ == "__main__":
    unittest.main()
