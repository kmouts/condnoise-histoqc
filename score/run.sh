#!/bin/bash
# run.sh -- launch a job inside Singularity, detached in tmux, with logging.
#
# Long jobs must survive SSH disconnection; tmux handles that. Logs are written to
# logs/<session>_<timestamp>.log so output survives even if the tmux session is lost.
#
#   ./run.sh variantB python train_enhanced.py --tag variantB --no-fa-in-basic --steps 1000
#   ./run.sh infer950 python infer_wsi.py --model basic --timesteps 950
#
# Then:  tmux attach -t variantB      (detach with Ctrl+B then D)
#        tail -f logs/variantB_*.log
#        gpustat -cup

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "usage: $0 <session-name> <command...>"
    echo "example: $0 variantB python train_enhanced.py --tag variantB --no-fa-in-basic"
    exit 1
fi

SESSION="$1"; shift

CODE_DIR="/nfs1/kmouts/code"
CONTAINER="/nfs1/kmouts/torchenv"
LOG_DIR="${CODE_DIR}/logs"
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/${SESSION}_$(date +%Y%m%d_%H%M%S).log"

# Capture the host's git state before launching: the container has no git binary.
source "${CODE_DIR}/provenance.sh"
capture_provenance "$SESSION"

# A tmux pane inherits the tmux *server's* environment, which was fixed when the server
# first started -- an exported variable here is invisible to it. `new-session -e` is the
# only way in. The array stays empty if capture_provenance bailed out, so that "unset"
# (nobody checked) never gets flattened into "" (checked, and clean).
PROV_ENV=()
if [ -n "${SINGULARITYENV_DQC_GIT_STATUS+set}" ]; then
    PROV_ENV+=(-e "SINGULARITYENV_DQC_GIT_STATUS=${SINGULARITYENV_DQC_GIT_STATUS}")
    PROV_ENV+=(-e "SINGULARITYENV_DQC_GIT_PATCH=${SINGULARITYENV_DQC_GIT_PATCH}")
    PROV_ENV+=(-e "SINGULARITYENV_DQC_GIT_UNTRACKED=${SINGULARITYENV_DQC_GIT_UNTRACKED}")
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "ERROR: tmux session '$SESSION' already exists."
    echo "  attach:  tmux attach -t $SESSION"
    echo "  kill:    tmux kill-session -t $SESSION"
    exit 1
fi

# CUDA_VISIBLE_DEVICES comes from ~/.bashrc (GPUs 2 and 6, which appear as 0 and 1
# inside the container). Reported here so the log records which GPUs a run used.
echo "session:   $SESSION"
echo "command:   $*"
echo "container: $CONTAINER"
echo "log:       $LOG"
echo "CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-<unset>}"
echo

# HF_TOKEN is passed through explicitly: the token file lives in the NFS home, which
# Singularity binds by default, but an explicit env var is more robust across bind modes.
tmux new-session -d -s "$SESSION" ${PROV_ENV[@]+"${PROV_ENV[@]}"} \
    "cd $CODE_DIR && \
     SINGULARITYENV_HF_TOKEN=\"\${HF_TOKEN:-}\" \
     singularity exec --nv $CONTAINER $* 2>&1 | tee $LOG"

echo "Started. Useful commands:"
echo "  tmux attach -t $SESSION     # watch (Ctrl+B then D to detach)"
echo "  tail -f $LOG                # follow the log without attaching"
echo "  gpustat -cup                # GPU usage"
echo "  tmux kill-session -t $SESSION"
