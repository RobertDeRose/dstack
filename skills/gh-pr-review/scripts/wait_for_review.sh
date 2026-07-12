#!/usr/bin/env bash

set -euo pipefail

start_time="$(date +%s)"
readonly start_time
readonly start_timeout_seconds=120
readonly workflow_name="${COPILOT_WORKFLOW_NAME:-Copilot}"

# A completed workflow run is considered new only when it was created after
# this time. A matching queued or running workflow is also accepted regardless
# of its age: GitHub may keep an existing Copilot review workflow active rather
# than create a duplicate when Copilot is requested again for the same PR head.
# Set COPILOT_REVIEW_REQUESTED_AFTER immediately before requesting a review to
# also recognize a completed run that began before this script was invoked.
readonly requested_after="${COPILOT_REVIEW_REQUESTED_AFTER:-$(date -u +'%Y-%m-%dT%H:%M:%SZ')}"

if ! pr_json="$(gh pr view --json number,headRefName,headRefOid)"; then
  echo "No pull request is associated with the current branch. Check out the PR branch before running this script." >&2
  exit 2
fi
pr_number="$(jq -r '.number' <<< "$pr_json")"
branch="$(jq -r '.headRefName' <<< "$pr_json")"
head_sha="$(jq -r '.headRefOid' <<< "$pr_json")"
readonly pr_number branch head_sha

echo "Waiting for Copilot review on PR #${pr_number} (max ${start_timeout_seconds} seconds to start)..."

while :; do
  runs="$(
    gh run list \
      --workflow "$workflow_name" \
      --branch "$branch" \
      --limit 100 \
      --json databaseId,createdAt,headSha,status 2> /dev/null
  )"
  run_id="$(
    jq -r \
      --arg requested_after "$requested_after" \
      --arg head_sha "$head_sha" \
      '.[] |
                select(.headSha == $head_sha) |
                select(
                    .createdAt >= $requested_after or
                    .status == "queued" or
                    .status == "in_progress"
                ) |
                .databaseId' \
      <<< "$runs"
  )"

  current_time="$(date +%s)"
  if [[ -n $run_id ]]; then
    run_id="$(head -n 1 <<< "$run_id")"
    echo "Copilot review workflow started (run ${run_id}). Waiting for completion..."
    gh run watch "$run_id" --compact --exit-status
    echo "Copilot finished its review."
    exit 0
  fi

  if ((current_time - start_time >= start_timeout_seconds)); then
    echo "Copilot did not start a new review workflow within ${start_timeout_seconds} seconds." >&2
    exit 1
  fi

  sleep 5
done
