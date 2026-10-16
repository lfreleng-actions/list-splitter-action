# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Split, deduplicate and validate the delimited lists of action inputs.

scripts/split_list.py is the entry point action.yaml runs. Each module
here owns one concern, so a new validate mode touches categories alone:

tokens
    splitting text into tokens and removing repeats
categories
    the validate modes, a registry of item categories, one module per
    family of modes
inputs
    reading and checking the action inputs
outputs
    rendering the outputs and publishing them to the runner
"""
