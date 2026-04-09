#!/bin/bash
# launch.sh — Start an autoresearch_sr agent loop
#
# Usage:
#   bash launch.sh --mode operator [--model sonnet] [--split ../splits/train_hard.txt] ...
#   bash launch.sh --mode codebase --sandbox-root /home/sca63/meta_sr_agent_loop [...]
#
# This script:
# 1. Copies reference docs into the workspace
# 2. Evaluates the baseline
# 3. Renders program.md from the template
# 4. Launches Claude Code to run the agent loop

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
MODE="operator"
MODEL="sonnet"
SPLIT="../splits/train_hard.txt"
N_RUNS=3
SEED=42
FITNESS_METRIC="gt"
MAX_EVALS=""
TIMEOUT=""
MAX_SAMPLES="1000"
PARTITION=""
TIME_LIMIT=""
RANDOM_TARGET_NOISE=""
SANDBOX_ROOT=""
SANDBOX_JULIA_PROJECT=""
SANDBOX_PYTHON_JULIAPKG_PROJECT=""
MAX_TURNS="200"
EDITABLE_FILES=""

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case $1 in
        --mode) MODE="$2"; shift 2 ;;
        --model) MODEL="$2"; shift 2 ;;
        --split) SPLIT="$2"; shift 2 ;;
        --n-runs) N_RUNS="$2"; shift 2 ;;
        --seed) SEED="$2"; shift 2 ;;
        --fitness-metric) FITNESS_METRIC="$2"; shift 2 ;;
        --max-evals) MAX_EVALS="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --max-samples) MAX_SAMPLES="$2"; shift 2 ;;
        --partition) PARTITION="$2"; shift 2 ;;
        --time-limit) TIME_LIMIT="$2"; shift 2 ;;
        --random-target-noise) RANDOM_TARGET_NOISE="--random-target-noise"; shift ;;
        --sandbox-root) SANDBOX_ROOT="$2"; shift 2 ;;
        --sandbox-julia-project) SANDBOX_JULIA_PROJECT="$2"; shift 2 ;;
        --sandbox-python-juliapkg-project) SANDBOX_PYTHON_JULIAPKG_PROJECT="$2"; shift 2 ;;
        --max-turns) MAX_TURNS="$2"; shift 2 ;;
        --editable-files) EDITABLE_FILES="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------
if [[ "$MODE" == "codebase" && -z "$SANDBOX_ROOT" ]]; then
    echo "Error: --sandbox-root is required for codebase mode"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 1: Copy reference docs
# ---------------------------------------------------------------------------
echo "=== Setting up workspace ==="

SR_JL="$SCRIPT_DIR/../SymbolicRegression.jl/src"

mkdir -p reference operators

if [[ -f "$SR_JL/custom_mutations/MUTATIONS_REFERENCE.md" ]]; then
    cp "$SR_JL/custom_mutations/MUTATIONS_REFERENCE.md" reference/
    echo "  Copied MUTATIONS_REFERENCE.md"
fi
if [[ -f "$SR_JL/custom_mutations/MUTATIONS_REFERENCE2.md" ]]; then
    cp "$SR_JL/custom_mutations/MUTATIONS_REFERENCE2.md" reference/
    echo "  Copied MUTATIONS_REFERENCE2.md"
fi
if [[ -f "$SR_JL/custom_survival/SURVIVAL_REFERENCE.md" ]]; then
    cp "$SR_JL/custom_survival/SURVIVAL_REFERENCE.md" reference/
    echo "  Copied SURVIVAL_REFERENCE.md"
fi
if [[ -f "$SR_JL/custom_selection/SELECTION_REFERENCE.md" ]]; then
    cp "$SR_JL/custom_selection/SELECTION_REFERENCE.md" reference/
    echo "  Copied SELECTION_REFERENCE.md"
fi

# ---------------------------------------------------------------------------
# Step 2: Evaluate baseline
# ---------------------------------------------------------------------------
echo ""
echo "=== Evaluating baseline ==="

PREPARE_ARGS="--mode baseline --split $SPLIT --n-runs $N_RUNS --seed $SEED --fitness-metric $FITNESS_METRIC --max-samples $MAX_SAMPLES"
[[ -n "$MAX_EVALS" ]] && PREPARE_ARGS="$PREPARE_ARGS --max-evals $MAX_EVALS"
[[ -n "$TIMEOUT" ]] && PREPARE_ARGS="$PREPARE_ARGS --timeout $TIMEOUT"
[[ -n "$PARTITION" ]] && PREPARE_ARGS="$PREPARE_ARGS --partition $PARTITION"
[[ -n "$TIME_LIMIT" ]] && PREPARE_ARGS="$PREPARE_ARGS --time-limit $TIME_LIMIT"
[[ -n "$RANDOM_TARGET_NOISE" ]] && PREPARE_ARGS="$PREPARE_ARGS $RANDOM_TARGET_NOISE"

python prepare.py $PREPARE_ARGS > baseline_run.log 2>&1
BASELINE_SCORE=$(grep "^score:" baseline_run.log | awk '{print $2}')

if [[ -z "$BASELINE_SCORE" ]]; then
    echo "ERROR: Could not extract baseline score. Check baseline_run.log:"
    tail -20 baseline_run.log
    exit 1
fi

echo "Baseline score: $BASELINE_SCORE"

# ---------------------------------------------------------------------------
# Step 3: Render program.md
# ---------------------------------------------------------------------------
echo ""
echo "=== Rendering program.md ==="

RENDER_ARGS="--mode $MODE --baseline-score $BASELINE_SCORE --split $SPLIT --n-runs $N_RUNS --seed $SEED --fitness-metric $FITNESS_METRIC"
[[ -n "$MAX_EVALS" ]] && RENDER_ARGS="$RENDER_ARGS --max-evals $MAX_EVALS"
[[ -n "$TIMEOUT" ]] && RENDER_ARGS="$RENDER_ARGS --timeout $TIMEOUT"
[[ -n "$PARTITION" ]] && RENDER_ARGS="$RENDER_ARGS --partition $PARTITION"
[[ -n "$TIME_LIMIT" ]] && RENDER_ARGS="$RENDER_ARGS --time-limit $TIME_LIMIT"
[[ -n "$MAX_SAMPLES" ]] && RENDER_ARGS="$RENDER_ARGS --max-samples $MAX_SAMPLES"
[[ -n "$RANDOM_TARGET_NOISE" ]] && RENDER_ARGS="$RENDER_ARGS --random-target-noise"
[[ -n "$SANDBOX_ROOT" ]] && RENDER_ARGS="$RENDER_ARGS --sandbox-root $SANDBOX_ROOT"
[[ -n "$SANDBOX_JULIA_PROJECT" ]] && RENDER_ARGS="$RENDER_ARGS --sandbox-julia-project $SANDBOX_JULIA_PROJECT"
[[ -n "$SANDBOX_PYTHON_JULIAPKG_PROJECT" ]] && RENDER_ARGS="$RENDER_ARGS --sandbox-python-juliapkg-project $SANDBOX_PYTHON_JULIAPKG_PROJECT"
[[ -n "$EDITABLE_FILES" ]] && RENDER_ARGS="$RENDER_ARGS --editable-files $EDITABLE_FILES"

python render_program.py $RENDER_ARGS

# ---------------------------------------------------------------------------
# Step 4: Launch Claude Code
# ---------------------------------------------------------------------------
echo ""
echo "=== Launching Claude Code agent ==="
echo "Mode: $MODE"
echo "Model: $MODEL"
echo "Max turns: $MAX_TURNS"
echo ""

claude --bare \
    -p "Read program.md and begin autonomous symbolic regression research. Do not stop." \
    --allowedTools "Read,Edit,Write,Bash" \
    --model "$MODEL" \
    --max-turns "$MAX_TURNS"
