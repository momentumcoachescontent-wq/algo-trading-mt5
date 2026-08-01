from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "infra/supabase/migrations/006_stage10c_observability.sql"
PREFLIGHT = ROOT / "infra/supabase/validation/006_stage10c_observability_preflight.sql"
VALIDATION = ROOT / "infra/supabase/validation/006_stage10c_observability_validation.sql"
WORKER = ROOT / "infra/worker/src/index.ts"
NORMALIZER = ROOT / "infra/worker/src/observability.ts"
CANDIDATE = ROOT / "infra/worker/src/tradeCandidate.ts"


class Stage10CObservabilityContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = MIGRATION.read_text(encoding="utf-8")
        cls.preflight = PREFLIGHT.read_text(encoding="utf-8")
        cls.validation = VALIDATION.read_text(encoding="utf-8")
        cls.worker = WORKER.read_text(encoding="utf-8")
        cls.normalizer = NORMALIZER.read_text(encoding="utf-8")
        cls.candidate = CANDIDATE.read_text(encoding="utf-8")

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

    def test_decision_constraint_preserves_legacy_and_allows_normalized_values(self) -> None:
        drop_marker = "DROP CONSTRAINT IF EXISTS signal_evals_decision_check"
        add_marker = "ADD CONSTRAINT signal_evals_decision_check CHECK"
        normalize_marker = "UPDATE public.signal_evals\nSET decision = CASE"
        self.assertIn(drop_marker, self.sql)
        self.assertIn(add_marker, self.sql)
        self.assertLess(self.sql.index(add_marker), self.sql.index(normalize_marker))
        for decision in (
            "SIGNAL",
            "BLOCKED",
            "OPENED",
            "CLOSED",
            "ERROR",
            "ENTRY_READY",
            "ENTRY_READY_REAL_ALLOWED",
            "ENTRY_READY_SHADOW_ONLY_BLOCKED",
            "BLOCKED_BY_EXECUTION_SCOPE",
            "BLOCKED_BY_GOVERNANCE_GUARD",
            "BLOCKED_BY_TECHNICAL_GUARD",
            "RAW_SIGNAL",
            "NO_SIGNAL",
        ):
            self.assertIn(f"'{decision}'", self.sql)

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

    def test_worker_and_sql_share_canonical_signal_id_contract(self) -> None:
        prefix = "stage10c-sig-v1|"
        self.assertIn(prefix, self.normalizer)
        self.assertIn(prefix, self.sql)
        self.assertNotIn("fnv1a64", self.normalizer)
        self.assertNotIn("MD5(", self.sql)
        self.assertIn("YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"", self.sql)
        self.assertIn("toFixed(8)", self.normalizer)

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
        self.assertIn("chooseOpenTradeCandidate", self.worker)
        self.assertIn("id=eq.", self.worker)
        self.assertNotIn("trades?position_id=eq.", self.worker)

    def test_explicit_candidate_metadata_mismatch_is_rejected(self) -> None:
        self.assertIn("modeMismatch", self.candidate)
        self.assertIn("variantMismatch", self.candidate)
        self.assertIn("if (modeMismatch || variantMismatch) return null", self.candidate)

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

    def test_operational_preflight_is_read_only(self) -> None:
        upper = self.preflight.upper()
        self.assertIn("BEGIN;", upper)
        self.assertIn("SET TRANSACTION READ ONLY", upper)
        self.assertIn("ROLLBACK;", upper)
        self.assertNotRegex(
            upper,
            r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|CREATE|TRUNCATE)\b",
        )
        self.assertIn("duplicate_open_trade_identity_inventory", self.preflight)

    def test_post_migration_validation_is_read_only(self) -> None:
        upper = self.validation.upper()
        self.assertIn("BEGIN;", upper)
        self.assertIn("SET TRANSACTION READ ONLY", upper)
        self.assertIn("ROLLBACK;", upper)
        self.assertNotRegex(
            upper,
            r"\b(INSERT|UPDATE|DELETE|ALTER|DROP|CREATE|TRUNCATE)\b",
        )

    def test_post_migration_validation_covers_mandatory_gates(self) -> None:
        for check_name in (
            "required_columns",
            "required_indexes",
            "decision_constraint_contract",
            "shadow_entry_not_error",
            "v4430_trade_execution_mode",
            "signal_eval_id_backfill",
            "legacy_ticket_not_invented_as_order",
        ):
            self.assertIn(f"'{check_name}'", self.validation)
        self.assertIn("violation_count", self.validation)
        self.assertIn("THEN 'PASS' ELSE 'FAIL'", self.validation)

    def test_post_migration_validation_includes_reconciliation_inventory(self) -> None:
        for check_name in (
            "signal_eval_id_prefix_inventory",
            "duplicate_signal_eval_id_inventory",
            "trade_link_status_inventory",
            "signal_decision_inventory",
            "execution_mode_inventory",
            "row_count_snapshot",
        ):
            self.assertIn(f"'{check_name}'", self.validation)


if __name__ == "__main__":
    unittest.main()
