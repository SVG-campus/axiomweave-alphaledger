from __future__ import annotations

from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class DashboardSmokeTests(unittest.TestCase):
    def test_dashboard_renders_public_competition_controls(self) -> None:
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=45)

        app.run()

        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Proof before profit")
        self.assertEqual(
            [tab.label for tab in app.tabs],
            [
                "Competition control",
                "Options agent",
                "Evidence ledger",
                "Evaluation readiness",
                "Equity baseline",
                "Replay & controls",
                "AxiomWeave packet",
            ],
        )
        metric_labels = {metric.label for metric in app.metric}
        self.assertTrue(
            {"Current phase", "New entries", "Max plan loss", "Default flat"}
            <= metric_labels
        )
        self.assertTrue(any(item.value == "PROMOTION: REFUSED" for item in app.error))
        visible_text = "\n".join(
            item.value
            for collection in (app.markdown, app.caption)
            for item in collection
        )
        self.assertIn("paper-order payload but never sends it", visible_text)
