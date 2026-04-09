#!/usr/bin/env python3
"""
Render program_template.md into program.md with mode-specific sections.
Called by launch.sh before starting the agent.
"""

import argparse
from pathlib import Path

# Mode-specific template sections

OPERATOR_SETUP = """\
   - `reference/` — API documentation for each operator type. Read these carefully.
   - `operators/` — the files you modify: `mutation.jl`, `survival.jl`, `selection.jl`."""

OPERATOR_RULES = """\
**What you CAN do:**
- Create or edit files in `operators/`:
  - `operators/mutation.jl` — custom mutation function
  - `operators/survival.jl` — custom survival function
  - `operators/selection.jl` — custom selection function

You may create, modify, or delete any of these files each iteration. If a file
doesn't exist (or is empty), the default behavior is used for that operator type.
You can modify one, two, or all three operators in a single iteration.

Read the reference docs in `reference/` for the API, function signatures, and examples:
- `reference/MUTATIONS_REFERENCE.md` — mutation operator API
- `reference/SURVIVAL_REFERENCE.md` — survival operator API
- `reference/SELECTION_REFERENCE.md` — selection operator API"""

OPERATOR_CONSTRAINTS = """\
- Do not create files outside of `operators/`."""

OPERATOR_EDIT_INSTRUCTION = """\
Edit operator files in `operators/` with an experimental idea. You can modify \
one or more of: `mutation.jl`, `survival.jl`, `selection.jl`."""

CODEBASE_SETUP = """\
   - The SymbolicRegression.jl source files you can edit (see below for full list)."""

CODEBASE_RULES = """\
**What you CAN do:**
- Edit the following Julia source files in `{SANDBOX_SR_SRC}`:

{ALLOWED_FILES_LIST}

These files contain the core symbolic regression search algorithm: mutation
operators, population dynamics, selection, survival, parsimony, complexity
scoring, and the main search loop. Everything is fair game within these files."""

CODEBASE_CONSTRAINTS = """\
- Do not edit any files outside the allowed list above.
- Do not modify files in `src/` that are not listed (e.g., `SymbolicRegression.jl`, `Options.jl`)."""

CODEBASE_EDIT_INSTRUCTION = """\
Edit the SymbolicRegression.jl source files with an experimental idea."""

METRIC_DESCRIPTIONS = {
    "gt": "ground-truth match rate (fraction of datasets where the discovered equation matches the true formula). Higher is better.",
    "r2": "R-squared on held-out validation data, averaged across datasets. Higher is better.",
}

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


def render(args):
    template = Path(args.template).read_text()

    prepare_flags_parts = [f"--split {args.split}", f"--n-runs {args.n_runs}",
                           f"--seed {args.seed}", f"--fitness-metric {args.fitness_metric}"]
    if args.max_evals:
        prepare_flags_parts.append(f"--max-evals {args.max_evals}")
    if args.timeout:
        prepare_flags_parts.append(f"--timeout {args.timeout}")
    if args.partition:
        prepare_flags_parts.append(f"--partition {args.partition}")
    if args.time_limit:
        prepare_flags_parts.append(f"--time-limit {args.time_limit}")
    if args.max_samples:
        prepare_flags_parts.append(f"--max-samples {args.max_samples}")
    if args.random_target_noise:
        prepare_flags_parts.append("--random-target-noise")

    # Mode-specific flags for prepare.py
    if args.mode == "codebase":
        if args.sandbox_root:
            prepare_flags_parts.append(f"--sandbox-root {args.sandbox_root}")
        if args.sandbox_julia_project:
            prepare_flags_parts.append(f"--sandbox-julia-project {args.sandbox_julia_project}")
        if args.sandbox_python_juliapkg_project:
            prepare_flags_parts.append(f"--sandbox-python-juliapkg-project {args.sandbox_python_juliapkg_project}")

    prepare_flags = " ".join(prepare_flags_parts)

    if args.mode == "operator":
        mode_setup = OPERATOR_SETUP
        mode_rules = OPERATOR_RULES
        mode_constraints = OPERATOR_CONSTRAINTS
        mode_edit = OPERATOR_EDIT_INSTRUCTION
    else:
        editable = args.editable_files or DEFAULT_EDITABLE_FILES
        files_list = "\n".join(f"  - `{f}`" for f in editable)
        sandbox_sr_src = f"{args.sandbox_root}/SymbolicRegression.jl/src" if args.sandbox_root else "SymbolicRegression.jl/src"
        mode_setup = CODEBASE_SETUP
        mode_rules = CODEBASE_RULES.replace("{ALLOWED_FILES_LIST}", files_list).replace("{SANDBOX_SR_SRC}", sandbox_sr_src)
        mode_constraints = CODEBASE_CONSTRAINTS
        mode_edit = CODEBASE_EDIT_INSTRUCTION

    replacements = {
        "{MODE_SETUP_SECTION}": mode_setup,
        "{MODE_RULES_SECTION}": mode_rules,
        "{MODE_CONSTRAINTS_SECTION}": mode_constraints,
        "{MODE_EDIT_INSTRUCTION}": mode_edit,
        "{MODE}": args.mode,
        "{METRIC}": args.fitness_metric,
        "{METRIC_DESCRIPTION}": METRIC_DESCRIPTIONS.get(args.fitness_metric, args.fitness_metric),
        "{BASELINE_SCORE}": args.baseline_score,
        "{PREPARE_FLAGS}": prepare_flags,
    }

    output = template
    for key, value in replacements.items():
        output = output.replace(key, value)

    output_path = Path(args.output)
    output_path.write_text(output)
    print(f"Rendered {args.output} ({len(output)} chars)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render program.md from template")
    parser.add_argument("--template", default="program_template.md")
    parser.add_argument("--output", default="program.md")
    parser.add_argument("--mode", choices=["operator", "codebase"], required=True)
    parser.add_argument("--baseline-score", type=str, required=True)

    # Evaluation flags (passed through to template)
    parser.add_argument("--split", default="../splits/train_hard.txt")
    parser.add_argument("--n-runs", type=int, default=3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fitness-metric", default="gt")
    parser.add_argument("--max-evals", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=None)
    parser.add_argument("--partition", type=str, default=None)
    parser.add_argument("--time-limit", type=str, default=None)
    parser.add_argument("--max-samples", type=int, default=None)
    parser.add_argument("--random-target-noise", action="store_true")

    # Codebase mode
    parser.add_argument("--sandbox-root", type=str, default=None)
    parser.add_argument("--sandbox-julia-project", type=str, default=None)
    parser.add_argument("--sandbox-python-juliapkg-project", type=str, default=None)
    parser.add_argument("--editable-files", nargs="*", default=None)

    args = parser.parse_args()
    render(args)
