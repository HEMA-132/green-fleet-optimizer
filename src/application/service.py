"""Application service layer for fleet optimization."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.optimization.optimizers import differential_evolution, qpso
from src.optimization.problem import FleetOptimizationProblem, OptimizationConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = PROJECT_ROOT / "data/processed/modeling/fuel_prediction_dataset.csv"


class FleetOptimizationService:
    """Application service providing validation, context discovery, and optimization execution."""

    def __init__(self, dataset_path: str | Path = DEFAULT_DATASET) -> None:
        self.dataset_path = Path(dataset_path)
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Modeling dataset not found at {self.dataset_path}")
        self.frame = pd.read_csv(self.dataset_path)
        
        required = {
            "distance", "engine_efficiency", "ship_type", "route_id", "month",
            "fuel_type", "weather_conditions", "fuel_consumption", "co2_emissions",
        }
        missing = sorted(required.difference(self.frame.columns))
        if missing:
            raise ValueError(f"Dataset missing required columns: {missing}")
            
        self._categories = {
            name: sorted(self.frame[name].astype(str).unique().tolist())
            for name in ("ship_type", "route_id", "month", "fuel_type", "weather_conditions")
        }
        self._efficiency_min = float(self.frame["engine_efficiency"].min())
        self._efficiency_max = float(self.frame["engine_efficiency"].max())
        self._route_distances = self.frame.groupby("route_id")["distance"].median().to_dict()

    def get_available_options(self) -> dict[str, Any]:
        """Return observed metadata and categorical option bounds for application inputs."""
        return {
            "ship_types": list(self._categories["ship_type"]),
            "months": list(self._categories["month"]),
            "weather_conditions": list(self._categories["weather_conditions"]),
            "routes": list(self._categories["route_id"]),
            "fuel_types": list(self._categories["fuel_type"]),
            "engine_efficiency_bounds": (self._efficiency_min, self._efficiency_max),
            "route_distances": dict(self._route_distances),
        }

    def validate_context(
        self,
        ship_type: str | None = None,
        month: str | None = None,
        weather_conditions: str | None = None,
        engine_efficiency: float | int | None = None,
        route_id: str | None = None,
        fuel_type: str | None = None,
    ) -> dict[str, Any]:
        """Validate categorical context selections and numerical efficiency bounds."""
        validated: dict[str, Any] = {}
        if ship_type is not None:
            if str(ship_type) not in self._categories["ship_type"]:
                raise ValueError(f"Unknown ship type: {ship_type!r}. Must be one of {self._categories['ship_type']}")
            validated["ship_type"] = str(ship_type)

        if month is not None:
            if str(month) not in self._categories["month"]:
                raise ValueError(f"Invalid month: {month!r}. Must be one of {self._categories['month']}")
            validated["month"] = str(month)

        if weather_conditions is not None:
            if str(weather_conditions) not in self._categories["weather_conditions"]:
                raise ValueError(
                    f"Unknown weather condition: {weather_conditions!r}. Must be one of {self._categories['weather_conditions']}"
                )
            validated["weather_conditions"] = str(weather_conditions)

        if engine_efficiency is not None:
            try:
                eff = float(engine_efficiency)
            except (TypeError, ValueError) as err:
                raise ValueError(f"Invalid engine efficiency value: {engine_efficiency!r}") from err

            if not (self._efficiency_min <= eff <= self._efficiency_max):
                raise ValueError(
                    f"Engine efficiency {eff} is outside observed bounds [{self._efficiency_min}, {self._efficiency_max}]."
                )
            validated["engine_efficiency"] = eff

        if route_id is not None:
            if str(route_id) not in self._categories["route_id"]:
                raise ValueError(f"Unknown route: {route_id!r}. Must be one of {self._categories['route_id']}")
            validated["route_id"] = str(route_id)

        if fuel_type is not None:
            if str(fuel_type) not in self._categories["fuel_type"]:
                raise ValueError(f"Unknown fuel type: {fuel_type!r}. Must be one of {self._categories['fuel_type']}")
            validated["fuel_type"] = str(fuel_type)

        return validated

    def run_optimization(
        self,
        ship_type: str | None = None,
        month: str | None = None,
        weather_conditions: str | None = None,
        engine_efficiency: float | int | None = None,
        fuel_weight: float = 0.7,
        co2_weight: float = 0.3,
        population_size: int = 24,
        iterations: int = 40,
        seed: int = 42,
    ) -> dict[str, Any]:
        """Execute Differential Evolution and QPSO optimization under specified context."""
        self.validate_context(
            ship_type=ship_type,
            month=month,
            weather_conditions=weather_conditions,
            engine_efficiency=engine_efficiency,
        )

        config = OptimizationConfig(
            fuel_weight=fuel_weight,
            co2_weight=co2_weight,
            population_size=population_size,
            iterations=iterations,
            seed=seed,
            context_ship_type=ship_type,
            context_month=month,
            context_weather_conditions=weather_conditions,
            context_engine_efficiency=float(engine_efficiency) if engine_efficiency is not None else None,
        )

        problem = FleetOptimizationProblem(self.frame, config)
        classical = differential_evolution(problem, seed=seed)
        quantum_inspired = qpso(problem, seed=seed)

        def _format_result(res: dict[str, Any]) -> dict[str, Any]:
            solution = res["final_solution"]
            return {
                "algorithm": res["algorithm"],
                "best_objective": float(res["best_objective"]),
                "fuel_consumption": float(max(0.0, res["fuel_consumption"])),
                "co2_emissions": float(max(0.0, res["co2_emissions"])),
                "runtime_seconds": float(res["runtime_seconds"]),
                "selected_route_id": solution["route_id"],
                "selected_fuel_type": solution["fuel_type"],
                "derived_distance": float(solution["distance"]),
                "final_solution": solution,
                "convergence_history": res["convergence_history"],
            }

        de_formatted = _format_result(classical)
        qpso_formatted = _format_result(quantum_inspired)

        return {
            "problem_metadata": problem.metadata(),
            "fixed_context": problem.context,
            "decision_variables": ["route_id", "fuel_type"],
            "derived_variable": "distance (route median)",
            "results": {
                "differential_evolution": de_formatted,
                "qpso": qpso_formatted,
            },
            "disclaimer": (
                "QPSO matched the classical baseline on the optimization objective and was faster in the "
                "tested benchmark, but the experiment does not establish quantum advantage."
            ),
        }
