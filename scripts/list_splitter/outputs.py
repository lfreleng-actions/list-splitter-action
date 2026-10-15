# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Render the outputs, and publish them and any error to the runner."""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping


def build_outputs(items: list[str]) -> dict[str, str]:
    """Render the items in each output format the action publishes."""
    return {
        "json": json.dumps(items, ensure_ascii=False, separators=(",", ":")),
        "csv": ",".join(items),
        "lines": "\n".join(items),
        "count": str(len(items)),
    }


def write_outputs(path: str, outputs: Mapping[str, str]) -> None:
    """Append outputs in the heredoc form, under a delimiter absent from each value.

    The heredoc form keeps a value from injecting further keys into
    the output file, whatever it holds.
    """
    with open(path, "a", encoding="utf-8") as sink:
        for name, value in outputs.items():
            delimiter = f"ghadelim_{secrets.token_hex(16)}"
            while delimiter in value:
                delimiter = f"ghadelim_{secrets.token_hex(16)}"
            sink.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")


def escape_command(text: str) -> str:
    """Escape text for the message of a workflow command."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def report_error(message: str) -> None:
    """Print an error annotation, escaped so that it stays one command."""
    print(f"::error::{escape_command(message)}")
