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

The action removes repeats, optionally checks each item as a GitHub
repository, issue, pull request, organisation or user, and publishes
the result as a JSON array, a comma-joined string, one item per line,
and a count, with the repositories the items name and a description of
each item.

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

With `owner` set, that action reads an empty list as every repository
the App can reach. A blank input then mints a token for the whole
organisation, which suits a workflow where blank means "scan them
all". Where it must not, guard the step with
`if: steps.split.outputs.count != '0'`.

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

Review named pull requests, with a token scoped to the repositories
they live in. Each item publishes as `owner/repo#N`, whichever spelling
the operator typed, and `details` carries its parts for a matrix:

```yaml
      - name: "Split pull request list"
        id: pulls
        uses: lfreleng-actions/list-splitter-action@<commit-sha>  # vX.Y.Z
        with:
          # For example: repo-a#12, other-repo/pull/3 and the URL of a
          # pull request in this organisation
          list: ${{ inputs.pull_requests }}
          validate: "pull-request"
          owner: ${{ github.repository_owner }}

      - name: "Mint token for those repositories"
        # An empty list would scope the token to every repository.
        if: steps.pulls.outputs.count != '0'
        uses: actions/create-github-app-token@<commit-sha>
        with:
          client-id: ${{ vars.APP_CLIENT_ID }}
          private-key: ${{ secrets.APP_PRIVATE_KEY }}
          owner: ${{ github.repository_owner }}
          repositories: ${{ steps.pulls.outputs.repositories }}
```

A matrix over `fromJSON(steps.pulls.outputs.details)` then reads
`matrix.repo` and `matrix.number` for each pull request.

Confirm named repositories exist before scanning them, reading each
one's default branch and flags in the same step. One run checks the
whole list in concurrent GraphQL queries, in place of one REST call
per repository:

```yaml
      - name: "Verify the named repositories"
        id: named
        uses: lfreleng-actions/list-splitter-action@<commit-sha>  # vX.Y.Z
        with:
          list: ${{ inputs.repo }}
          validate: "repository"
          owner: ${{ inputs.org }}
          verify: "true"
          token: ${{ secrets.ORG_READ_TOKEN }}
```

Each `details` entry then carries `default_branch`, `archived`,
`fork`, `is_template`, `disabled`, `private` and `visibility`, named as
the REST API names them.

<!-- markdownlint-enable MD046 -->

## Inputs

<!-- markdownlint-disable MD013 -->

| Name        | Required | Default               | Description                                                                                 |
| ----------- | -------- | --------------------- | ------------------------------------------------------------------------------------------- |
| list        | False    | `""`                  | Items separated by commas, spaces, tabs or newlines; blank gives no items                   |
| validate    | False    | `none`                | Item check, from the [validate modes](#validate-modes) below                                |
| ignore-case | False    | `auto`                | Treat items differing in case alone as repeats: `auto`, `true` or `false`                   |
| owner       | False    | `""`                  | Owner the repositories, issues and pull requests belong to; blank uses the workflow's owner |
| verify      | False    | `false`               | Confirm each item exists on GitHub as its mode describes: `true` or `false`                 |
| token       | False    | `${{ github.token }}` | Token for `verify`, able to read the items; read for nothing else                           |

<!-- markdownlint-enable MD013 -->

## Validate Modes

<!-- markdownlint-disable MD013 -->

| Mode           | Accepts                                                                       | Publishes      |
| -------------- | ----------------------------------------------------------------------------- | -------------- |
| `none`         | Anything: globs, paths, free-form tokens                                      | The token      |
| `repository`   | A bare repository name, without its owner                                     | The name       |
| `issue`        | `repo#N`, `owner/repo#N`, `repo/issues/N`, `owner/repo/issues/N`, or its URL  | `owner/repo#N` |
| `pull-request` | `repo#N`, `owner/repo#N`, `repo/pull/N`, `owner/repo/pull/N`, or its URL      | `owner/repo#N` |
| `organisation` | An organisation name; `organization` selects this mode too                    | The name       |
| `user`         | A user name                                                                   | The name       |

<!-- markdownlint-enable MD013 -->

Repositories, issues and pull requests belong to the `owner` input,
which defaults to the owner of the repository running the workflow.
Short forms such as `repo#12` resolve against it, and the action
refuses a reference naming any other owner: a run holds a token for
one owner, and a typo must not reach a stranger's repository.

## Outputs

<!-- markdownlint-disable MD013 -->

| Name         | Example                                      | Description                                                     |
| ------------ | -------------------------------------------- | --------------------------------------------------------------- |
| json         | `["repo-a","repo-b"]`                        | JSON array of the items, in the order given                     |
| csv          | `repo-a,repo-b`                              | Items joined by commas                                          |
| lines        | `repo-a`⏎`repo-b`                            | Items one per line                                              |
| count        | `2`                                          | Number of items                                                 |
| repositories | `repo-a,repo-b`                              | Distinct repositories the items name, joined by commas          |
| details      | `[{"item":"o/repo-a#1","owner":"o",...}]`    | JSON array describing each item, in the order of `json`         |

<!-- markdownlint-enable MD013 -->

`repositories` holds bare names, as `actions/create-github-app-token`
takes them, and stays blank for an empty list and for modes naming no
repository. That action reads blank as every repository the App can
reach, so check `count` before minting a token that must stay narrow.
Each `details` entry holds the item as `item`, plus the fields of its
mode:

<!-- markdownlint-disable MD013 -->

| Mode                   | Fields                    | With `verify`                                                                                        |
| ---------------------- | ------------------------- | ---------------------------------------------------------------------------------------------------- |
| `none`                 | None beyond `item`        | Not available                                                                                        |
| `repository`           | `owner`, `repo`           | `html_url`, `default_branch`, `archived`, `fork`, `is_template`, `disabled`, `private`, `visibility` |
| `issue`                | `owner`, `repo`, `number` | `html_url`, `state`                                                                                  |
| `pull-request`         | `owner`, `repo`, `number` | `html_url`, `state`, `draft`                                                                         |
| `organisation`, `user` | `login`                   | `html_url`                                                                                           |

<!-- markdownlint-enable MD013 -->

`default_branch` is `null` for an empty repository. States read
`open` or `closed`, and `merged` for a merged pull request.

## Verification

With `verify: true` the action confirms every item on GitHub after the
offline checks, and refuses an item in these cases:

- GitHub holds nothing there, or nothing the token can see: a private
  repository the token cannot read looks the same as a missing one.
- The object is of the other kind: a pull request where the list named
  an issue, or a user where it named an organisation.
- The object has moved. GitHub follows a renamed or transferred
  repository, and a transferred issue, to its new place; the action
  names that place instead of acting on it unannounced, since it may
  belong to another owner.

The action checks every item that passed the offline checks, even
when others failed, so one run reports both kinds of mistake. When
GitHub cannot answer at all, the run fails with an error saying so,
after any offline refusals, and blames no item for it.

Verification reads through GitHub's GraphQL API at
`GITHUB_GRAPHQL_URL`, which GitHub Enterprise Server runners set to
their own server. A short list costs one round trip: lookups travel as
aliased fields, shared evenly among queries of 5 to 50 lookups that
run eight at a time, each charged one point of the GraphQL rate limit.
Measured against `api.github.com`, 50 repositories verify in under a
second and 120 in about one and a half. List values travel as query
variables, never in the query text, and the action follows no
redirect, so the token reaches the endpoint alone.

The default `github.token` reads public objects and the repository
running the workflow. To verify private repositories elsewhere in an
organisation, pass a token that can read them, such as an App token
from `actions/create-github-app-token` scoped to those repositories.
The step receives the token input whether or not `verify` is on, as
it does every input; the action reads it to verify and for nothing
else.

## Implementation Details

The action runs `scripts/split_list.py` with the runner's `python3`;
the `scripts/list_splitter` package beside it holds the implementation
and needs nothing beyond the standard library. Without `verify` it
makes no network calls and needs no token, so a trusted job can run it
before minting any credential.

- **Splitting.** Any run of commas and whitespace separates two items.
  Input holding separators alone yields no items, as a blank input
  does, so a caller can treat `count` of `0` as "no selection".
- **Repeats.** The action keeps the first occurrence of each item, in
  the order given. Spellings of one issue or pull request, such as
  `repo#12` and its URL, count as repeats too. With `ignore-case` the
  comparison ignores case but the first spelling survives:
  `Repo-A, repo-a` gives `["Repo-A"]`. `auto` ignores case for every
  mode naming something on GitHub, since GitHub treats those names
  that way, and compares case for `none`, since globs and other tokens
  may be case-sensitive.
- **Validation.** Each mode checks the structure of a name, as GitHub
  forms names. Repository names hold ASCII letters, digits, `.`, `-` and
  `_`, up to 100 characters, never `.` or `..`. Organisation and user
  names hold letters, digits, hyphens and the underscore of an
  enterprise managed user, up to 39 characters, never starting with a
  hyphen. Hyphen placement is otherwise free: GitHub's signup form
  refuses doubled or trailing hyphens, but real accounts such as
  `a--b--t` and `johan--` predate it, so the action does not refuse
  them. `verify` settles whether an account exists. Numbers must fit
  the 32-bit range GitHub stores them in. Each refusal names its
  reason: an owner on a bare repository name, a reference to another
  owner, or a pull request URL given as an issue. The action reports
  every invalid item as an error annotation before failing, so one
  corrected re-run fixes every mistake in a list, and it publishes no
  outputs on failure.
- **Output safety.** Outputs go to `$GITHUB_OUTPUT` in the heredoc
  form under a random delimiter, so no item can forge a further key,
  and the log line naming the items never lets an item open a line,
  where the runner would read it as a workflow command.

Each validate mode is a `Category` in the
`scripts/list_splitter/categories` package, one module per family of
modes, stating what a valid item looks like, the form it publishes,
and whether GitHub compares items without regard to case. A new mode
is one more class, added to `CATEGORIES` in the package's
`__init__.py`. A mode GitHub can confirm subclasses `Verifiable`
instead, adding where its object lives and how to check what GitHub
holds there; `scripts/list_splitter/graphql.py` batches, sends and
reads every lookup, whatever the mode. URL references follow
`GITHUB_SERVER_URL`, so on GitHub Enterprise Server they take that
server's address.

## Notes

The action needs `python3` on the runner: GitHub-hosted Linux and macOS
images provide it. Run the tests locally with:

```bash
python3 -B -m unittest discover -s tests
```

[pre-commit.ci results page]: https://results.pre-commit.ci/latest/github/lfreleng-actions/list-splitter-action/main
[pre-commit.ci status badge]: https://results.pre-commit.ci/badge/github/lfreleng-actions/list-splitter-action/main.svg
