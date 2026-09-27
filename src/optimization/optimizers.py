"""Deterministic classical and quantum-inspired optimizers."""

from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np

from .problem import FleetOptimizationProblem


def _result(
    algorithm: str,
    problem: FleetOptimizationProblem,
    best_vector: np.ndarray,
    history: list[dict[str, float]],
    runtime_seconds: float,
) -> dict[str, Any]:
    evaluation = problem.evaluate(best_vector)
    return {
        "algorithm": algorithm,
        "best_objective": evaluation["objective"],
        "fuel_consumption": evaluation["fuel_consumption"],
        "co2_emissions": evaluation["co2_emissions"],
        "runtime_seconds": runtime_seconds,
        "iterations": len(history),
        "convergence_history": history,
        "final_solution": problem.decode(best_vector),
        "final_vector": [float(value) for value in best_vector],
        "config": problem.metadata(),
    }


def differential_evolution(
    problem: FleetOptimizationProblem,
    seed: int | None = None,
) -> dict[str, Any]:
    """Use deterministic Differential Evolution as the classical baseline."""
    started = time.perf_counter()
    rng = np.random.default_rng(problem.config.seed if seed is None else seed)
    bounds = np.asarray(problem.bounds_list(), dtype=float)
    population = rng.uniform(bounds[:, 0], bounds[:, 1], size=(problem.config.population_size, len(bounds)))
    scores = np.array([problem.evaluate(vector)["objective"] for vector in population])
    best_index = int(np.argmin(scores))
    best_vector = population[best_index].copy()
    best_score = float(scores[best_index])
    history: list[dict[str, float]] = []

    for iteration in range(problem.config.iterations):
        for index in range(len(population)):
            candidates = [candidate for candidate in range(len(population)) if candidate != index]
            a, b, c = rng.choice(candidates, size=3, replace=False)
            mutant = population[a] + 0.8 * (population[b] - population[c])
            mutant = np.clip(mutant, bounds[:, 0], bounds[:, 1])
            crossover = rng.random(len(bounds)) < 0.9
            crossover[rng.integers(0, len(bounds))] = True
            trial = np.where(crossover, mutant, population[index])
            trial_score = problem.evaluate(trial)["objective"]
            if trial_score <= scores[index]:
                population[index] = trial
                scores[index] = trial_score
                if trial_score < best_score:
                    best_score = float(trial_score)
                    best_vector = trial.copy()
        history.append({"iteration": float(iteration + 1), "best_objective": best_score})

    return _result("differential_evolution", problem, best_vector, history, time.perf_counter() - started)


def qpso(
    problem: FleetOptimizationProblem,
    seed: int | None = None,
) -> dict[str, Any]:
    """Run Quantum Particle Swarm Optimization with bounded particles."""
    started = time.perf_counter()
    rng = np.random.default_rng(problem.config.seed if seed is None else seed)
    bounds = np.asarray(problem.bounds_list(), dtype=float)
    particles = rng.uniform(bounds[:, 0], bounds[:, 1], size=(problem.config.population_size, len(bounds)))
    personal_best = particles.copy()
    personal_scores = np.array([problem.evaluate(vector)["objective"] for vector in particles])
    global_index = int(np.argmin(personal_scores))
    global_best = personal_best[global_index].copy()
    global_score = float(personal_scores[global_index])
    history: list[dict[str, float]] = []

    for iteration in range(problem.config.iterations):
        mbest = personal_best.mean(axis=0)
        alpha = 1.0 - 0.5 * ((iteration + 1) / problem.config.iterations)
        for index in range(len(particles)):
            attractor_weight = rng.random(len(bounds))
            attractor = attractor_weight * personal_best[index] + (1.0 - attractor_weight) * global_best
            direction = np.where(rng.random(len(bounds)) < 0.5, -1.0, 1.0)
            step = alpha * np.abs(mbest - particles[index]) * np.log(1.0 / np.maximum(rng.random(len(bounds)), 1e-12))
            particles[index] = np.clip(attractor + direction * step, bounds[:, 0], bounds[:, 1])
            score = problem.evaluate(particles[index])["objective"]
            if score < personal_scores[index]:
                personal_best[index] = particles[index].copy()
                personal_scores[index] = score
                if score < global_score:
                    global_best = particles[index].copy()
                    global_score = float(score)
        history.append({"iteration": float(iteration + 1), "best_objective": global_score})

    return _result("qpso", problem, global_best, history, time.perf_counter() - started)
