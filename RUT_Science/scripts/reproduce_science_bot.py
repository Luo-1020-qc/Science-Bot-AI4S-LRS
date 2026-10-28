"""Reproduce frozen v1 training into a NEW output directory."""
import argparse
from pathlib import Path
import torch
from rut_science.science_bot.cache import OutcomeCache
from rut_science.science_bot.training import train_bc, train_ppo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--steps", type=int, default=20000)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory")
    torch.set_num_threads(1)
    cache = OutcomeCache()
    train_bc(args.output/"bc", cache)
    for seed in (11, 22, 33, 44, 55):
        for kind, warm in (("ppo_scratch", None), ("bc_ppo", args.output/"bc")):
            train_ppo(args.output/f"{kind}_{seed}", cache, seed, args.steps, warm)
        cache.memory.clear()
    for ablation in ("no_budget", "no_history", "no_diagnostics", "no_fault_training"):
        train_ppo(args.output/ablation, cache, 11, args.steps, args.output/"bc",
                  fault_training=ablation != "no_fault_training",
                  ablation=None if ablation == "no_fault_training" else ablation)
        cache.memory.clear()


if __name__ == "__main__":
    main()
