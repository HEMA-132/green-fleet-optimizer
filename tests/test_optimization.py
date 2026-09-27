import json

import numpy as np
import pandas as pd

from src.optimization.experiment import run_benchmark, run_experiment
from src.optimization.optimizers import differential_evolution, qpso
from src.optimization.problem import FleetOptimizationProblem, OptimizationConfig


def sample_frame():
    return pd.DataFrame(
        [
            {"distance": 50, "engine_efficiency": 70, "ship_type": "Tanker", "route_id": "R1", "month": "January", "fuel_type": "Diesel", "weather_conditions": "Calm", "fuel_consumption": 100, "co2_emissions": 300},
            {"distance": 100, "engine_efficiency": 80, "ship_type": "Tanker", "route_id": "R2", "month": "June", "fuel_type": "HFO", "weather_conditions": "Stormy", "fuel_consumption": 180, "co2_emissions": 550},
            {"distance": 150, "engine_efficiency": 90, "ship_type": "Trawler", "route_id": "R1", "month": "December", "fuel_type": "Diesel", "weather_conditions": "Moderate", "fuel_consumption": 220, "co2_emissions": 650},
            {"distance": 80, "engine_efficiency": 75, "ship_type": "Trawler", "route_id": "R2", "month": "March", "fuel_type": "HFO", "weather_conditions": "Calm", "fuel_consumption": 140, "co2_emissions": 420},
        ]
    )


def test_objective_uses_shared_weighted_outputs():
    problem = FleetOptimizationProblem(sample_frame(), OptimizationConfig(population_size=4, iterations=2))
    vector = np.array([0, 0], dtype=float)
    result = problem.evaluate(vector)
    assert result["feasible"]
    assert result["objective"] == (
        0.7 * result["fuel_consumption"] / problem.target_scales["fuel_consumption"]
        + 0.3 * result["co2_emissions"] / problem.target_scales["co2_emissions"]
    )


def test_constraint_handling_rejects_out_of_bounds():
    problem = FleetOptimizationProblem(sample_frame())
    result = problem.evaluate(np.full(2, 10_000.0))
    assert not result["feasible"]
    assert np.isinf(result["objective"])


def test_decisions_context_and_route_distance_are_explicit():
    problem = FleetOptimizationProblem(sample_frame())
    assert problem.metadata()["decision_names"] == ["route_id", "fuel_type"]
    assert "weather_conditions" in problem.metadata()["context_names"]
    solution = problem.decode(np.array([0.0, 0.0]))
    assert solution["fuel_type"] in problem.categories["fuel_type"]
    assert solution["route_id"] in problem.categories["route_id"]
    assert solution["distance"] == problem.route_distances[solution["route_id"]]


def test_context_cannot_be_manipulated_by_optimizer_vector():
    problem = FleetOptimizationProblem(sample_frame())
    first = problem.decode(np.array([0.0, 0.0]))
    second = problem.decode(np.array([1.0, 1.0]))
    for name in ("ship_type", "month", "weather_conditions", "engine_efficiency"):
        assert first[name] == second[name] == problem.context[name]


def test_both_optimizers_use_same_problem_objective_and_physical_bounds():
    config = OptimizationConfig(population_size=8, iterations=3, seed=7)
    problem = FleetOptimizationProblem(sample_frame(), config)
    classical = differential_evolution(problem, seed=7)
    quantum = qpso(problem, seed=7)
    assert classical["config"]["objective"] == quantum["config"]["objective"]
    for result in (classical, quantum):
        solution = result["final_solution"]
        assert solution["distance"] in problem.route_distances.values()
        assert solution["fuel_type"] in problem.categories["fuel_type"]
        assert solution["engine_efficiency"] == problem.context["engine_efficiency"]
        assert result["fuel_consumption"] >= 0
        assert result["co2_emissions"] >= 0


def test_both_optimizers_are_deterministic_with_fixed_seed():
    config = OptimizationConfig(population_size=8, iterations=4, seed=7)
    problem = FleetOptimizationProblem(sample_frame(), config)
    classical_a = differential_evolution(problem, seed=7)
    classical_b = differential_evolution(problem, seed=7)
    qpso_a = qpso(problem, seed=7)
    qpso_b = qpso(problem, seed=7)
    assert classical_a["final_vector"] == classical_b["final_vector"]
    assert qpso_a["final_vector"] == qpso_b["final_vector"]
    assert len(qpso_a["convergence_history"]) == config.iterations


def test_experiment_result_schema_and_artifacts(tmp_path):
    dataset = tmp_path / "modeling.csv"
    sample_frame().to_csv(dataset, index=False)
    result = run_experiment(dataset, tmp_path / "results", OptimizationConfig(population_size=8, iterations=3))
    saved = json.loads((tmp_path / "results" / "optimization_results.json").read_text())
    assert {item["algorithm"] for item in result["results"]} == {"differential_evolution", "qpso"}
    assert {item["algorithm"] for item in saved["results"]} == {"differential_evolution", "qpso"}
    assert (tmp_path / "results" / "convergence_history.csv").exists()
    for item in result["results"]:
        assert "fuel_consumption" in item
        assert "co2_emissions" in item
        assert "final_solution" in item
        assert "config" in item


def test_benchmark_executes_all_seeds_and_writes_schema(tmp_path):
    dataset = tmp_path / "modeling.csv"
    sample_frame().to_csv(dataset, index=False)
    config = OptimizationConfig(population_size=8, iterations=3, seed=42)
    result = run_benchmark(dataset, tmp_path / "benchmark", seeds=(11, 22, 33), config=config)
    records = result["records"]
    assert set(records["seed"]) == {11, 22, 33}
    assert set(records["optimizer"]) == {"differential_evolution", "qpso"}
    assert len(records) == 6
    assert not records.isna().any().any()
    assert set(records["evaluation_count"]) == {32}
    assert (tmp_path / "benchmark" / "benchmark_results.csv").exists()
    assert (tmp_path / "benchmark" / "benchmark_summary.json").exists()
    assert (tmp_path / "benchmark" / "benchmark_convergence.csv").exists()


def test_benchmark_reproducibility_and_improvement_calculation(tmp_path):
    dataset = tmp_path / "modeling.csv"
    sample_frame().to_csv(dataset, index=False)
    config = OptimizationConfig(population_size=8, iterations=3, seed=42)
    first = run_benchmark(dataset, tmp_path / "first", seeds=(11, 22), config=config)
    second = run_benchmark(dataset, tmp_path / "second", seeds=(11, 22), config=config)
    first_records = first["records"].drop(columns=["runtime_seconds"])
    second_records = second["records"].drop(columns=["runtime_seconds"])
    pd.testing.assert_frame_equal(first_records, second_records)
    improvement = first["summary"]["aggregate"]["improvement_percent_qpso_vs_classical"]
    classical = first["summary"]["aggregate"]["by_optimizer"]["differential_evolution"]["mean_objective"]
    qpso_result = first["summary"]["aggregate"]["by_optimizer"]["qpso"]["mean_objective"]
    assert improvement["objective"] == (classical - qpso_result) / classical * 100
    assert "positive means QPSO is faster" in improvement["runtime_interpretation"]
