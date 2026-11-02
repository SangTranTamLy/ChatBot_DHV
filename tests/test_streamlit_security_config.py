from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StreamlitSecurityConfigTests(unittest.TestCase):
    def test_streamlit_server_is_bound_to_loopback_only(self) -> None:
        config_path = PROJECT_ROOT / ".streamlit" / "config.toml"
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(config.get("server", {}).get("address"), "127.0.0.1")
