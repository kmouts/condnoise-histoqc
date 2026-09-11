#!/bin/bash
# runbg.sh -- launch a job in Singularity, in the background, logging to a file.
#
# Uses nohup rather than tmux: the job survives disconnection and output goes straight
# to a log you can follow with `tail -f`, with no attach/detach step.
#
#   ./runbg.sh variantB python train_enhanced.py --tag variantB --no-fa-in-basic
#   GPU=1 ./runbg.sh variantA python train_enhanced.py --tag variantA --fa-in-basic
#
# GPU selection: your account is allocated physical GPUs 2 and 6 via CUDA_VISIBLE_DEVICES
# in ~/.bashrc. Inside that allocation they are indexed 0 and 1. GPU=0 or GPU=1 picks one
# of yours; leaving GPU unset makes both visible (the code uses cuda:0, so effectively the
# first). Note this selects *within* your allocation -- it cannot grant access to cards
# that were not assigned to you, and it should not be used to try.

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "usage: [GPU=n] $0 <job-name> <command...>"
    echo "  GPU=0  -> first allocated GPU   (physical 2)"
    echo "  GPU=1  -> second allocated GPU  (physical 6)"
    echo "  unset  -> both visible"
    exit 1
fi

NAME="$1"; shift

CODE_DIR="/nfs1/kmouts/code"
CONTAINER="/nfs1/kmouts/torchenv"
LOG_DIR="${CODE_DIR}/logs"
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/${NAME}_$(date +%Y%m%d_%H%M%S).log"

if [ -n "${GPU:-}" ]; then
    export SINGULARITYENV_CUDA_VISIBLE_DEVICES="$GPU"
    GPU_DESC="index $GPU within your allocation (${CUDA_VISIBLE_DEVICES:-unset})"
else
    GPU_DESC="all allocated (${CUDA_VISIBLE_DEVICES:-unset})"
fi

cd "$CODE_DIR"

# Capture the host's git state before launching: the container has no git binary.
# Plain `export` suffices here -- nohup's child inherits this shell directly, unlike
# run.sh, whose tmux panes inherit the tmux server's environment instead.
source "${CODE_DIR}/provenance.sh"
capture_provenance "$NAME"

# -u keeps Python's output unbuffered, so `tail -f` shows progress as it happens
# rather than in delayed chunks.
nohup singularity exec --nv "$CONTAINER" python -u "${@:2}" > "$LOG" 2>&1 &
PID=$!

echo "job:  $NAME"
echo "pid:  $PID"
echo "gpu:  $GPU_DESC"
echo "log:  $LOG"
echo
echo "  tail -f $LOG      # follow output"
echo "  kill $PID         # stop the job"
echo "  gpustat -cup      # confirm which GPU it landed on"
