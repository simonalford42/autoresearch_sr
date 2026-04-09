#!/usr/bin/env bash

 # job name
#SBATCH -J autoresearch_sr
 # output file
#SBATCH -o out/%j.out
#SBATCH -e out/%j.out
 # total nodes
#SBATCH -N 1
 # total cores
#SBATCH -n 1
#SBATCH --requeue
 # total limit (hh:mm:ss)
#SBATCH -t 48:00:00
#SBATCH --mem=4G
#SBATCH --partition=ellis

source /home/sca63/mambaforge/etc/profile.d/conda.sh
conda activate meta_sr_agent_loop

mkdir -p "${PWD}/out"

claude --bare --dangerously-skip-permissions \
    -p "Read program.md and begin autonomous symbolic regression research. Do not stop." \
    --model sonnet-4-6 \
    2>&1 | tee "out/run_$(date +%Y%m%d_%H%M%S).log"
