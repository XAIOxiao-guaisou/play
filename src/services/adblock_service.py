"""Adblock Service - request blocking based on Adblock rules.

Provides request interception and blocking based on standard Adblock format rules.
Rules can be loaded from environment variable ADBLOCK_RULES_PATH.

Note:
    - No default rules are bundled (to minimize overhead).
    - If adblockparser is not installed or no rules file is provided,
      the service gracefully degrades to pass-through mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class AdblockRules:
    """Adblock rules loader and matcher.

    Attributes:
        rules_path: Path to the Adblock rules file.
        _rules: Loaded rule object (cached after first load).
    """

    rules_path: Optional[Path] = None
    _rules: Optional[object] = None

    def load(self) -> None:
        """Load Adblock rules from file if not already loaded.

        Automatically handles missing adblockparser library and
        invalid/missing rule files by degrading gracefully.
        """
        if self._rules is not None:
            return

        if not self.rules_path or not self.rules_path.exists():
            self._rules = None
            return

        try:
            from adblockparser import AdblockRules as _AdblockRules  # type: ignore
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Adblock] adblockparser not installed, skipping: {exc}")
            self._rules = None
            return

        lines = []
        try:
            with self.rules_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("!"):
                        continue
                    lines.append(line)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[Adblock] Rules file read failed, skipping: {exc}")
            self._rules = None
            return

        if not lines:
            self._rules = None
            return

        self._rules = _AdblockRules(lines)
        logger.info("Adblock service for request filtering.")

    @staticmethod
    def from_env() -> AdblockRules:
        """Create AdblockRules instance from environment configuration.

        Reads ADBLOCK_RULES_PATH environment variable to locate rules file.

        Returns:
            AdblockRules instance (rules_path may be None if not configured).
        """
    def should_block(self, url: str) -> bool:
        """Check if a URL should be blocked according to loaded rules.

        Args:
            url: The URL to check.

        Returns:
            True if the URL matches a blocking rule, False otherwise.
        """
        self.load()
        if not self._rules:
            return False
        try:
            return bool(self._rules.should_block(url))
        except Exception:
            return False


class AdblockService:
    @staticmethod
    def from_env() -> AdblockRules:
        raw = os.getenv("ADBLOCK_RULES_PATH", "").strip()
        if not raw:
            return AdblockRules(rules_path=None)
        return AdblockRules(rules_path=Path(raw))
