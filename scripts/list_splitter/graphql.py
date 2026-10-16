# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Look objects up on GitHub in batched, concurrent GraphQL queries.

A Lookup names a path of fields from the query root, such as
repository(owner, name) then issueOrPullRequest(number), and the
fields to read where the path ends. Lookups travel as aliased fields,
shared evenly among up to MAX_CONCURRENT_QUERIES queries that run at
once, so a list of any length costs a few round trips, each charged
one point of the GraphQL rate limit. Values from the list travel as
variables, never in the query text, so no item can change what a
query asks.

GitHub answers a missing object with null and carries on with the
rest of the query, so one absent object fails its own lookup alone.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, TypeVar

# Measured against api.github.com: GitHub resolves the aliases of one
# query in turn, around 45 ms each for a repository, while separate
# queries run side by side. Spreading a list evenly across eight
# concurrent queries verified repositories two to three times faster
# than queries of fifty, and issues no slower. At least five lookups
# to a query keeps a short list to one or two round trips and rate
# limit points; fifty bounds how long any one query takes.
MIN_BATCH = 5
MAX_BATCH = 50
MAX_CONCURRENT_QUERIES = 8
ATTEMPTS = 3
TIMEOUT_SECONDS = 30
RETRY_STATUSES = frozenset({500, 502, 503, 504})
USER_AGENT = "lfreleng-actions/list-splitter-action"


class GitHubError(Exception):
    """GitHub could not answer: the network, the token or the service failed."""


class TransientError(Exception):
    """A failure that another attempt may not meet."""


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Turn every redirect into an error reply.

    urllib would follow one with the token attached, to any host and
    over plain HTTP, and hand back whatever the new place answers.
    GitHub's GraphQL endpoint does not redirect.
    """

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        """Follow nothing; urllib then raises the redirect as HTTPError."""
        return None


OPENER = urllib.request.build_opener(RefuseRedirects)


@dataclass(frozen=True)
class Argument:
    """One argument of a field, sent as a variable."""

    name: str
    # The variable's GraphQL type, such as String! or Int!.
    type: str
    value: str | int


@dataclass(frozen=True)
class Step:
    """One field on the path to an object."""

    field: str
    arguments: tuple[Argument, ...]
    # Why the lookup fails when this field resolves to nothing.
    missing: str


@dataclass(frozen=True)
class Lookup:
    """The path to one object, and the fields to read from it."""

    path: tuple[Step, ...]
    selection: str


@dataclass(frozen=True)
class Found:
    """The object a lookup reached."""

    node: dict[str, Any]


@dataclass(frozen=True)
class Absent:
    """Why a lookup reached no object."""

    reason: str


Result = Found | Absent
Transport = Callable[[dict[str, Any]], dict[str, Any]]
Value = TypeVar("Value")


def alias(index: int) -> str:
    """The alias of a batch's index-th lookup in its query."""
    return f"l{index}"


def render(batch: Sequence[Lookup]) -> dict[str, Any]:
    """One query for a batch of lookups, every value a variable."""
    declarations: list[str] = []
    variables: dict[str, str | int] = {}
    fields: list[str] = []
    for index, lookup in enumerate(batch):
        calls: list[str] = []
        for depth, step in enumerate(lookup.path):
            arguments: list[str] = []
            for argument in step.arguments:
                name = f"v{index}_{depth}_{argument.name}"
                declarations.append(f"${name}: {argument.type}")
                variables[name] = argument.value
                arguments.append(f"{argument.name}: ${name}")
            calls.append(
                f"{step.field}({', '.join(arguments)})" if arguments else step.field
            )
        # Each field opens a selection the next one sits inside; the
        # selection's own braces close the innermost.
        opened = " { ".join(calls)
        closed = " }" * (len(calls) - 1)
        fields.append(f"{alias(index)}: {opened} {{ {lookup.selection} }}{closed}")
    signature = f"query({', '.join(declarations)})" if declarations else "query"
    return {"query": f"{signature} {{ {' '.join(fields)} }}", "variables": variables}


def walk(lookup: Lookup, node: Any) -> Result:
    """Follow a lookup's path through its part of the reply."""
    for depth, step in enumerate(lookup.path):
        if depth:
            node = node.get(step.field)
        if not isinstance(node, dict):
            return Absent(step.missing)
    return Found(node)


def interpret(batch: Sequence[Lookup], reply: Mapping[str, Any]) -> list[Result]:
    """Read each lookup's object from a query's reply, or why it has none.

    A NOT_FOUND error repeats what a null in the data already says. Any
    other error naming a lookup fails that lookup; an error naming none
    means GitHub refused the query as a whole.
    """
    errors = reply.get("errors") or []
    if not isinstance(errors, list):
        raise GitHubError("GitHub refused the query")
    aliases = {alias(index) for index in range(len(batch))}
    refusals: dict[str, str] = {}
    for error in errors:
        entry: dict[str, Any] = error if isinstance(error, dict) else {}
        message = str(entry.get("message", error))
        path = entry.get("path")
        where = path[0] if isinstance(path, list) and path else None
        if where not in aliases:
            raise GitHubError(f"GitHub refused the query: {message}")
        if entry.get("type") != "NOT_FOUND":
            refusals.setdefault(str(where), f"GitHub refused the lookup: {message}")
    data = reply.get("data")
    if not isinstance(data, dict):
        raise GitHubError("GitHub's reply carried no data")
    results: list[Result] = []
    for index, lookup in enumerate(batch):
        refusal = refusals.get(alias(index))
        results.append(
            Absent(refusal) if refusal else walk(lookup, data.get(alias(index)))
        )
    return results


async def send_all(
    payloads: Sequence[dict[str, Any]], transport: Transport
) -> list[dict[str, Any]]:
    """Send every query, at most MAX_CONCURRENT_QUERIES at once.

    Every query runs to its end before the first failure, if any, is
    raised, so none is left running unobserved.
    """
    loop = asyncio.get_running_loop()
    workers = min(MAX_CONCURRENT_QUERIES, len(payloads))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        replies = await asyncio.gather(
            *(loop.run_in_executor(pool, transport, payload) for payload in payloads),
            return_exceptions=True,
        )
    failures = [reply for reply in replies if isinstance(reply, BaseException)]
    if failures:
        raise failures[0]
    return [reply for reply in replies if not isinstance(reply, BaseException)]


def batch_sizes(count: int) -> list[int]:
    """How many lookups each query carries, for a list of count lookups."""
    if not count:
        return []
    queries = max(
        -(-count // MAX_BATCH),
        min(MAX_CONCURRENT_QUERIES, max(1, count // MIN_BATCH)),
    )
    size, extra = divmod(count, queries)
    return [size + 1] * extra + [size] * (queries - extra)


def look_up(lookups: Sequence[Lookup], transport: Transport) -> list[Result]:
    """Resolve every lookup, in order, in as little time as GitHub allows."""
    batches: list[Sequence[Lookup]] = []
    start = 0
    for size in batch_sizes(len(lookups)):
        batches.append(lookups[start : start + size])
        start += size
    if not batches:
        return []
    replies = asyncio.run(send_all([render(batch) for batch in batches], transport))
    return [
        result
        for batch, reply in zip(batches, replies, strict=True)
        for result in interpret(batch, reply)
    ]


def describe(error: urllib.error.HTTPError) -> str:
    """GitHub's message from an error reply, or else the reason phrase.

    The body may be cut short, as IncompleteRead, or not be JSON; either
    way the reason phrase stands in, so the status still decides whether
    to retry.
    """
    try:
        reply = json.loads(error.read())
    except (OSError, ValueError, RecursionError, http.client.HTTPException):
        return str(error.reason)
    message = reply.get("message") if isinstance(reply, dict) else None
    return message if isinstance(message, str) else str(error.reason)


@dataclass(frozen=True)
class HttpTransport:
    """Posts queries to GitHub's GraphQL endpoint, retrying brief failures."""

    endpoint: str
    token: str = field(repr=False)
    opener: Callable[..., Any] = OPENER.open
    sleep: Callable[[float], None] = time.sleep

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Send one query and return GitHub's decoded reply."""
        body = json.dumps(payload).encode("utf-8")
        attempt = 1
        while True:
            try:
                return self.post(body)
            except TransientError as exc:
                if attempt == ATTEMPTS:
                    raise GitHubError(f"{exc}, after {ATTEMPTS} attempts") from exc
            self.sleep(attempt)
            attempt += 1

    def post(self, body: bytes) -> dict[str, Any]:
        """Make one attempt, telling a brief failure from a lasting one."""
        request = urllib.request.Request(
            self.endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with self.opener(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            message = f"GitHub answered HTTP {exc.code}: {describe(exc)}"
            if exc.code in RETRY_STATUSES:
                raise TransientError(message) from exc
            raise GitHubError(message) from exc
        except (OSError, http.client.HTTPException) as exc:
            raise TransientError(f"could not reach GitHub: {exc}") from exc
        try:
            reply = json.loads(raw)
        except (ValueError, RecursionError) as exc:
            raise GitHubError("GitHub's reply is not JSON") from exc
        if not isinstance(reply, dict):
            raise GitHubError("GitHub's reply is not a JSON object")
        return reply


def field_of(node: Mapping[str, Any], key: str, kind: type[Value]) -> Value:
    """A field of an object GitHub sent, checked against the type it must have."""
    value = node.get(key)
    if not isinstance(value, kind):
        raise GitHubError(f"GitHub's reply lacks {key}")
    return value
