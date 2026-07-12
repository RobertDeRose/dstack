#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = [
# ]
# ///
# ruff: noqa: S603

"""
Fetch all PR conversation comments + reviews + review threads (inline threads)
for the PR associated with the current git branch, by shelling out to:

  gh api graphql

Filters out review threads that are resolved or outdated.
Skips status comments and reviews from known bots (e.g., github-actions, sonarqube).

Requires:
  - `gh auth login` already set up
  - current branch has an associated (open) PR

Usage:
  uv run <skill-dir>/scripts/fetch_comments.py > pr_comments.json
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any


QUERY = """\
query(
  $owner: String!,
  $repo: String!,
  $number: Int!,
  $commentsCursor: String,
  $reviewsCursor: String,
  $threadsCursor: String
) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      url
      title
      state

      # Top-level "Conversation" comments (issue comments on the PR)
      comments(first: 100, after: $commentsCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          body
          createdAt
          updatedAt
          author { login }
        }
      }

      # Review submissions (Approve / Request changes / Comment), with body if present
      reviews(first: 100, after: $reviewsCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          state
          body
          submittedAt
          author { login }
        }
      }

      # Inline review threads (grouped), includes resolved state
      reviewThreads(first: 100, after: $threadsCursor) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          diffSide
          startLine
          startDiffSide
          originalLine
          originalStartLine
          resolvedBy { login }
          comments(first: 100) {
            nodes {
              id
              body
              createdAt
              updatedAt
              author { login }
            }
          }
        }
      }
    }
  }
}
"""

# Case-insensitive blocklist for bot logins.
# GitHub Apps usually append '[bot]' to their logins, while some integrations are standard users.
MAX_BODY_CHARS = 20_000
MAX_DIAGNOSTIC_CHARS = 2_000
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
ALLOWED_COMMANDS = {
    ("gh", "auth"),
    ("gh", "pr"),
    ("gh", "api"),
}


BOT_BLOCKLIST = {
    "github-actions",
    "github-actions[bot]",
    "sonarqube",
    "sonarcloud",
    "sonarcloud[bot]",
    "sonarqubecloud",
}


def _is_bot(node: dict[str, Any]) -> bool:
    """Helper to check if a comment/review author is a known bot."""
    author = node.get("author")
    if not author:  # Handle deleted accounts/ghost users
        return False
    login = author.get("login", "").lower()
    return login in BOT_BLOCKLIST


def _clean_external_text(value: object, *, limit: int = MAX_BODY_CHARS) -> tuple[str, bool]:
    text = CONTROL_CHARS.sub("", str(value or ""))
    if len(text) <= limit:
        return text, False
    return text[:limit] + "\n[truncated by dstack review collector]", True


def _normalize_external_node(node: dict[str, Any], *, source_type: str) -> dict[str, Any]:
    normalized = dict(node)
    body, truncated = _clean_external_text(normalized.get("body"))
    normalized["body"] = body
    normalized["body_truncated"] = truncated
    normalized["trust"] = "untrusted_external_content"
    normalized["source_type"] = source_type
    return normalized


def _validate_command(cmd: list[str]) -> None:
    if len(cmd) < 2 or tuple(cmd[:2]) not in ALLOWED_COMMANDS:
        msg = f"Unsupported command for review collector: {cmd[:2]!r}"
        raise RuntimeError(msg)
    if any("\n" in value or "\x00" in value for value in cmd):
        msg = "Command arguments contain prohibited control characters"
        raise RuntimeError(msg)


def _run(cmd: list[str], stdin: str | None = None) -> str:
    _validate_command(cmd)
    completed = subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        diagnostic, _ = _clean_external_text(completed.stderr, limit=MAX_DIAGNOSTIC_CHARS)
        msg = f"Command failed ({completed.returncode}): {' '.join(cmd[:3])}"
        if diagnostic.strip():
            msg += f"\n{diagnostic.strip()}"
        raise RuntimeError(msg)
    return completed.stdout


def _run_json(cmd: list[str], stdin: str | None = None) -> dict[str, Any]:
    out = _run(cmd, stdin=stdin)
    try:
        payload = json.loads(out)
    except json.JSONDecodeError as exc:
        msg = f"Failed to parse JSON from {' '.join(cmd[:3])}: {exc}"
        raise RuntimeError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"Expected a JSON object from {' '.join(cmd[:3])}"
        raise RuntimeError(msg)
    return payload


def _ensure_gh_authenticated() -> None:
    try:
        _run(["gh", "auth", "status"])
    except RuntimeError:
        print("run `gh auth login` to authenticate the GitHub CLI", file=sys.stderr)
        msg = "gh auth status failed; run `gh auth login` to authenticate the GitHub CLI"
        raise RuntimeError(msg) from None


def gh_pr_view_json(fields: str) -> dict[str, Any]:
    return _run_json(["gh", "pr", "view", "--json", fields])


def get_current_pr_ref() -> tuple[str, str, int]:
    pr = gh_pr_view_json("number,headRepositoryOwner,headRepository")
    owner = pr["headRepositoryOwner"]["login"]
    repo = pr["headRepository"]["name"]
    number = int(pr["number"])
    return owner, repo, number


def gh_api_graphql(
    owner: str,
    repo: str,
    number: int,
    comments_cursor: str | None = None,
    reviews_cursor: str | None = None,
    threads_cursor: str | None = None,
) -> dict[str, Any]:
    cmd = [
        "gh",
        "api",
        "graphql",
        "-F",
        "query=@-",
        "-F",
        f"owner={owner}",
        "-F",
        f"repo={repo}",
        "-F",
        f"number={number}",
    ]
    if comments_cursor:
        cmd += ["-F", f"commentsCursor={comments_cursor}"]
    if reviews_cursor:
        cmd += ["-F", f"reviewsCursor={reviews_cursor}"]
    if threads_cursor:
        cmd += ["-F", f"threadsCursor={threads_cursor}"]

    return _run_json(cmd, stdin=QUERY)


def fetch_all(owner: str, repo: str, number: int) -> dict[str, Any]:
    conversation_comments: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    review_threads: list[dict[str, Any]] = []

    comments_cursor: str | None = None
    reviews_cursor: str | None = None
    threads_cursor: str | None = None

    pr_meta: dict[str, Any] | None = None

    while True:
        payload = gh_api_graphql(
            owner=owner,
            repo=repo,
            number=number,
            comments_cursor=comments_cursor,
            reviews_cursor=reviews_cursor,
            threads_cursor=threads_cursor,
        )

        if payload.get("errors"):
            msg = f"GitHub GraphQL errors:\n{json.dumps(payload['errors'], indent=2)}"
            raise RuntimeError(msg)

        pr = payload["data"]["repository"]["pullRequest"]
        if pr_meta is None:
            pr_meta = {
                "number": pr["number"],
                "url": pr["url"],
                "title": pr["title"],
                "state": pr["state"],
                "owner": owner,
                "repo": repo,
            }

        c = pr["comments"]
        r = pr["reviews"]
        t = pr["reviewThreads"]

        # 1. Filter Top-level Conversation Comments
        for comment in c.get("nodes") or []:
            if not _is_bot(comment):
                conversation_comments.append(_normalize_external_node(comment, source_type="pull_request_comment"))

        # 2. Filter Review Submissions
        for review in r.get("nodes") or []:
            if not _is_bot(review):
                reviews.append(_normalize_external_node(review, source_type="review_submission"))

        # 3. Filter Inline Review Threads (and internal thread comments)
        for thread in t.get("nodes") or []:
            # First, enforce your existing criteria (must be active and up-to-date)
            if not thread.get("isResolved") and not thread.get("isOutdated"):
                # Filter out specific individual comments within this thread if written by a bot
                thread_comments = thread.get("comments", {}).get("nodes") or []
                filtered_comments = [
                    _normalize_external_node(msg, source_type="inline_review_comment")
                    for msg in thread_comments
                    if not _is_bot(msg)
                ]

                # Only keep the thread if it still contains valid human comments
                if filtered_comments:
                    normalized_thread = dict(thread)
                    path_text, path_truncated = _clean_external_text(normalized_thread.get("path"), limit=1_024)
                    normalized_thread["path"] = path_text
                    normalized_thread["path_truncated"] = path_truncated
                    normalized_thread["trust"] = "untrusted_external_content"
                    normalized_thread["source_type"] = "inline_review_thread"
                    normalized_thread["comments"] = {"nodes": filtered_comments}
                    review_threads.append(normalized_thread)

        comments_cursor = c["pageInfo"]["endCursor"] if c["pageInfo"]["hasNextPage"] else None
        reviews_cursor = r["pageInfo"]["endCursor"] if r["pageInfo"]["hasNextPage"] else None
        threads_cursor = t["pageInfo"]["endCursor"] if t["pageInfo"]["hasNextPage"] else None

        if not (comments_cursor or reviews_cursor or threads_cursor):
            break

    assert pr_meta is not None
    return {
        "schema_version": 1,
        "trust": "untrusted_external_content",
        "pull_request": pr_meta,
        "conversation_comments": conversation_comments,
        "reviews": reviews,
        "review_threads": review_threads,
    }


def main() -> None:
    _ensure_gh_authenticated()
    owner, repo, number = get_current_pr_ref()
    result = fetch_all(owner, repo, number)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
