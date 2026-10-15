# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Split a delimited list into tokens, and remove repeats."""

from __future__ import annotations

import re
from collections.abc import Iterable

SEPARATORS = re.compile(r"[,\s]+")


def split(text: str) -> list[str]:
    """Split on commas and any whitespace, dropping empty tokens."""
    return [token for token in SEPARATORS.split(text) if token]


def dedupe(tokens: Iterable[str], ignore_case: bool) -> list[str]:
    """Keep the first occurrence of each token, in the order given."""
    seen: set[str] = set()
    kept: list[str] = []
    for token in tokens:
        key = token.casefold() if ignore_case else token
        if key not in seen:
            seen.add(key)
            kept.append(token)
    return kept
