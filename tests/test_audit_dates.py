"""Official chart publication may lag the live PE observation; never lead it."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_snapshot import check_history_date


class AuditDateTests(unittest.TestCase):
    def test_real_one_day_provider_lag_is_reported_without_rewriting_dates(self):
        self.assertEqual(check_history_date("2026-10-29","2026-10-30"),1)

    def test_future_or_outdated_chart_cannot_be_published(self):
        for history in ("2026-10-31","2026-10-20"):
            with self.assertRaises(ValueError):check_history_date(history,"2026-10-30")


if __name__=="__main__":unittest.main()
