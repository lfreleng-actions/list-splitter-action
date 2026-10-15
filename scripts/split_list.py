# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Entry point that action.yaml runs with the runner's python3.

The inputs arrive in the environment as SPLIT_* variables and the
outputs go to $GITHUB_OUTPUT. The list_splitter package beside this
script holds the implementation; python3 puts the script's directory
on sys.path, so the package needs no installing.
"""

from __future__ import annotations

import os
import sys

from list_splitter.action import main

if __name__ == "__main__":
    sys.exit(main(os.environ))
