import unittest
from datetime import datetime, timezone

import job_radar


class JobRadarTests(unittest.TestCase):
    def test_parse_iso_utc(self):
        parsed = job_radar.parse_datetime("2026-11-25T10:00:00Z")
        self.assertEqual(parsed, datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc))

    def test_parse_epoch_ms(self):
        parsed = job_radar.parse_datetime(1795600800000)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_relative_dates_are_not_invented(self):
        self.assertIsNone(job_radar.parse_datetime("Posted 2 days ago"))

    def test_keyword_score_prefers_matching_role(self):
        job = {
            "title": "GRC Automation Engineer",
            "location": "Remote - India",
            "description": "FedRAMP NIST 800-53 Python API integrations TPRM ISO 27001 SOC 2 evidence workflows AWS compliance",
        }
        result = job_radar.local_score(job, job_radar.DEFAULT_PROFILE)
        self.assertGreaterEqual(result["fit_score"], 70)

    def test_nonmatching_role_scores_lower(self):
        job = {"title": "Frontend Designer", "location": "New York", "description": "CSS and visual design"}
        result = job_radar.local_score(job, job_radar.DEFAULT_PROFILE)
        self.assertLess(result["fit_score"], 30)


if __name__ == "__main__":
    unittest.main()
