# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""A stand-in for GitHub's GraphQL endpoint, shared by the tests.

FakeGitHub answers the queries list_splitter.graphql renders the way
GitHub does: each aliased lookup reads its variables, walks a table of
known objects, and resolves to an object or to null with a NOT_FOUND
error. It records every query, and how many ran at once.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any

# One rendered lookup: the alias, then each field on its path with
# the variables it takes, then the selection.
FIELD = re.compile(r"(\w+)\((.*?)\) \{")
VARIABLE = re.compile(r"(\w+): \$(\w+)")


class FakeGitHub:
    """Answers lookups from tables of repositories, numbered items and accounts."""

    def __init__(self, delay: float = 0.0) -> None:
        """Start with no objects; ``delay`` holds each reply, to overlap queries."""
        # (owner, repo) in lower case -> repository node
        self.repositories: dict[tuple[str, str], dict[str, Any]] = {}
        # (owner, repo, number) in lower case -> issue or pull request node
        self.numbered: dict[tuple[str, str, int], dict[str, Any]] = {}
        # login in lower case -> account node
        self.accounts: dict[str, dict[str, Any]] = {}
        self.queries: list[dict[str, Any]] = []
        self.delay = delay
        self.running = 0
        self.peak = 0
        self.lock = threading.Lock()

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Answer one query, as the transport would deliver GitHub's reply."""
        with self.lock:
            self.queries.append(payload)
            self.running += 1
            self.peak = max(self.peak, self.running)
        try:
            time.sleep(self.delay)
            return self.answer(payload["query"], payload["variables"])
        finally:
            with self.lock:
                self.running -= 1

    def answer(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Resolve each aliased lookup of a query."""
        data: dict[str, Any] = {}
        errors: list[dict[str, Any]] = []
        body = query[query.index("{") + 1 :]
        for alias, rest in re.findall(r"(l\d+): (.*?)(?= l\d+: |\s*\}\s*$)", body):
            path = [
                (name, {arg: variables[var] for arg, var in VARIABLE.findall(args)})
                for name, args in FIELD.findall(rest)
            ]
            data[alias] = self.resolve(path)
            # GitHub reports a missing repository or number as an error
            # too, but a missing account as a bare null.
            missing_inside = (
                isinstance(data[alias], dict)
                and data[alias].get("issueOrPullRequest", 0) is None
            )
            if path[0][0] != "repositoryOwner" and (
                data[alias] is None or missing_inside
            ):
                errors.append(
                    {"type": "NOT_FOUND", "path": [alias], "message": "absent"}
                )
        reply: dict[str, Any] = {"data": data}
        if errors:
            reply["errors"] = errors
        return reply

    def resolve(self, path: list[tuple[str, dict[str, Any]]]) -> dict[str, Any] | None:
        """Walk one lookup's path through the tables."""
        (field, arguments), *inner = path
        if field == "repositoryOwner":
            return self.accounts.get(str(arguments["login"]).lower())
        key = (str(arguments["owner"]).lower(), str(arguments["name"]).lower())
        repository = self.repositories.get(key)
        if repository is None or not inner:
            return repository
        number = int(inner[0][1]["number"])
        return {"issueOrPullRequest": self.numbered.get((*key, number))}

    def add_repository(self, owner: str, name: str, **extra: Any) -> None:
        """Hold a repository, as GraphQL describes one."""
        node = {
            "nameWithOwner": f"{owner}/{name}",
            "url": f"https://github.com/{owner}/{name}",
            "isArchived": False,
            "isFork": False,
            "isTemplate": False,
            "isDisabled": False,
            "isPrivate": False,
            "visibility": "PUBLIC",
            "defaultBranchRef": {"name": "main"},
        }
        node.update(extra)
        self.repositories[(owner.lower(), name.lower())] = node

    def add_numbered(
        self, owner: str, name: str, number: int, typename: str, **extra: Any
    ) -> None:
        """Hold an issue or pull request, creating its repository if new."""
        if (owner.lower(), name.lower()) not in self.repositories:
            self.add_repository(owner, name)
        segment = "pull" if typename == "PullRequest" else "issues"
        node = {
            "__typename": typename,
            "number": number,
            "url": f"https://github.com/{owner}/{name}/{segment}/{number}",
            "state": "OPEN",
            "isDraft": False,
            "repository": {"nameWithOwner": f"{owner}/{name}"},
        }
        node.update(extra)
        self.numbered[(owner.lower(), name.lower(), number)] = node

    def add_account(self, login: str, typename: str) -> None:
        """Hold an organisation or user."""
        self.accounts[login.lower()] = {
            "__typename": typename,
            "url": f"https://github.com/{login}",
        }
