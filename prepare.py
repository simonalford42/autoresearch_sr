"""
Evaluation harness for autoresearch_sr experiments.
Wraps PySR SLURM evaluation — this file is READ-ONLY for the agent.

Operator mode:
    Reads Julia operator files from operators/ directory,
    builds PySRConfig, evaluates via SLURM, reports score.

Codebase mode:
    Evaluates the sandbox SymbolicRegression.jl as-is (agent edits .jl files directly).

Usage:
    python prepare.py --mode operator [flags]
    python prepare.py --mode codebase --sandbox-root /path/to/sandbox [flags]
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Import from parent meta_sr repo
META_SR_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(META_SR_ROOT))

from parallel_eval_pysr import (
    PySRConfig,
    PySRSlurmEvaluator,
    get_default_mutation_weights,
    get_default_pysr_kwargs,
)
from evolve_pysr import (
    _build_target_noise_map,
    _evaluate_configs_with_noise_map,
    pre_validate_julia_syntax,
)
from utils import load_dataset_names_from_split

# ---------------------------------------------------------------------------
# Constants (fixed, do not modify)
# ---------------------------------------------------------------------------

TARGET_NOISE_LEVELS = [0.0, 0.001, 0.01, 0.1]

DEFAULT_EDITABLE_FILES = [
    "AdaptiveParsimony.jl",
    "RegularizedEvolution.jl",
    "SingleIteration.jl",
    "Mutate.jl",
    "MutationFunctions.jl",
    "MutationWeights.jl",
    "ConstantOptimization.jl",
    "SearchUtils.jl",
    "HallOfFame.jl",
    "Population.jl",
    "PopMember.jl",
    "Complexity.jl",
    "CheckConstraints.jl",
]

# ---------------------------------------------------------------------------
# Operator file reading
# ---------------------------------------------------------------------------

def read_operator_file(path: Path) -> str | None:
    """Read an operator .jl file if it exists and is non-empty."""
    if path.exists():
        code = path.read_text().strip()
        return code if code else None
    return None


def build_operator_config(operators_dir: Path, pysr_kwargs: dict) -> PySRConfig:
    """Build a PySRConfig from operator files in the workspace."""
    mutation_code_str = read_operator_file(operators_dir / "mutation.jl")
    survival_code_str = read_operator_file(operators_dir / "survival.jl")
    selection_code_str = read_operator_file(operators_dir / "selection.jl")

    mutation_weights = get_default_mutation_weights()
    custom_mutation_code = None
    allow_custom_mutations = False

    if mutation_code_str:
        # Extract function name for the mutation dict
        import re
        match = re.search(r'function\s+(\w+)\s*\(', mutation_code_str)
        name = match.group(1) if match else "custom_mutation"
        custom_mutation_code = {name: mutation_code_str}
        mutation_weights["weight_custom_mutation_1"] = 0.5
        allow_custom_mutations = True

    return PySRConfig(
        mutation_weights=mutation_weights,
        pysr_kwargs=pysr_kwargs,
        custom_mutation_code=custom_mutation_code,
        allow_custom_mutations=allow_custom_mutations,
        custom_selection_code=selection_code_str,
        custom_survival_code=survival_code_str,
        name="agent_candidate",
    )


def build_baseline_config(pysr_kwargs: dict) -> PySRConfig:
    """Build a baseline PySRConfig (no custom operators)."""
    mutation_weights = get_default_mutation_weights()
    return PySRConfig(
        mutation_weights=mutation_weights,
        pysr_kwargs=pysr_kwargs,
        name="baseline",
    )


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def run_evaluation(args):
    """Run PySR evaluation and print results."""

    dataset_names = load_dataset_names_from_split(args.split)
    pysr_kwargs = get_default_pysr_kwargs()
    if args.max_evals:
        pysr_kwargs["max_evals"] = args.max_evals
    if args.timeout:
        pysr_kwargs["timeout_in_seconds"] = args.timeout

    # Build noise map
    target_noise_map = None
    if args.random_target_noise:
        target_noise_map = _build_target_noise_map(
            dataset_names, args.seed, TARGET_NOISE_LEVELS
        )

    # Determine repo root and isolation paths
    if args.mode == "codebase":
        repo_root = args.sandbox_root
        julia_project = args.sandbox_julia_project or str(
            Path(args.sandbox_root) / "SymbolicRegression.jl"
        )
        python_juliapkg_project = args.sandbox_python_juliapkg_project
    else:
        # Operator mode: use the main meta_sr repo
        repo_root = str(META_SR_ROOT)
        julia_project = args.julia_project or str(
            META_SR_ROOT / "SymbolicRegression.jl"
        )
        python_juliapkg_project = args.python_juliapkg_project

    evaluator = PySRSlurmEvaluator(
        results_dir=args.results_dir or str(Path.cwd() / "eval_results"),
        partition=args.partition,
        time_limit=args.time_limit,
        mem_per_cpu=args.mem_per_cpu,
        dataset_max_samples=args.max_samples,
        data_seed=args.seed,
        max_retries=2,
        job_timeout=args.job_timeout,
        use_cache=not args.no_cache,
        repo_root=repo_root,
        julia_project=julia_project,
        python_juliapkg_project=python_juliapkg_project,
        julia_depot_path=args.julia_depot_path,
    )

    # Build config
    if args.mode == "operator":
        operators_dir = Path(args.operators_dir)
        config = build_operator_config(operators_dir, pysr_kwargs)

        # Validate operator files
        for op_file in ["mutation.jl", "survival.jl", "selection.jl"]:
            code = read_operator_file(operators_dir / op_file)
            if code:
                ok, msg = pre_validate_julia_syntax(code)
                if not ok:
                    print(f"SYNTAX_ERROR: {op_file}: {msg}")
                    sys.exit(1)

        # Print what operators are active
        has_mutation = config.custom_mutation_code is not None
        has_survival = config.custom_survival_code is not None
        has_selection = config.custom_selection_code is not None
        print(f"Operators: mutation={'custom' if has_mutation else 'default'}, "
              f"survival={'custom' if has_survival else 'default'}, "
              f"selection={'custom' if has_selection else 'default'}")
    elif args.mode == "codebase":
        config = build_baseline_config(pysr_kwargs)
        print(f"Codebase mode: evaluating sandbox at {repo_root}")
    elif args.mode == "baseline":
        config = build_baseline_config(pysr_kwargs)
        print("Baseline mode: evaluating unmodified PySR")
    else:
        print(f"Unknown mode: {args.mode}")
        sys.exit(1)

    # Run evaluation
    print(f"Evaluating on {len(dataset_names)} datasets, {args.n_runs} runs each...")
    print(f"Fitness metric: {args.fitness_metric}")
    print()

    try:
        results = _evaluate_configs_with_noise_map(
            evaluator,
            [config],
            dataset_names,
            args.seed,
            args.n_runs,
            target_noise_map,
            args.fitness_metric,
        )
    except Exception as e:
        print(f"EVAL_ERROR: {e}")
        sys.exit(2)

    avg_score, score_vector, result_details = results[0]

    # Print per-dataset results
    print("\n--- Per-dataset results ---")
    for detail in result_details:
        ds = detail.get("dataset_name", "?")
        ds_score = detail.get("avg_score", detail.get("avg_r2", "?"))
        print(f"  {ds}: {ds_score}")

    # Print the key result line (agent greps for this)
    print(f"\n---")
    print(f"score:    {avg_score:.6f}")
    print(f"datasets: {len(dataset_names)}")
    print(f"metric:   {args.fitness_metric}")
    print(f"n_runs:   {args.n_runs}")
    print(f"---")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Evaluation harness for autoresearch_sr (DO NOT MODIFY)"
    )

    # Mode
    parser.add_argument(
        "--mode", choices=["operator", "codebase", "baseline"],
        required=True,
        help="operator: evaluate operators/*.jl files. "
             "codebase: evaluate sandbox SR.jl. "
             "baseline: evaluate unmodified PySR."
    )

    # Operator mode
    parser.add_argument(
        "--operators-dir", type=str, default="operators",
        help="Directory containing operator .jl files (operator mode)"
    )

    # Codebase mode / isolation
    parser.add_argument("--sandbox-root", type=str, default=None)
    parser.add_argument("--sandbox-julia-project", type=str, default=None)
    parser.add_argument("--sandbox-python-juliapkg-project", type=str, default=None)
    parser.add_argument("--julia-project", type=str, default=None)
    parser.add_argument("--python-juliapkg-project", type=str, default=None)
    parser.add_argument("--julia-depot-path", type=str, default=None)

    # Evaluation settings
    parser.add_argument("--split", type=str, default="../splits/train_hard.txt")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-runs", type=int, default=3)
    parser.add_argument("--fitness-metric", type=str, default="gt",
                        choices=["r2", "gt"])
    parser.add_argument("--max-evals", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--max-samples", type=int, default=1000)
    parser.add_argument("--random-target-noise", action="store_true")

    # SLURM settings
    parser.add_argument("--partition", type=str, default="default_partition")
    parser.add_argument("--time-limit", type=str, default="04:00:00")
    parser.add_argument("--mem-per-cpu", type=str, default="8G")
    parser.add_argument("--job-timeout", type=float, default=600.0)
    parser.add_argument("--results-dir", type=str, default=None)
    parser.add_argument("--no-cache", action="store_true")

    args = parser.parse_args()
    run_evaluation(args)
