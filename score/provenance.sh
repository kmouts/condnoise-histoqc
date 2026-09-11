#!/bin/bash
# provenance.sh -- host-side half of the run-provenance protocol.
#
# Sourced by run.sh and runbg.sh; not a standalone script.
#
# The singularity container has no git binary, so a script running inside it cannot
# tell whether the code it is executing matches a commit. Everything git-related is
# therefore captured out here, on the host, and handed in through the environment:
#
#   DQC_GIT_STATUS     `git status --porcelain`; empty string means genuinely clean,
#                      unset means nobody looked -- log_run() distinguishes the two
#   DQC_GIT_PATCH      path to a staged `git diff HEAD`
#   DQC_GIT_UNTRACKED  path to a staged tarball of untracked files
#
# log_run() copies both files into the run's own output directory. The launcher cannot
# write there itself: the output path is derived by the experiment script from its own
# arguments and is not knowable at launch time.
#
# Staging lives under the data root, deliberately not in logs/ -- logs/ is tracked, and
# a stray `git add -A` would otherwise sweep provenance artefacts into the repo.

PROV_DIR="/nfs1/kmouts/DiffusionQC/provenance"
UNTRACKED_WARN_MB=50

capture_provenance() {
    local name="$1"
    local stamp status untracked bytes mb
    stamp="$(date +%Y%m%d_%H%M%S)"

    if ! status="$(git -C "$CODE_DIR" status --porcelain 2>/dev/null)"; then
        echo "provenance: WARNING -- git unavailable or not a repo. Nothing is exported,"
        echo "            so run.json falls back to its mtime heuristic."
        return 0
    fi

    DQC_GIT_STATUS="$status"
    DQC_GIT_PATCH=""
    DQC_GIT_UNTRACKED=""

    if [ -z "$status" ]; then
        echo "provenance: clean at $(git -C "$CODE_DIR" rev-parse --short HEAD)"
    else
        mkdir -p "$PROV_DIR"
        DQC_GIT_PATCH="${PROV_DIR}/${name}_${stamp}.patch"
        git -C "$CODE_DIR" diff HEAD > "$DQC_GIT_PATCH"

        # `git diff HEAD` covers tracked files only, so untracked ones are archived
        # separately -- without this, commit + patch reconstruct only half the tree.
        # The index is deliberately left alone: `git add -N` would fold them into the
        # diff, but a launcher must not mutate the repo it is only observing.
        untracked="$(git -C "$CODE_DIR" ls-files --others --exclude-standard)"
        if [ -n "$untracked" ]; then
            DQC_GIT_UNTRACKED="${PROV_DIR}/${name}_${stamp}_untracked.tar.gz"
            printf '%s\n' "$untracked" | tar czf "$DQC_GIT_UNTRACKED" -C "$CODE_DIR" -T -
            bytes="$(stat -c %s "$DQC_GIT_UNTRACKED")"
            mb=$(( bytes / 1048576 ))
            if [ "$mb" -ge "$UNTRACKED_WARN_MB" ]; then
                echo "provenance: WARNING -- untracked archive is ${mb}MB (>= ${UNTRACKED_WARN_MB}MB)."
                echo "            Something large is untracked and will be copied into the"
                echo "            output directory of every run. Check .gitignore first."
            fi
        fi

        echo "provenance: DIRTY at $(git -C "$CODE_DIR" rev-parse --short HEAD) -- $(printf '%s\n' "$status" | wc -l) change(s)"
        echo "            patch:     $DQC_GIT_PATCH"
        if [ -n "$DQC_GIT_UNTRACKED" ]; then
            echo "            untracked: $DQC_GIT_UNTRACKED"
        fi
    fi

    # Exported for the nohup path (runbg.sh). run.sh cannot use these -- its tmux panes
    # inherit the tmux *server's* environment, not this shell's -- so it re-passes them
    # with `tmux new-session -e`, reading the same three variables.
    export SINGULARITYENV_DQC_GIT_STATUS="$DQC_GIT_STATUS"
    export SINGULARITYENV_DQC_GIT_PATCH="$DQC_GIT_PATCH"
    export SINGULARITYENV_DQC_GIT_UNTRACKED="$DQC_GIT_UNTRACKED"
}
