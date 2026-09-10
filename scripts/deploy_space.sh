#!/usr/bin/env bash
# Ship a committed ref to the HF Space without keeping the Space's YAML
# frontmatter in the repo copy of README.md (GitHub renders that block as
# an ugly metadata table). Builds a throwaway commit that prepends
# space-config.yaml to the README, pushes it to the `space` remote, then
# removes the worktree. The repo README stays clean; HF gets its config.
#
#   scripts/deploy_space.sh [ref] [remote]   # defaults: current branch, space
set -euo pipefail

ref="${1:-$(git branch --show-current)}"
: "${ref:=main}"   # detached HEAD has no branch name — fall back to main
remote="${2:-space}"
root="$(git rev-parse --show-toplevel)"
config="$root/space-config.yaml"
tmp="$(mktemp -d)"
trap 'git worktree remove --force "$tmp" >/dev/null 2>&1 || rm -rf "$tmp"' EXIT

[ -f "$config" ] || { echo "missing $config" >&2; exit 1; }

if [ -n "$(git status --porcelain)" ]; then
  echo "warning: uncommitted changes won't ship — only committed work on $ref is deployed" >&2
fi

git worktree add --quiet --detach "$tmp" "$ref"
{ printf -- '---\n'; cat "$config"; printf -- '---\n\n'; cat "$tmp/README.md"; } > "$tmp/README.md.next"
mv "$tmp/README.md.next" "$tmp/README.md"

git -C "$tmp" add README.md
git -C "$tmp" commit --quiet -m "deploy: prepend Space config to README (from $ref)"
# Deploys are throwaway commits, so the Space's main is rewritten every
# time — only the tip (the tree) matters to the build.
git -C "$tmp" push --force "$remote" HEAD:refs/heads/main

echo "pushed $ref (+ Space config) to $remote:main — watch the Space's Logs → Build tab"
