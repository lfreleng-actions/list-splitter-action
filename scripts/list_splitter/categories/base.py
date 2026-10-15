# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""What every validate mode provides, and the error a refusal raises."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class InvalidItem(Exception):
    """Why a token is not an item of the selected category."""


class Category(ABC):
    """One validate mode: what an item looks like, and how GitHub compares it."""

    # Spellings the validate input accepts; the first is the canonical one.
    names: ClassVar[tuple[str, ...]]
    # Whether GitHub compares items without regard to case; the
    # ignore-case input follows this when set to auto.
    ignore_case: ClassVar[bool]

    @abstractmethod
    def parse(self, token: str) -> str:
        """Return the item a token names, or raise InvalidItem saying why not."""
