"""
Unit tests for LLMInvestigationAgent and SigNozMCPAdapter API key and credential validation.
"""

import os
import unittest
from unittest.mock import patch, MagicMock

from src.llm_agent import LLMInvestigationAgent
from src.signoz_mcp_adapter import SigNozMCPAdapter


class TestLLMAgentAPIKeyValidation(unittest.TestCase):
    """Tests for GEMINI_API_KEY validation in LLMInvestigationAgent."""

    @patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=True)
    def test_missing_gemini_api_key_raises_value_error(self):
        """Verify that initializing LLMInvestigationAgent without GEMINI_API_KEY raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            LLMInvestigationAgent(api_key="")
        self.assertIn("GEMINI_API_KEY is not set", str(ctx.exception))

    @patch("src.llm_agent.genai.Client")
    def test_valid_gemini_api_key_initializes_client(self, mock_genai_client):
        """Verify that providing a valid GEMINI_API_KEY initializes genai.Client."""
        agent = LLMInvestigationAgent(api_key="test-gemini-key")
        mock_genai_client.assert_called_once_with(api_key="test-gemini-key")
        self.assertEqual(agent.model, "gemini-2.5-flash")


class TestSigNozAdapterAuthValidation(unittest.TestCase):
    """Tests for SigNoz MCP credentials validation."""

    def test_missing_all_credentials_raises_runtime_error(self):
        """Verify that calling auth headers with no API key or login creds raises RuntimeError."""
        adapter = SigNozMCPAdapter(api_key="", email="", password="", org_id="")
        with self.assertRaises(RuntimeError) as ctx:
            adapter._auth_headers()
        self.assertIn("No SigNoz MCP credentials configured", str(ctx.exception))

    def test_api_key_header_formatting(self):
        """Verify SIGNOZ-API-KEY header formatting when API key is set."""
        adapter = SigNozMCPAdapter(api_key="my-signoz-key")
        headers = adapter._auth_headers()
        self.assertEqual(headers, {"SIGNOZ-API-KEY": "my-signoz-key"})


if __name__ == "__main__":
    unittest.main()
