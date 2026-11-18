#!/bin/bash
# Transport scan on Stoat: one array element for each line of inputs.txt.
#PBS -N transport
#PBS -q batch
#PBS -A nucth
#PBS -l nodes=1:ppn=12
#PBS -l mem=24gb
#PBS -l walltime=03:00:00
#PBS -t 1-36%4
#PBS -j oe
#PBS -o logs/
set -euo pipefail

cd "$PBS_O_WORKDIR"
module purge
module load python/3.9.6

export OMP_NUM_THREADS=$PBS_NUM_PPN
config=$(sed -n "${PBS_ARRAYID}p" inputs.txt)
python transport.py "$config"
