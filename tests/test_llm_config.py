import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from code_review_multiagent.llm_client import openai_base_url, use_openai_compatible
from code_review_multiagent.llm_config import LLMConfig


class LLMConfigTests(unittest.TestCase):
    def test_openai_base_url_adds_v1_for_newapi(self):
        cfg = LLMConfig(provider="newapi", api_key="x", base_url="http://example.com", model="m")
        self.assertEqual(openai_base_url(cfg), "http://example.com/v1")

    def test_openai_base_url_adds_v1_for_deepseek(self):
        cfg = LLMConfig(provider="deepseek", api_key="x", base_url="https://api.deepseek.com", model="m")
        self.assertEqual(openai_base_url(cfg), "https://api.deepseek.com/v1")

    def test_claude_is_anthropic_compatible_even_with_base_url(self):
        cfg = LLMConfig(provider="claude", api_key="x", base_url="http://127.0.0.1:8990", model="m")
        self.assertFalse(use_openai_compatible(cfg))


if __name__ == "__main__":
    unittest.main()
