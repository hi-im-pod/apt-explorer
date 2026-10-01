#!/usr/bin/env bash
# Keeps the pipeline's saved state (see pipeline/aptx/core/state.py) on a draft
# release of this repository, so a cache eviction cannot lose it.
#
#   pipeline-state.sh fetch DEST   download the newest saved state to DEST
#   pipeline-state.sh store FILE   save FILE as the newest saved state
#
# A draft release is visible only to people who can push to the repository, and
# its assets do not expire. What it holds is small and public by construction
# (titles, links, dates and link statuses), and `aptx state` refuses to pack
# or unpack anything else.
#
# Needs GITHUB_REPOSITORY and a token with contents: write in GH_TOKEN.
set -euo pipefail

repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"
tag="${STATE_TAG:-pipeline-state}"
keep=3

release_id() {
  gh api "repos/$repo/releases" --paginate \
    --jq ".[] | select(.draft and .tag_name == \"$tag\") | .id" | head -n 1
}

# Newest first, as "id size name" lines.
assets() {
  gh api "repos/$repo/releases/$1" \
    --jq '[.assets[] | select(.name | test("^state-.*[.]tgz$"))] | sort_by(.created_at) | reverse | .[] | "\(.id) \(.size) \(.name)"'
}

output() {
  if [ -n "${GITHUB_OUTPUT:-}" ]; then echo "$1" >> "$GITHUB_OUTPUT"; fi
}

fetch() {
  local dest="$1" id newest
  id="$(release_id)"
  newest=""
  if [ -n "$id" ]; then newest="$(assets "$id" | head -n 1)"; fi
  if [ -z "$newest" ]; then
    echo "No saved state yet, so this run starts from the cache alone."
    output "found=false"
    return 0
  fi
  read -r asset_id size name <<< "$newest"
  mkdir -p "$(dirname "$dest")"
  gh api -H "Accept: application/octet-stream" "repos/$repo/releases/assets/$asset_id" > "$dest"
  if [ "$(wc -c < "$dest")" -ne "$size" ]; then
    echo "::error::$name downloaded as $(wc -c < "$dest") bytes, expected $size"
    exit 1
  fi
  tar -tzf "$dest" > /dev/null
  echo "Fetched $name ($size bytes)."
  output "found=true"
}

store() {
  local file="$1" id previous name new_size
  [ -s "$file" ] || { echo "::error::$file is missing or empty"; exit 1; }
  tar -tzf "$file" > /dev/null
  id="$(release_id)"
  if [ -z "$id" ]; then
    id="$(gh api -X POST "repos/$repo/releases" \
      -f tag_name="$tag" \
      -f name="Pipeline state (draft, never publish)" \
      -f body="Saved state for the weekly build. Written and read by .github/workflows/build.yml. Leave as a draft." \
      -F draft=true --jq .id)"
    echo "Created the draft release $id."
  fi

  new_size="$(wc -c < "$file")"
  previous="$(assets "$id" | head -n 1 || true)"
  if [ -n "$previous" ]; then
    read -r _ old_size _ <<< "$previous"
    # A restore that quietly failed would pack almost nothing. Keep the old state rather than replace it.
    if [ "$((new_size * 2))" -lt "$old_size" ]; then
      echo "::error::The new state is $new_size bytes against $old_size last time. Keeping the old one."
      exit 1
    fi
  fi

  # Upload under a new name first and prune afterwards, so a failed upload never leaves the release empty.
  name="state-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}.tgz"
  gh api -X POST "https://uploads.github.com/repos/$repo/releases/$id/assets?name=$name" \
    -H "Content-Type: application/gzip" --input "$file" --jq .id > /dev/null
  echo "Stored $name ($new_size bytes)."

  assets "$id" | tail -n +"$((keep + 1))" | while read -r old_id _ old_name; do
    gh api -X DELETE "repos/$repo/releases/assets/$old_id"
    echo "Removed $old_name."
  done
}

case "${1:-}" in
  fetch) fetch "${2:?usage: pipeline-state.sh fetch DEST}" ;;
  store) store "${2:?usage: pipeline-state.sh store FILE}" ;;
  *) echo "usage: pipeline-state.sh fetch DEST | store FILE" >&2; exit 2 ;;
esac
