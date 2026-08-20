#!/bin/sh
# Assemble a DRAFT of the CHANGELOG section for the next release.
#
# Why this exists: the section used to be written by a person reading `git log`
# across three repositories and retelling it from memory. Nothing checked the
# retelling for completeness — only the heading's shape — and in 0.11.0 a fix
# that mattered to users (core#124: the queue-number memory never expired, so
# payments reported as sent and never arrived, curable only by a restart) was
# left out of the notes entirely. `release-shelf.yml` copies that section into
# the GitHub Release verbatim, so what is missing here is missing in public.
#
# What it changes: the human's job stops being "remember, then add" and becomes
# "read, then delete on purpose". Nothing is dropped by this script — every
# commit in range is printed, sorted into two blocks, and the second block is
# titled to be read rather than skipped.
#
# This is an ASSISTANT, not a guard. Nothing turns red if the draft is ignored:
# checking completeness would mean reading the PRIVATE core repository from the
# PUBLIC repo's CI, and that perimeter costs more than the defect. Which is also
# why the script refuses to run under CI at all — see the guard below.
#
# It reads. It never writes a file, never commits, never publishes.
set -eu

MODE=full
for arg in "$@"; do
    case "$arg" in
        --ranges-only) MODE=ranges ;;
        --classify) MODE=classify ;;
        -h|--help)
            echo "usage: sh scripts/release-notes-draft.sh [--ranges-only|--classify]"
            echo "  --ranges-only  print the tag and the neighbour ranges, no network"
            echo "  --classify     read commit subjects on stdin, print user-facing|internal"
            exit 0
            ;;
        *)
            echo "release-notes-draft: unknown argument '$arg'" >&2
            exit 2
            ;;
    esac
done

# A release note is edited by a person. Under CI there is no person, and the only
# way this could run there is if someone wired it in — at which point the public
# repository's workflow would need a token for the private `core`. Refusing now
# is cheaper than noticing then.
if [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ]; then
    echo "release-notes-draft: refusing to run under CI." >&2
    echo "  This reads the PRIVATE core repository with a person's own gh credentials." >&2
    echo "  Wiring it into a workflow would put a private-repo token in a public repo." >&2
    echo "  Run it on your machine while preparing step 1 of the release." >&2
    exit 3
fi

# `classify` is the whole editorial policy, and it is deliberately weak on its
# own: a prefix is a hint about a commit, not a fact about its reader. The one
# rule that overrides it is security — 0.11.0 shipped `chore(deps): h2 0.4.16
# (RUSTSEC-2026-0258)`, a real fix for users wearing an internal prefix, and the
# block a tired person skims is the wrong place for it.
classify() {
    case "$1" in
        *RUSTSEC-*|*CVE-*|*GHSA-*) echo user-facing ;;
        docs*|chore*|ci*|test*|refactor*|build*|style*) echo internal ;;
        *) echo user-facing ;;
    esac
}

if [ "$MODE" = classify ]; then
    while IFS= read -r subject; do
        [ -n "$subject" ] || continue
        classify "$subject"
    done
    exit 0
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# The previous release tag. Not `git describe --match 'wallet-tui-v*'`: --match
# takes a glob, and a glob cannot say "digits to the end of the string", so
# `wallet-tui-v0.0.0-shelf-test` — a real tag in this repo, pushed to prove the
# release workflow ran — matches it exactly as well as a real release does.
# Filtered by shape AND required to be an ancestor, so a tag on some other
# branch cannot decide this release's range.
PREV_TAG="${RELEASE_NOTES_PREV_TAG:-}"
if [ -z "$PREV_TAG" ]; then
    for candidate in $(git tag --list 'wallet-tui-v*' --sort=-v:refname); do
        case "${candidate#wallet-tui-v}" in
            *[!0-9.]*) continue ;;
        esac
        if git merge-base --is-ancestor "$candidate" HEAD 2>/dev/null; then
            PREV_TAG="$candidate"
            break
        fi
    done
fi
if [ -z "$PREV_TAG" ]; then
    echo "release-notes-draft: no previous release tag reachable from HEAD." >&2
    echo "  Looked for tags matching wallet-tui-v<digits and dots> that are ancestors." >&2
    echo "  Without one there is no range to describe. Name it explicitly:" >&2
    echo "    RELEASE_NOTES_PREV_TAG=wallet-tui-vX.Y.Z sh scripts/release-notes-draft.sh" >&2
    exit 4
fi

# The neighbour versions this release moves through are already written down —
# in the pins the image is built from, then and now. Nobody has to remember them
# or type them: the repository knows.
pin_at() {  # pin_at <ref-or-worktree> <ARG name>
    if [ "$1" = "worktree" ]; then
        sed -n "s|^ARG $2=ghcr\.io/rustok-org/[a-z-]*:v\(.*\)$|\1|p" Dockerfile.wallet | head -n 1
    else
        git show "$1:Dockerfile.wallet" \
            | sed -n "s|^ARG $2=ghcr\.io/rustok-org/[a-z-]*:v\(.*\)$|\1|p" | head -n 1
    fi
}

CORE_WAS="$(pin_at "$PREV_TAG" CORE_IMAGE)"
CORE_NOW="$(pin_at worktree CORE_IMAGE)"
CONSOLE_WAS="$(pin_at "$PREV_TAG" CONSOLE_IMAGE)"
CONSOLE_NOW="$(pin_at worktree CONSOLE_IMAGE)"

for pair in "CORE_IMAGE:$CORE_WAS:$CORE_NOW" "CONSOLE_IMAGE:$CONSOLE_WAS:$CONSOLE_NOW"; do
    name="${pair%%:*}"
    rest="${pair#*:}"
    if [ -z "${rest%%:*}" ] || [ -z "${rest#*:}" ]; then
        echo "release-notes-draft: could not read $name from Dockerfile.wallet at $PREV_TAG or now." >&2
        echo "  An empty range would print as 'nothing changed', which is a lie, not a result." >&2
        exit 5
    fi
done

echo "Previous release: $PREV_TAG"
echo "core:    v$CORE_WAS -> v$CORE_NOW"
echo "console: v$CONSOLE_WAS -> v$CONSOLE_NOW"

[ "$MODE" = ranges ] && exit 0

command -v gh >/dev/null 2>&1 || {
    echo "release-notes-draft: gh is not installed, and the neighbours' history is not local." >&2
    exit 6
}

USER_FACING="$(mktemp)"
INTERNAL="$(mktemp)"
trap 'rm -f "$USER_FACING" "$INTERNAL"' EXIT

sort_line() {  # sort_line <repo label> <subject> <url>
    printf -- '- [ ] %-8s %s   %s\n' "$1" "$2" "$3" >> "$(
        [ "$(classify "$2")" = user-facing ] && echo "$USER_FACING" || echo "$INTERNAL"
    )"
}

collect_neighbour() {  # collect_neighbour <label> <repo> <was> <now>
    if [ "$3" = "$4" ]; then
        echo "  $1: v$3 unchanged — nothing to pull" >&2
        return 0
    fi
    body="$(gh api "repos/$2/compare/v$3...v$4" \
        --jq '.commits[] | (.commit.message | split("\n")[0]) + "\t" + .html_url' 2>&1)" || {
        echo "release-notes-draft: cannot read $2 v$3...v$4 through gh." >&2
        echo "  $body" >&2
        echo "  This is a failure, not an empty release. Fix access and re-run." >&2
        exit 7
    }
    if [ -z "$body" ]; then
        echo "  $1: pin moved v$3 -> v$4 but no commits between the tags — look yourself" >&2
        return 0
    fi
    echo "$body" | while IFS="$(printf '\t')" read -r subject url; do
        sort_line "$1" "$subject" "$url"
    done
}

collect_neighbour core rustok-org/core "$CORE_WAS" "$CORE_NOW"
collect_neighbour console rustok-org/console "$CONSOLE_WAS" "$CONSOLE_NOW"

git log --format='%h	%s' "$PREV_TAG..HEAD" | while IFS="$(printf '\t')" read -r sha subject; do
    sort_line mcp "$subject" "$sha"
done

echo
echo "## Looks user-facing — turn each into prose, or delete it on purpose"
cat "$USER_FACING"
echo
echo "## Looks internal — check before dropping"
cat "$INTERNAL"
