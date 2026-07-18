from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "infra/supabase/migrations/006_stage10c_observability.sql"
WORKER = ROOT / "infra/worker/src/index.ts"
NORMALIZER = ROOT / "infra/worker/src/observability.ts"


class Stage10CObservabilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.worker = WORKER.read_text(encoding="utf-8")
        cls.normalizer = NORMALIZER.read_text(encoding="utf-8")

    def test_migration_is_idempotent_and_transactional(self) -> None:
        self.assertIn("BEGIN;", self.sql)
        self.assertIn("COMMIT;", self.sql)
        self.assertIn("ADD COLUMN IF NOT EXISTS", self.sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS", self.sql)
        self.assertNotRegex(self.sql.upper(), r"\bDROP\s+(TABLE|COLUMN|SCHEMA)\b")

    def test_signal_observability_columns_are_present(self) -> None:
        required = {
            "signal_eval_id",
            "decision",
            "technical_signal_status",
            "execution_mode",
            "order_send_allowed",
            "would_have_traded",
            "primary_signal_reason",
            "governance_guard_reason",
            "execution_denied_reason",
            "strategy_variant",
            "guard_version",
            "magic_number",
            "boot_id",
            "bar_h4",
        }
        for column in required:
            self.assertRegex(self.sql, rf"\b{re.escape(column)}\b")

    def test_trade_identity_columns_are_present(self) -> None:
        for column in (
            "order_ticket",
            "deal_ticket",
            "position_id",
            "signal_eval_id",
            "execution_mode",
            "strategy_variant",
            "link_status",
        ):
            self.assertRegex(self.sql, rf"\b{re.escape(column)}\b")

    def test_legacy_ticket_is_never_reclassified_as_order_or_deal(self) -> None:
        normalized = " ".join(self.sql.lower().split())
        self.assertNotIn("set position_id = ticket", normalized)
        self.assertNotIn("set order_ticket = ticket", normalized)
        self.assertNotIn("set deal_ticket = ticket", normalized)
        self.assertIn("raw_payload ->> 'order_ticket'", normalized)
        self.assertIn("raw_payload ->> 'deal_ticket'", normalized)

    def test_unique_historical_signal_position_link_is_supported(self) -> None:
        self.assertIn("WITH candidate_links AS", self.sql)
        self.assertIn("HAVING COUNT(*) = 1", self.sql)
        self.assertIn("s.eval_time = t.open_time", self.sql)
        self.assertIn("ABS(s.entry_price - t.open_price) <= 0.00001", self.sql)

    def test_shadow_entry_error_is_repaired(self) -> None:
        self.assertIn("ENTRY_READY_SHADOW_ONLY_BLOCKED", self.sql)
        self.assertIn("UPPER(decision) IN ('ERROR', 'SIGNAL', 'BLOCKED')", self.sql)
        self.assertIn("UPPER(COALESCE(action, '')) LIKE 'ENTRY_READY%'", self.sql)
        self.assertIn("would_have_traded", self.sql)

    def test_worker_persists_separate_reasons_and_identities(self) -> None:
        for field in (
            "primary_signal_reason",
            "governance_guard_reason",
            "execution_denied_reason",
            "order_ticket",
            "deal_ticket",
            "position_id",
            "signal_eval_id",
            "link_status",
        ):
            self.assertIn(field, self.worker)

    def test_worker_does_not_patch_by_position_id_directly(self) -> None:
        self.assertIn("findOpenTradeCandidates", self.worker)
        self.assertIn("chooseSingleCandidate", self.worker)
        self.assertIn("id=eq.", self.worker)
        self.assertNotIn("trades?position_id=eq.", self.worker)

    def test_signal_insert_failure_is_not_reported_as_success(self) -> None:
        self.assertIn(
            'await requireInsert(supabaseUrl, key, "signal_evals", row, requestId)',
            self.worker,
        )
        self.assertIn("Supabase ${table} insert failed", self.worker)

    def test_actual_v4430_ticket_semantics_are_documented_in_code(self) -> None:
        self.assertIn("trade_open payload sends ticket == position_id", self.normalizer)
        self.assertIn("LINKED_SIGNAL_POSITION_MISSING_ORDER_TICKET", self.normalizer)
        self.assertIn("body.open_time", self.normalizer)
        self.assertIn("body.eval_time", self.normalizer)

    def test_observability_layer_never_enables_orders(self) -> None:
        self.assertNotRegex(
            self.normalizer,
            r"orderSendAllowed\s*:\s*true",
        )
        self.assertIn("ENTRY_READY_SHADOW_ONLY_BLOCKED", self.normalizer)


if __name__ == "__main__":
    unittest.main()
