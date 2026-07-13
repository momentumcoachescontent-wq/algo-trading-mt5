import unittest

from python.pipeline.replay_stage10d_phase1_contract import run_replay


class ReplayStage10DPhase1Tests(unittest.TestCase):
    def test_july_8_recorded_candidates_are_blocked(self):
        result = run_replay()
        self.assertTrue(result["pass"])
        self.assertEqual(result["events_total"], 2)
        self.assertEqual(result["events_passed"], 2)
        self.assertEqual(result["defective_promotions_prevented"], 2)
        for row in result["events"]:
            self.assertEqual(row["raw_h4_signal"], 1)
            self.assertEqual(row["discrete_bias"], 0)
            self.assertEqual(row["v4431_filtered_signal"], 0)


if __name__ == "__main__":
    unittest.main()
