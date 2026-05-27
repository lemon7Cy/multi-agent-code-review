import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_review_multiagent.agents import build_default_agents
from code_review_multiagent.models import ReviewFile


class TestCoverageAgentTests(unittest.TestCase):
    def test_default_agents_include_test_coverage_agent(self):
        names = [agent.name for agent in build_default_agents()]
        self.assertIn("Test Coverage Agent", names)

    def test_flags_production_change_without_matching_test_change(self):
        agent = next(agent for agent in build_default_agents() if agent.name == "Test Coverage Agent")
        review = agent.review(
            [
                ReviewFile(path="src/billing.py", content="def calculate_total(x):\n    return x * 2\n"),
                ReviewFile(path="README.md", content="docs"),
            ]
        )

        rule_ids = {finding.rule_id for finding in review.findings}
        self.assertIn("TEST-MISSING-COVERAGE", rule_ids)
        finding = review.findings[0]
        self.assertEqual(finding.file_path, "src/billing.py")
        self.assertEqual(finding.severity.value, "Medium")

    def test_accepts_matching_test_file(self):
        agent = next(agent for agent in build_default_agents() if agent.name == "Test Coverage Agent")
        review = agent.review(
            [
                ReviewFile(path="src/billing.py", content="def calculate_total(x):\n    return x * 2\n"),
                ReviewFile(path="tests/test_billing.py", content="def test_calculate_total():\n    assert True\n"),
            ]
        )

        self.assertEqual(review.findings, [])
        self.assertTrue(any("覆盖" in note or "测试" in note for note in review.notes))


if __name__ == "__main__":
    unittest.main()
