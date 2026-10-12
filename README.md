<!--
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# ✂️ List Splitter

<!-- prettier-ignore-start -->
<!-- markdownlint-disable-next-line MD013 -->
[![Linux Foundation](https://img.shields.io/badge/Linux-Foundation-blue)](https://linuxfoundation.org/) [![Source Code](https://img.shields.io/badge/GitHub-100000?logo=github&logoColor=white&color=blue)](https://github.com/lfreleng-actions/list-splitter-action) [![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0) [![pre-commit.ci status badge]][pre-commit.ci results page] [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/lfreleng-actions/list-splitter-action/badge)](https://scorecard.dev/viewer/?uri=github.com/lfreleng-actions/list-splitter-action)
<!-- prettier-ignore-end -->

Splits a list typed into a workflow input into separate items, so that
every workflow in the organisation reads lists the same way. Separate
items with commas, spaces, tabs or newlines, in any mix:

```text
repo-a, repo-b repo-c
```

The action removes repeats, optionally checks each item, and publishes
the result as a JSON array, a comma-joined string, one item per line,
and a count.

## Usage Example

Run one matrix job per repository named in a `workflow_dispatch` input:

<!-- markdownlint-disable MD046 -->

```yaml
on:
  workflow_dispatch:
    inputs:
      repositories:
        description: 'Repositories (commas and/or spaces); blank for all'
        type: string
        default: ''

jobs:
  select:
    runs-on: ubuntu-latest
    outputs:
      repositories: ${{ steps.split.outputs.json }}
      count: ${{ steps.split.outputs.count }}
    steps:
      - name: "Split repository list"
        id: split
        uses: lfreleng-actions/list-splitter-action@<commit-sha>  # vX.Y.Z
        with:
          list: ${{ inputs.repositories }}
          validate: "repository"

  scan:
    needs: select
    if: needs.select.outputs.count != '0'
    runs-on: ubuntu-latest
    strategy:
      matrix:
        repository: ${{ fromJSON(needs.select.outputs.repositories) }}
    steps:
      - run: echo "Scanning ${{ matrix.repository }}"
```

Scope a GitHub App token to the named repositories, which
`actions/create-github-app-token` takes as a comma-joined list:

```yaml
      - name: "Mint token for the named repositories"
        uses: actions/create-github-app-token@<commit-sha>
        with:
          client-id: ${{ vars.APP_CLIENT_ID }}
          private-key: ${{ secrets.APP_PRIVATE_KEY }}
          owner: ${{ github.repository_owner }}
          repositories: ${{ steps.split.outputs.csv }}
```

Read glob patterns into a shell array, without validation:

```yaml
      - name: "Split include patterns"
        id: include
        uses: lfreleng-actions/list-splitter-action@<commit-sha>  # vX.Y.Z
        with:
          list: ${{ inputs.extra-include }}

      - name: "Use the patterns"
        shell: bash
        env:
          PATTERNS: ${{ steps.include.outputs.lines }}
        run: |
          mapfile -t patterns <<< "$PATTERNS"
```

`mapfile` reads empty `lines` output as one empty element, so check
`count` first, or skip empty entries.

<!-- markdownlint-enable MD046 -->

## Inputs

<!-- markdownlint-disable MD013 -->

| Name        | Required | Default | Description                                                                              |
| ----------- | -------- | ------- | ---------------------------------------------------------------------------------------- |
| list        | False    | `""`    | Items separated by commas, spaces, tabs or newlines; blank gives no items                |
| validate    | False    | `none`  | Item check: `none` accepts anything; `repository` accepts bare repository names alone    |
| ignore-case | False    | `auto`  | Treat items differing in case alone as repeats: `auto`, `true` or `false`                |

<!-- markdownlint-enable MD013 -->

## Outputs

<!-- markdownlint-disable MD013 -->

| Name  | Example               | Description                                 |
| ----- | --------------------- | ------------------------------------------- |
| json  | `["repo-a","repo-b"]` | JSON array of the items, in the order given |
| csv   | `repo-a,repo-b`       | Items joined by commas                      |
| lines | `repo-a`⏎`repo-b`     | Items one per line                          |
| count | `2`                   | Number of items                             |

<!-- markdownlint-enable MD013 -->

## Implementation Details

The action runs `scripts/split_list.py` with the runner's `python3`.
It makes no network calls and needs no token, so a trusted job can run
it before minting any credential.

- **Splitting.** Any run of commas and whitespace separates two items.
  Input holding separators alone yields no items, as a blank input
  does, so a caller can treat `count` of `0` as "no selection".
- **Repeats.** The action keeps the first occurrence of each item, in
  the order given. With `ignore-case` the comparison ignores case but
  the first spelling survives: `Repo-A, repo-a` gives `["Repo-A"]`.
  `auto` ignores case for `repository`, since GitHub treats repository
  names that way, and compares case for `none`, since globs and
  other tokens may be case-sensitive.
- **Validation.** `repository` accepts ASCII letters, digits, `.`, `-`
  and `_`, up to 100 characters, refusing `.` and `..`. An item
  carrying an owner (`org/repo`) gets its own message, since that is
  the likeliest mistake. The action reports every invalid item as an
  error annotation before failing, so one corrected re-run fixes every
  mistake in a list, and it publishes no outputs on failure.
- **Output safety.** Outputs go to `$GITHUB_OUTPUT` in the heredoc
  form under a random delimiter, so no item can forge a further key,
  and the log line naming the items never lets an item open a line,
  where the runner would read it as a workflow command.

New validation modes extend the `VALIDATORS` table in the script; a
mode GitHub compares without regard to case joins
`CASE_INSENSITIVE_MODES` too.

## Notes

The action needs `python3` on the runner: GitHub-hosted Linux and macOS
images provide it. Run the tests locally with:

```bash
python3 -B -m unittest discover -s tests
```

[pre-commit.ci results page]: https://results.pre-commit.ci/latest/github/lfreleng-actions/list-splitter-action/main
[pre-commit.ci status badge]: https://results.pre-commit.ci/badge/github/lfreleng-actions/list-splitter-action/main.svg
