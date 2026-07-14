from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from python.research.stage10d_governed_manifest import (
    build_governed_manifest_bundle,
    write_governed_manifest_bundle,
)


class Stage10DGovernedManifestTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def write_csv(self, name: str, rows: list[str]) -> Path:
        path = self.root / name
        path.write_text(
            "TIME,OPEN,HIGH,LOW,CLOSE,TICK_VOLUME\n" + "\n".join(rows) + "\n",
            encoding="utf-8",
        )
        return path

    def write_json(self, name: str, payload: dict[str, object]) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return path

    def policy(self, *, classification: str) -> Path:
        return self.write_json(
            "policy.json",
            {
                "policy_version": "stage10d-gap-governance-v1",
                "symbol": "USDJPY",
                "rules": [
                    {
                        "rule_id": "test-gap",
                        "timeframe": "H4",
                        "previous_time": "2026-07-06 04:00:00",
                        "current_time": "2026-07-06 12:00:00",
                        "classification": classification,
                        "action": "BLOCK_FINAL_MANIFEST",
                        "rationale": "test gap",
                    }
                ],
            },
        )

    def profile(self, *, allowed_version: str = "stage10d-gap-governance-v1") -> Path:
        return self.write_json(
            "profile.json",
            {
                "profile_version": "stage10d-feed-profile-v1",
                "symbol": "USDJPY",
                "broker_company": "MetaQuotes Ltd.",
                "account_server": "MetaQuotes-Demo",
                "terminal_environment": "mt5-macos-wine",
                "server_time_observation": {
                    "observed_at_utc": "2026-07-14T01:00:29Z",
                    "offset": "UTC+03:00",
                },
                "historical_offset_policy": "Do not infer a fixed historical offset.",
                "calendar_confirmation": {
                    "mode": "PROMOTE_EXACT_ENUMERATED_PENDING_RULES",
                    "allowed_policy_versions": [allowed_version],
                },
            },
        )

    def h4_csv(self) -> Path:
        return self.write_csv(
            "USDJPY_H4.csv",
            [
                "2026-07-06 00:00:00,150,151,149,150.5,100",
                "2026-07-06 04:00:00,150.5,151.5,150,151,110",
                "2026-07-06 12:00:00,151,152,150.5,151.5,120",
                "2026-07-06 16:00:00,151.5,152.5,151,152,130",
            ],
        )

    def test_exact_session_gap_builds_research_eligible_manifest(self):
        bundle = build_governed_manifest_bundle(
            self.h4_csv(),
            policy_path=self.policy(
                classification="PENDING_BROKER_CALENDAR_CONFIRMATION"
            ),
            feed_profile_path=self.profile(),
            symbol="USDJPY",
            timeframe="H4",
        )
        manifest = bundle.manifest
        self.assertEqual(manifest.raw_quality_status, "FAIL")
        self.assertEqual(
            manifest.governance_status,
            "PASS_WITH_CONFIRMED_SESSION_CLOSURES",
        )
        self.assertTrue(manifest.research_eligible)
        self.assertEqual(manifest.confirmed_session_gap_count, 1)
        self.assertEqual(manifest.governed_data_gap_count, 0)
        self.assertEqual(manifest.excluded_bar_times, ())
        self.assertFalse(manifest.synthetic)
        self.assertIn("MetaQuotes-Demo broker-server wall-clock", manifest.timestamp_semantics)

    def test_governed_data_gap_records_exact_excluded_bar(self):
        bundle = build_governed_manifest_bundle(
            self.h4_csv(),
            policy_path=self.policy(classification="GOVERNED_DATA_GAP"),
            feed_profile_path=self.profile(),
            symbol="USDJPY",
            timeframe="H4",
        )
        self.assertEqual(
            bundle.manifest.governance_status,
            "PASS_WITH_GOVERNED_EXCLUSIONS",
        )
        self.assertEqual(bundle.manifest.excluded_bar_times, ("2026-07-06 08:00:00",))

    def test_manifest_identity_is_deterministic(self):
        csv_path = self.h4_csv()
        policy_path = self.policy(
            classification="PENDING_BROKER_CALENDAR_CONFIRMATION"
        )
        profile_path = self.profile()
        first = build_governed_manifest_bundle(
            csv_path,
            policy_path=policy_path,
            feed_profile_path=profile_path,
            symbol="USDJPY",
            timeframe="H4",
        )
        second = build_governed_manifest_bundle(
            csv_path,
            policy_path=policy_path,
            feed_profile_path=profile_path,
            symbol="USDJPY",
            timeframe="H4",
        )
        self.assertEqual(
            first.manifest.governed_manifest_id,
            second.manifest.governed_manifest_id,
        )

    def test_unverified_policy_version_blocks_research(self):
        bundle = build_governed_manifest_bundle(
            self.h4_csv(),
            policy_path=self.policy(
                classification="PENDING_BROKER_CALENDAR_CONFIRMATION"
            ),
            feed_profile_path=self.profile(allowed_version="another-policy"),
            symbol="USDJPY",
            timeframe="H4",
        )
        self.assertEqual(bundle.manifest.governance_status, "PENDING_BROKER_CALENDAR")
        self.assertFalse(bundle.manifest.research_eligible)

    def test_m15_is_explicitly_partial_path_coverage(self):
        csv_path = self.write_csv(
            "USDJPY_M15.csv",
            [
                "2026-07-13 00:00:00,150,151,149,150.5,100",
                "2026-07-13 00:15:00,150.5,151,150,150.8,110",
            ],
        )
        policy_path = self.write_json(
            "m15-policy.json",
            {
                "policy_version": "stage10d-gap-governance-v1",
                "symbol": "USDJPY",
                "rules": [],
            },
        )
        bundle = build_governed_manifest_bundle(
            csv_path,
            policy_path=policy_path,
            feed_profile_path=self.profile(),
            symbol="USDJPY",
            timeframe="M15",
        )
        self.assertEqual(
            bundle.manifest.coverage_classification,
            "PARTIAL_INTRABAR_PATH_COVERAGE",
        )
        self.assertTrue(bundle.manifest.research_eligible)

    def test_writer_emits_all_audit_artifacts(self):
        bundle = build_governed_manifest_bundle(
            self.h4_csv(),
            policy_path=self.policy(classification="GOVERNED_DATA_GAP"),
            feed_profile_path=self.profile(),
            symbol="USDJPY",
            timeframe="H4",
        )
        outputs = write_governed_manifest_bundle(bundle, self.root / "out")
        self.assertEqual(
            set(outputs),
            {"governed_manifest", "raw_manifest", "raw_quality", "gap_governance"},
        )
        self.assertTrue(all(path.exists() for path in outputs.values()))


if __name__ == "__main__":
    unittest.main()
