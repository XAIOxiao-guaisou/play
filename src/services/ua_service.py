"""User-Agent Service - provides random User-Agent selection.

Supplies realistic User-Agent strings from a curated pool
to simulate various browsers and devices. Currently integrates
with config.FingerprintConfig for centralized UA management.
"""

from __future__ import annotations

import random

from config import FingerprintConfig


class UAService:
    """User-Agent service providing random agent selection."""

    @staticmethod
    def get_random() -> str:
        """Get a random User-Agent string from the configured pool.

        Returns:
            A randomly selected User-Agent string, or a default fallback.
        """
        fp = FingerprintConfig()
        if not fp.USER_AGENTS:
            return "Mozilla/5.0"
        return random.choice(fp.USER_AGENTS)
