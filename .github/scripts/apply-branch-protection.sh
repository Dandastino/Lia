#!/usr/bin/env bash
# Applies branch protection to main. Idempotent (PUT replaces the full config).
# Usage: .github/scripts/apply-branch-protection.sh [--dry-run] [--repo owner/name] [--branch main]
set -euo pipefail

REPO="Dandastino/Lia"
BRANCH="main"
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --repo) REPO="$2"; shift ;;
    --branch) BRANCH="$2"; shift ;;
    -h|--help) sed -n '2,3p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

PAYLOAD='{
  "required_status_checks": { "strict": true, "contexts": ["ci-passed"] },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}'

echo "Target: PUT /repos/${REPO}/branches/${BRANCH}/protection"
echo "Payload:"
echo "$PAYLOAD"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] No changes made."
  exit 0
fi

command -v gh >/dev/null || { echo "gh CLI not found" >&2; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "Run 'gh auth login' first" >&2; exit 1; }

echo "$PAYLOAD" | gh api --method PUT "/repos/${REPO}/branches/${BRANCH}/protection" --input - >/dev/null
echo "Branch protection applied to ${REPO}@${BRANCH}."
