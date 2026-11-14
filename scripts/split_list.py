# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Entry point that action.yaml runs in isolated mode (python -I).

The inputs arrive in the environment as SPLIT_* variables and the
outputs go to $GITHUB_OUTPUT. The list_splitter package beside this
script holds the implementation. Isolated mode leaves the script's
directory off sys.path, so the script adds it, and the package needs
no installing.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from list_splitter.action import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(os.environ))
