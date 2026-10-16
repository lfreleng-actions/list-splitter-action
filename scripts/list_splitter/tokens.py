# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Split a delimited list into tokens, and remove repeats."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import TypeVar

SEPARATORS = re.compile(r"[,\s]+")
Entry = TypeVar("Entry")


def split(text: str) -> list[str]:
    """Split on commas and any whitespace, dropping empty tokens."""
    return [token for token in SEPARATORS.split(text) if token]


def dedupe(
    entries: Iterable[Entry], key: Callable[[Entry], str], ignore_case: bool
) -> list[Entry]:
    """Keep the first entry with each key, in the order given."""
    seen: set[str] = set()
    kept: list[Entry] = []
    for entry in entries:
        identity = key(entry).casefold() if ignore_case else key(entry)
        if identity not in seen:
            seen.add(identity)
            kept.append(entry)
    return kept
