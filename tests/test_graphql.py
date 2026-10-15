# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation

"""Unit tests for list_splitter.graphql."""

from __future__ import annotations

import http.client
import io
import json
import sys
import threading
import unittest
import urllib.error
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fake_github import FakeGitHub  # noqa: E402
from list_splitter import graphql  # noqa: E402
from list_splitter.graphql import (  # noqa: E402
    Absent,
    Argument,
    Found,
    GitHubError,
    HttpTransport,
    Lookup,
    Step,
)


def repository(owner: str, name: str) -> Lookup:
    """A lookup of one repository's name, as a category would write it."""
    arguments = (Argument("owner", "String!", owner), Argument("name", "String!", name))
    return Lookup((Step("repository", arguments, "no repository"),), "nameWithOwner")


def numbered(owner: str, name: str, number: int) -> Lookup:
    """A lookup of an issue or pull request inside its repository."""
    outer = repository(owner, name).path[0]
    inner = Step("issueOrPullRequest", (Argument("number", "Int!", number),), "no item")
    return Lookup((outer, inner), "__typename")


class RenderTest(unittest.TestCase):
    """Queries carry aliases and variables, and no value from the list."""

    def test_nested_path_renders_inside_out(self) -> None:
        """Each step wraps the next, and every argument is a variable."""
        payload = graphql.render([numbered("o", "r", 7)])
        self.assertEqual(
            payload["query"],
            "query($v0_0_owner: String!, $v0_0_name: String!, $v0_1_number: Int!)"
            " { l0: repository(owner: $v0_0_owner, name: $v0_0_name)"
            " { issueOrPullRequest(number: $v0_1_number) { __typename } } }",
        )
        self.assertEqual(
            payload["variables"],
            {"v0_0_owner": "o", "v0_0_name": "r", "v0_1_number": 7},
        )

    def test_values_never_reach_the_query_text(self) -> None:
        """A value written to escape its string stays a variable."""
        hostile = 'x") { id } evil: viewer { login } #'
        payload = graphql.render([repository(hostile, "r"), repository("o", hostile)])
        self.assertNotIn("evil", payload["query"])
        self.assertEqual(payload["variables"]["v0_0_owner"], hostile)
        self.assertEqual(payload["variables"]["v1_0_name"], hostile)

    def test_fields_without_arguments_render_bare(self) -> None:
        """GraphQL refuses empty parentheses, so a plain field has none."""
        viewer = Lookup((Step("viewer", (), "no viewer"),), "login")
        self.assertEqual(
            graphql.render([viewer]),
            {"query": "query { l0: viewer { login } }", "variables": {}},
        )


class InterpretTest(unittest.TestCase):
    """Each lookup reads its own part of a reply, whatever befell the others."""

    batch = (repository("o", "a"), numbered("o", "b", 1), numbered("o", "c", 2))

    def test_nulls_fail_their_own_lookup_at_their_own_depth(self) -> None:
        """A missing repository and a missing number give their own reasons."""
        reply = {
            "data": {
                "l0": {"nameWithOwner": "o/a"},
                "l1": None,
                "l2": {"issueOrPullRequest": None},
            },
            "errors": [
                {"type": "NOT_FOUND", "path": ["l1"], "message": "no repo"},
                {"type": "NOT_FOUND", "path": ["l2", "issueOrPullRequest"]},
            ],
        }
        self.assertEqual(
            graphql.interpret(self.batch, reply),
            [
                Found({"nameWithOwner": "o/a"}),
                Absent("no repository"),
                Absent("no item"),
            ],
        )

    def test_other_errors_on_a_lookup_fail_it_with_github_s_message(self) -> None:
        """A refusal such as SAML enforcement names the lookup it hit."""
        reply = {
            "data": {"l0": None, "l1": None, "l2": None},
            "errors": [{"type": "FORBIDDEN", "path": ["l1"], "message": "SAML"}],
        }
        self.assertEqual(
            graphql.interpret(self.batch, reply)[1],
            Absent("GitHub refused the lookup: SAML"),
        )

    def test_errors_naming_no_lookup_fail_the_query(self) -> None:
        """Rate limits and malformed queries are not about any one item."""
        for reply in (
            {"errors": [{"type": "RATE_LIMITED", "message": "slow down"}]},
            {"data": {}, "errors": [{"path": ["viewer"], "message": "odd"}]},
            {"data": None},
            {"data": {}, "errors": "not a list"},
        ):
            with self.subTest(reply=reply):
                with self.assertRaises(GitHubError):
                    graphql.interpret(self.batch, reply)

    def test_field_of_refuses_a_reply_of_the_wrong_shape(self) -> None:
        """A field GitHub always sends, missing or mistyped, is an error."""
        self.assertEqual(graphql.field_of({"n": 1}, "n", int), 1)
        for node in ({}, {"n": "1"}):
            with self.subTest(node=node):
                with self.assertRaises(GitHubError):
                    graphql.field_of(node, "n", int)


class LookUpTest(unittest.TestCase):
    """Lookups batch, run concurrently, and come back in order."""

    def test_batches_spread_evenly_up_to_the_limits(self) -> None:
        """Short lists share one query; long ones fill every slot evenly."""
        for count, sizes in (
            (0, []),
            (1, [1]),
            (9, [9]),
            (10, [5, 5]),
            (11, [6, 5]),
            (20, [5, 5, 5, 5]),
            (50, [7, 7, 6, 6, 6, 6, 6, 6]),
            (400, [50] * 8),
            (401, [45] * 5 + [44] * 4),
        ):
            with self.subTest(count=count):
                sizes_found = graphql.batch_sizes(count)
                self.assertEqual(sizes_found, sizes)
                self.assertTrue(
                    all(
                        graphql.MIN_BATCH <= size <= graphql.MAX_BATCH for size in sizes
                    )
                    or count < graphql.MIN_BATCH
                )

    def test_no_lookups_send_no_query(self) -> None:
        """An empty list costs nothing."""
        fake = FakeGitHub()
        self.assertEqual(graphql.look_up([], fake), [])
        self.assertEqual(fake.queries, [])

    def test_lookups_travel_in_batches_and_return_in_order(self) -> None:
        """120 lookups take eight queries; each result matches its lookup."""
        fake = FakeGitHub()
        for index in range(0, 120, 2):
            fake.add_repository("o", f"r{index}")
        results = graphql.look_up([repository("o", f"r{i}") for i in range(120)], fake)
        self.assertEqual(
            [len(query["variables"]) // 2 for query in fake.queries], [15] * 8
        )
        for index, result in enumerate(results):
            with self.subTest(index=index):
                if index % 2:
                    self.assertEqual(result, Absent("no repository"))
                else:
                    self.assertEqual(
                        result, Found(fake.repositories[("o", f"r{index}")])
                    )

    def test_queries_overlap_up_to_the_limit(self) -> None:
        """Batches run concurrently, never more than the limit at once."""
        fake = FakeGitHub(delay=0.1)
        with patch.object(graphql, "MAX_BATCH", 1):
            graphql.look_up([repository("o", f"r{i}") for i in range(12)], fake)
        self.assertEqual(len(fake.queries), 12)
        self.assertGreater(fake.peak, 1)
        self.assertLessEqual(fake.peak, graphql.MAX_CONCURRENT_QUERIES)

    def test_a_failed_query_fails_the_lookups(self) -> None:
        """One query GitHub cannot answer fails the whole verification."""
        fake = FakeGitHub()

        def flaky(payload: dict[str, Any]) -> dict[str, Any]:
            if payload["variables"].get("v0_0_name") == "r1":
                raise GitHubError("down")
            return fake(payload)

        with patch.object(graphql, "MAX_BATCH", 1):
            with self.assertRaisesRegex(GitHubError, "down"):
                graphql.look_up([repository("o", f"r{i}") for i in range(3)], flaky)
        self.assertEqual(len(fake.queries), 2)


class Opener:
    """Stands in for urlopen, playing back one outcome per call."""

    def __init__(self, *outcomes: bytes | BaseException) -> None:
        """Queue the replies or exceptions, in call order."""
        self.outcomes = list(outcomes)
        self.requests: list[Any] = []

    def __call__(self, request: Any, timeout: float) -> io.BytesIO:
        """Record the request, then reply or raise as queued."""
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return io.BytesIO(outcome)


def http_error(code: int, body: bytes = b"") -> urllib.error.HTTPError:
    """An error reply as urlopen raises it."""
    return urllib.error.HTTPError(
        "https://api.github.invalid/graphql",
        code,
        "Reason",
        Message(),
        io.BytesIO(body),
    )


class CutShort(io.BytesIO):
    """A reply body the connection dropped partway through."""

    def read(self, size: int | None = -1) -> bytes:
        """Fail as http.client does on a truncated body."""
        raise http.client.IncompleteRead(b'{"mess')


def truncated_error(code: int) -> urllib.error.HTTPError:
    """An error reply whose body cannot be read in full."""
    url = "https://api.github.invalid/graphql"
    return urllib.error.HTTPError(url, code, "Reason", Message(), CutShort())


class HttpTransportTest(unittest.TestCase):
    """The transport retries brief failures and reports lasting ones."""

    def transport(self, opener: Opener) -> tuple[HttpTransport, list[float]]:
        """A transport using the opener, recording its pauses."""
        pauses: list[float] = []
        endpoint = "https://api.github.invalid/graphql"
        return HttpTransport(endpoint, "secret", opener, pauses.append), pauses

    def test_posts_json_with_the_token(self) -> None:
        """One POST carries the query as JSON and the token as a bearer."""
        opener = Opener(b'{"data": {}}')
        transport, _ = self.transport(opener)
        self.assertEqual(transport({"query": "{ x }"}), {"data": {}})
        (request,) = opener.requests
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "bearer secret")
        self.assertEqual(json.loads(request.data), {"query": "{ x }"})
        self.assertNotIn("secret", repr(transport))

    def test_retries_server_errors_and_network_failures(self) -> None:
        """A 502 and a dropped connection are retried, with growing pauses."""
        opener = Opener(http_error(502), urllib.error.URLError("reset"), b"{}")
        transport, pauses = self.transport(opener)
        self.assertEqual(transport({}), {})
        self.assertEqual(pauses, [1, 2])

    def test_gives_up_after_the_last_attempt(self) -> None:
        """Three brief failures in a row become a lasting one."""
        transport, _ = self.transport(Opener(*[http_error(503)] * graphql.ATTEMPTS))
        with self.assertRaisesRegex(GitHubError, "HTTP 503.*after 3 attempts"):
            transport({})

    def test_refusals_fail_at_once_with_github_s_message(self) -> None:
        """A rejected token is not retried, and says why."""
        opener = Opener(http_error(401, b'{"message": "Bad credentials"}'))
        transport, pauses = self.transport(opener)
        with self.assertRaisesRegex(GitHubError, "HTTP 401: Bad credentials"):
            transport({})
        self.assertEqual(pauses, [])

    def test_a_reply_must_be_a_json_object(self) -> None:
        """HTML from a proxy, or a bare array, is not a GraphQL reply."""
        for body in (b"<html>", b"[]", b"[" * 100_000):
            with self.subTest(body=body[:10]):
                transport, _ = self.transport(Opener(body))
                with self.assertRaises(GitHubError):
                    transport({})

    def test_an_unreadable_error_body_still_retries(self) -> None:
        """A truncated 503 body falls back to the reason phrase, and retries."""
        opener = Opener(truncated_error(503), truncated_error(503), b"{}")
        transport, pauses = self.transport(opener)
        self.assertEqual(transport({}), {})
        self.assertEqual(pauses, [1, 2])
        transport, _ = self.transport(
            Opener(*[truncated_error(503)] * graphql.ATTEMPTS)
        )
        with self.assertRaisesRegex(GitHubError, "HTTP 503: Reason, after 3"):
            transport({})


def serve(handler: type[BaseHTTPRequestHandler]) -> str:
    """Run a local HTTP server for the rest of the test; return its address."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}"


class QuietHandler(BaseHTTPRequestHandler):
    """A request handler that keeps the test output free of request logs."""

    def log_message(self, format: str, *args: Any) -> None:
        """Log nothing."""


class Target(QuietHandler):
    """Where a redirect points: records every request that arrives."""

    reached: ClassVar[list[str | None]] = []

    def do_GET(self) -> None:
        """Record the request's token, and answer as GitHub might."""
        self.reached.append(self.headers.get("Authorization"))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")


class RedirectTest(unittest.TestCase):
    """The token goes to the endpoint and nowhere else."""

    def test_a_redirect_fails_and_the_token_stays(self) -> None:
        """urllib would follow a redirect with the token; the transport refuses."""
        Target.reached.clear()
        target = serve(Target)

        class Redirector(QuietHandler):
            def do_POST(self) -> None:
                """Send every query elsewhere."""
                self.send_response(302)
                self.send_header("Location", f"{target}/elsewhere")
                self.end_headers()

        transport = HttpTransport(f"{serve(Redirector)}/graphql", "secret")
        with self.assertRaisesRegex(GitHubError, "HTTP 302"):
            transport({"query": "{ x }"})
        self.assertEqual(Target.reached, [])


if __name__ == "__main__":
    unittest.main()
