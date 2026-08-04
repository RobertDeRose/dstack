#!/usr/bin/env -S uv run --script
#
# /// script
# requires-python = ">=3.13"
# dependencies = [
# ]
# ///
# ruff: noqa: EM101, S603

"""
Fetch all PR conversation comments + reviews + review threads (inline threads)
for the PR associated with the current git branch, by shelling out to:

  gh api graphql

Filters out review threads that are resolved or outdated. Skips status comments and reviews from known bots;
SonarQube Cloud content is retained only when the optional `sonar` CLI is installed and a SonarQube comment is present.

Requires:
  - `gh auth login` already set up
  - current branch has an associated (open) PR

Usage:
  uv run <skill-dir>/scripts/fetch_comments.py > pr_comments.json
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import parse_qs, urlsplit


QUERY = """\
query(
  $owner: String!,
  $repo: String!,
  $number: Int!,
  $commentsCursor: String,
  $reviewsCursor: String,
  $threadsCursor: String,
  $includeComments: Boolean!,
  $includeReviews: Boolean!,
  $includeThreads: Boolean!
) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      url
      title
      state

      # Top-level "Conversation" comments (issue comments on the PR)
      comments(first: 100, after: $commentsCursor) @include(if: $includeComments) {
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
      reviews(first: 100, after: $reviewsCursor) @include(if: $includeReviews) {
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
      reviewThreads(first: 100, after: $threadsCursor) @include(if: $includeThreads) {
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
            pageInfo { hasNextPage endCursor }
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

THREAD_COMMENTS_QUERY = """\
query($threadId: ID!, $commentsCursor: String) {
  node(id: $threadId) {
    ... on PullRequestReviewThread {
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
    }
  }
}
"""

# Case-insensitive blocklist for bot logins.
# GitHub Apps usually append '[bot]' to their logins, while some integrations are standard users.
MAX_BODY_CHARS = 20_000
MAX_DIAGNOSTIC_CHARS = 2_000
SONAR_PAGE_SIZE = 500
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SONAR_URL = re.compile(r"https://(?:www\.)?sonarcloud\.io/[^\s<>()]+", re.IGNORECASE)
SONAR_PROJECT_KEY = re.compile(r"[A-Za-z0-9_.:-]+")
ALLOWED_COMMANDS = {
    ("gh", "auth"),
    ("gh", "pr"),
    ("gh", "api"),
    ("sonar", "list"),
}


SONAR_BOT_LOGINS = {
    "sonarqube",
    "sonarcloud",
    "sonarcloud[bot]",
    "sonarqubecloud",
    "sonarqubecloud[bot]",
}
BOT_BLOCKLIST = {
    "github-actions",
    "github-actions[bot]",
    *SONAR_BOT_LOGINS,
}


def _author_login(node: dict[str, Any]) -> str:
    author = node.get("author")
    if not author:  # Handle deleted accounts/ghost users
        return ""
    return str(author.get("login", "")).lower()


def _is_sonar_bot(node: dict[str, Any]) -> bool:
    return _author_login(node) in SONAR_BOT_LOGINS


def _is_bot(node: dict[str, Any], *, allow_sonar: bool = False) -> bool:
    """Check if a comment/review author is a known bot."""
    login = _author_login(node)
    if allow_sonar and login in SONAR_BOT_LOGINS:
        return False
    return login in BOT_BLOCKLIST


def _sonar_cli_available() -> bool:
    return shutil.which("sonar") is not None


def _sonar_project_keys(node: dict[str, Any]) -> set[str]:
    """Extract safe SonarCloud project keys from links in a Sonar bot comment."""
    if not _is_sonar_bot(node):
        return set()
    keys: set[str] = set()
    for raw_url in SONAR_URL.findall(str(node.get("body") or "")):
        try:
            query = parse_qs(urlsplit(raw_url.rstrip(".,;")).query)
        except ValueError:
            continue
        for parameter in ("id", "project"):
            for value in query.get(parameter, []):
                if SONAR_PROJECT_KEY.fullmatch(value):
                    keys.add(value)
    return keys


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


def _collect_sonar_issues(number: int, project_keys: list[str]) -> list[dict[str, Any]]:
    if not project_keys:
        raise RuntimeError("could not derive a SonarQube project key from the SonarCloud comment")

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for project in project_keys:
        page = 1
        while True:
            payload = _run_json(
                [
                    "sonar",
                    "list",
                    "issues",
                    "--project",
                    project,
                    "--pull-request",
                    str(number),
                    "--page-size",
                    str(SONAR_PAGE_SIZE),
                    "--page",
                    str(page),
                    "--format",
                    "json",
                ]
            )
            issues = payload.get("issues")
            if not isinstance(issues, list):
                raise RuntimeError("SonarQube CLI returned JSON without an issues array")
            for issue in issues:
                if not isinstance(issue, dict):
                    raise RuntimeError("SonarQube CLI returned a non-object issue")
                key = str(issue.get("key") or "")
                identity = (project, key)
                if identity in seen:
                    continue
                seen.add(identity)
                item = dict(issue)
                body, truncated = _clean_external_text(item.get("message"))
                item["body"] = body
                item["body_truncated"] = truncated
                item["project"] = project
                item["trust"] = "untrusted_external_content"
                item["source_type"] = "sonarqube_issue"
                normalized.append(item)

            paging = payload.get("paging")
            total = paging.get("total") if isinstance(paging, dict) else None
            has_next_page = isinstance(paging, dict) and paging.get("hasNextPage") is True
            if not has_next_page and not (isinstance(total, int) and page * SONAR_PAGE_SIZE < total):
                break
            page += 1
    return normalized


def gh_api_graphql(
    owner: str,
    repo: str,
    number: int,
    comments_cursor: str | None = None,
    reviews_cursor: str | None = None,
    threads_cursor: str | None = None,
    *,
    include_comments: bool = True,
    include_reviews: bool = True,
    include_threads: bool = True,
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
        "-F",
        f"includeComments={'true' if include_comments else 'false'}",
        "-F",
        f"includeReviews={'true' if include_reviews else 'false'}",
        "-F",
        f"includeThreads={'true' if include_threads else 'false'}",
    ]
    if comments_cursor:
        cmd += ["-F", f"commentsCursor={comments_cursor}"]
    if reviews_cursor:
        cmd += ["-F", f"reviewsCursor={reviews_cursor}"]
    if threads_cursor:
        cmd += ["-F", f"threadsCursor={threads_cursor}"]

    return _run_json(cmd, stdin=QUERY)


def gh_thread_comments(thread_id: str, comments_cursor: str | None = None) -> dict[str, Any]:
    cmd = [
        "gh",
        "api",
        "graphql",
        "-F",
        "query=@-",
        "-F",
        f"threadId={thread_id}",
    ]
    if comments_cursor:
        cmd += ["-F", f"commentsCursor={comments_cursor}"]

    payload = _run_json(cmd, stdin=THREAD_COMMENTS_QUERY)
    if payload.get("errors"):
        msg = f"GitHub GraphQL errors:\n{json.dumps(payload['errors'], indent=2)}"
        raise RuntimeError(msg)
    try:
        comments = payload["data"]["node"]["comments"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("GitHub GraphQL response omitted review-thread comments") from exc
    if not isinstance(comments, dict):
        raise RuntimeError("GitHub GraphQL returned invalid review-thread comments")
    return comments


def _next_cursor(connection: dict[str, Any]) -> str | None:
    page_info = connection.get("pageInfo")
    if not isinstance(page_info, dict):
        raise RuntimeError("GitHub GraphQL response omitted pagination information")
    if not page_info.get("hasNextPage"):
        return None
    cursor = page_info.get("endCursor")
    if not isinstance(cursor, str) or not cursor:
        raise RuntimeError("GitHub GraphQL response has a next page without an end cursor")
    return cursor


def _fetch_thread_comment_nodes(thread: dict[str, Any]) -> list[dict[str, Any]]:
    connection = thread.get("comments")
    if not isinstance(connection, dict):
        raise RuntimeError("GitHub GraphQL response omitted review-thread comments")
    nodes = list(connection.get("nodes") or [])
    cursor = _next_cursor(connection)
    if not cursor:
        return nodes
    thread_id = thread.get("id")
    if not isinstance(thread_id, str) or not thread_id:
        raise RuntimeError("GitHub GraphQL response omitted the review-thread ID")
    while cursor:
        connection = gh_thread_comments(thread_id, cursor)
        nodes.extend(connection.get("nodes") or [])
        cursor = _next_cursor(connection)
    return nodes


def fetch_all(owner: str, repo: str, number: int) -> dict[str, Any]:
    conversation_comments: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    review_threads: list[dict[str, Any]] = []
    sonar_issues: list[dict[str, Any]] = []
    sonar_cli_available = _sonar_cli_available()
    sonar_comment_detected = False
    sonar_project_keys: set[str] = set()

    comments_cursor: str | None = None
    reviews_cursor: str | None = None
    threads_cursor: str | None = None
    include_comments = True
    include_reviews = True
    include_threads = True

    pr_meta: dict[str, Any] | None = None

    while include_comments or include_reviews or include_threads:
        payload = gh_api_graphql(
            owner=owner,
            repo=repo,
            number=number,
            comments_cursor=comments_cursor,
            reviews_cursor=reviews_cursor,
            threads_cursor=threads_cursor,
            include_comments=include_comments,
            include_reviews=include_reviews,
            include_threads=include_threads,
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

        if include_comments:
            c = pr.get("comments")
            if not isinstance(c, dict):
                raise RuntimeError("GitHub GraphQL response omitted pull-request comments")
            # 1. Filter top-level conversation comments. SonarCloud content is retained only when
            # the optional SonarQube CLI is installed; the CLI is also used to fetch structured issues below.
            for comment in c.get("nodes") or []:
                if _is_sonar_bot(comment):
                    sonar_comment_detected = True
                    sonar_project_keys.update(_sonar_project_keys(comment))
                if not _is_bot(comment, allow_sonar=sonar_cli_available):
                    source_type = "sonarqube_comment" if _is_sonar_bot(comment) else "pull_request_comment"
                    conversation_comments.append(_normalize_external_node(comment, source_type=source_type))
            comments_cursor = _next_cursor(c)
            include_comments = comments_cursor is not None

        if include_reviews:
            r = pr.get("reviews")
            if not isinstance(r, dict):
                raise RuntimeError("GitHub GraphQL response omitted pull-request reviews")
            # 2. Filter review submissions
            for review in r.get("nodes") or []:
                if _is_sonar_bot(review):
                    sonar_comment_detected = True
                    sonar_project_keys.update(_sonar_project_keys(review))
                if not _is_bot(review, allow_sonar=sonar_cli_available):
                    source_type = "sonarqube_review" if _is_sonar_bot(review) else "review_submission"
                    reviews.append(_normalize_external_node(review, source_type=source_type))
            reviews_cursor = _next_cursor(r)
            include_reviews = reviews_cursor is not None

        if include_threads:
            t = pr.get("reviewThreads")
            if not isinstance(t, dict):
                raise RuntimeError("GitHub GraphQL response omitted review threads")
            # 3. Filter inline review threads (and internal thread comments)
            for thread in t.get("nodes") or []:
                thread_comments = _fetch_thread_comment_nodes(thread)
                for message in thread_comments:
                    if _is_sonar_bot(message):
                        sonar_comment_detected = True
                        sonar_project_keys.update(_sonar_project_keys(message))
                # Keep only active, up-to-date threads.
                if not thread.get("isResolved") and not thread.get("isOutdated"):
                    filtered_comments = [
                        _normalize_external_node(
                            msg,
                            source_type=("sonarqube_inline_comment" if _is_sonar_bot(msg) else "inline_review_comment"),
                        )
                        for msg in thread_comments
                        if not _is_bot(msg, allow_sonar=sonar_cli_available)
                    ]

                    # Only keep the thread if it still contains valid comments.
                    if filtered_comments:
                        normalized_thread = dict(thread)
                        path_text, path_truncated = _clean_external_text(normalized_thread.get("path"), limit=1_024)
                        normalized_thread["path"] = path_text
                        normalized_thread["path_truncated"] = path_truncated
                        normalized_thread["trust"] = "untrusted_external_content"
                        normalized_thread["source_type"] = "inline_review_thread"
                        normalized_thread["comments"] = {"nodes": filtered_comments}
                        review_threads.append(normalized_thread)
            threads_cursor = _next_cursor(t)
            include_threads = threads_cursor is not None

    sonar_status: dict[str, Any]
    if not sonar_comment_detected:
        sonar_status = {
            "status": "not_detected",
            "cli_available": sonar_cli_available,
            "issue_count": 0,
            "projects": [],
        }
    elif not sonar_cli_available:
        sonar_status = {
            "status": "skipped",
            "cli_available": False,
            "issue_count": 0,
            "projects": sorted(sonar_project_keys),
            "reason": "sonar CLI is not installed",
        }
    else:
        try:
            sonar_issues = _collect_sonar_issues(number, sorted(sonar_project_keys))
        except RuntimeError as error:
            detail, _ = _clean_external_text(str(error), limit=MAX_DIAGNOSTIC_CHARS)
            sonar_status = {
                "status": "error",
                "cli_available": True,
                "issue_count": 0,
                "projects": sorted(sonar_project_keys),
                "error": detail,
            }
        else:
            sonar_status = {
                "status": "loaded",
                "cli_available": True,
                "issue_count": len(sonar_issues),
                "projects": sorted(sonar_project_keys),
            }

    assert pr_meta is not None
    return {
        "schema_version": 1,
        "trust": "untrusted_external_content",
        "pull_request": pr_meta,
        "conversation_comments": conversation_comments,
        "reviews": reviews,
        "review_threads": review_threads,
        "sonarqube": sonar_status,
        "sonar_issues": sonar_issues,
    }


def main() -> None:
    _ensure_gh_authenticated()
    owner, repo, number = get_current_pr_ref()
    result = fetch_all(owner, repo, number)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
