"""Common experiment runner for classical and QPSO comparisons."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .optimizers import differential_evolution, qpso
from .problem import FleetOptimizationProblem, OptimizationConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = PROJECT_ROOT / "data/processed/modeling/fuel_prediction_dataset.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data/processed/optimization"
DEFAULT_BENCHMARK_SEEDS = (11, 22, 33, 44, 55)


def _improvement(classical_mean: float, qpso_mean: float) -> float:
    if classical_mean == 0:
        return float("nan")
    return (classical_mean - qpso_mean) / classical_mean * 100.0


def _benchmark_record(result: dict[str, Any], seed: int, config: OptimizationConfig) -> dict[str, Any]:
    solution = result["final_solution"]
    return {
        "seed": seed,
        "optimizer": result["algorithm"],
        "best_objective": result["best_objective"],
        "predicted_fuel_consumption": result["fuel_consumption"],
        "predicted_co2_emissions": result["co2_emissions"],
        "selected_route_id": solution["route_id"],
        "selected_fuel_type": solution["fuel_type"],
        "derived_distance": solution["distance"],
        "runtime_seconds": result["runtime_seconds"],
        "iterations": config.iterations,
        "evaluation_count": config.population_size * (config.iterations + 1),
    }


def _aggregate_benchmark(records: pd.DataFrame) -> dict[str, Any]:
    aggregate: dict[str, Any] = {}
    for optimizer, group in records.groupby("optimizer", sort=True):
        aggregate[optimizer] = {
            "mean_objective": float(group["best_objective"].mean()),
            "std_objective": float(group["best_objective"].std(ddof=1)),
            "min_objective": float(group["best_objective"].min()),
            "max_objective": float(group["best_objective"].max()),
            "mean_predicted_fuel_consumption": float(group["predicted_fuel_consumption"].mean()),
            "mean_predicted_co2_emissions": float(group["predicted_co2_emissions"].mean()),
            "mean_runtime_seconds": float(group["runtime_seconds"].mean()),
        }
    classical = aggregate["differential_evolution"]
    qpso_result = aggregate["qpso"]
    paired = records.pivot(index="seed", columns="optimizer", values="best_objective")
    paired_difference = paired["qpso"] - paired["differential_evolution"]
    paired_analysis = {
        "objective_difference_qpso_minus_classical_by_seed": {
            str(seed): float(value) for seed, value in paired_difference.items()
        },
        "mean_difference": float(paired_difference.mean()),
        "std_difference": float(paired_difference.std(ddof=1)),
        "note": "Descriptive paired comparison across five seeds; inferential significance is not asserted.",
    }
    return {
        "by_optimizer": aggregate,
        "improvement_percent_qpso_vs_classical": {
            "objective": _improvement(classical["mean_objective"], qpso_result["mean_objective"]),
            "predicted_fuel_consumption": _improvement(
                classical["mean_predicted_fuel_consumption"],
                qpso_result["mean_predicted_fuel_consumption"],
            ),
            "predicted_co2_emissions": _improvement(
                classical["mean_predicted_co2_emissions"],
                qpso_result["mean_predicted_co2_emissions"],
            ),
            "runtime_seconds": _improvement(
                classical["mean_runtime_seconds"],
                qpso_result["mean_runtime_seconds"],
            ),
            "runtime_interpretation": "positive means QPSO is faster; negative means QPSO is slower",
        },
        "paired_objective_analysis": paired_analysis,
    }


def run_benchmark(
    dataset_path: str | Path = DEFAULT_DATASET,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    seeds: tuple[int, ...] = DEFAULT_BENCHMARK_SEEDS,
    config: OptimizationConfig | None = None,
) -> dict[str, Any]:
    """Run a paired multi-seed quantum-inspired performance comparison."""
    config = config or OptimizationConfig(population_size=30, iterations=50)
    if not seeds:
        raise ValueError("At least one benchmark seed is required.")
    frame = pd.read_csv(dataset_path)
    problem = FleetOptimizationProblem(frame, config)
    records: list[dict[str, Any]] = []
    convergence_records: list[dict[str, Any]] = []
    for seed in seeds:
        for optimizer in (differential_evolution, qpso):
            result = optimizer(problem, seed=seed)
            records.append(_benchmark_record(result, seed, config))
            convergence_records.extend(
                {
                    "seed": seed,
                    "optimizer": result["algorithm"],
                    **point,
                }
                for point in result["convergence_history"]
            )

    benchmark = pd.DataFrame(records)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    benchmark.to_csv(output / "benchmark_results.csv", index=False)
    pd.DataFrame(convergence_records).to_csv(output / "benchmark_convergence.csv", index=False)
    summary = {
        "benchmark_type": "quantum-inspired performance comparison",
        "dataset_path": str(dataset_path),
        "seeds": list(seeds),
        "configuration": config.as_dict(),
        "evaluation_count_per_run": config.population_size * (config.iterations + 1),
        "problem": problem.metadata(),
        "aggregate": _aggregate_benchmark(benchmark),
        "paired_seed_count": len(seeds),
        "statistical_note": "Five paired seeds support descriptive comparison only; no superiority claim is made.",
    }
    (output / "benchmark_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {"records": benchmark, "summary": summary, "output_dir": str(output)}


def run_experiment(
    dataset_path: str | Path = DEFAULT_DATASET,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    config: OptimizationConfig | None = None,
) -> dict[str, Any]:
    """Run both optimizers with the same problem, configuration, and objective."""
    config = config or OptimizationConfig()
    frame = pd.read_csv(dataset_path)
    problem = FleetOptimizationProblem(frame, config)
    classical = differential_evolution(problem, seed=config.seed)
    quantum_inspired = qpso(problem, seed=config.seed)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    results = [classical, quantum_inspired]
    (output / "optimization_results.json").write_text(
        json.dumps({"problem": problem.metadata(), "results": results}, indent=2),
        encoding="utf-8",
    )
    convergence = pd.DataFrame(
        [
            {
                "algorithm": result["algorithm"],
                **point,
            }
            for result in results
            for point in result["convergence_history"]
        ]
    )
    convergence.to_csv(output / "convergence_history.csv", index=False)
    return {"problem": problem.metadata(), "results": results, "output_dir": str(output)}


if __name__ == "__main__":
    run_benchmark()
