"""Shared fuel/CO2 optimization problem and objective."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DECISION_NAMES = ("route_id", "fuel_type")
CONTEXT_NAMES = ("ship_type", "month", "weather_conditions", "engine_efficiency")
ONE_HOT_NAMES = ("ship_type", "route_id", "fuel_type", "weather_conditions")


@dataclass(frozen=True)
class OptimizationConfig:
    fuel_weight: float = 0.7
    co2_weight: float = 0.3
    population_size: int = 24
    iterations: int = 40
    seed: int = 42
    context_ship_type: str | None = None
    context_month: str | None = None
    context_weather_conditions: str | None = None
    context_engine_efficiency: float | None = None

    def __post_init__(self) -> None:
        if self.fuel_weight < 0 or self.co2_weight < 0:
            raise ValueError("Objective weights must be non-negative.")
        if self.fuel_weight + self.co2_weight <= 0:
            raise ValueError("At least one objective weight must be positive.")
        if self.population_size < 4 or self.iterations < 1:
            raise ValueError("Population size must be at least 4 and iterations positive.")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class FleetOptimizationProblem:
    """Optimize route and fuel type under fixed observed operating context.

    Distance is derived from the observed median for the selected route. Ship type,
    month, weather, and engine efficiency remain contextual and cannot be changed.
    """

    def __init__(self, frame: pd.DataFrame, config: OptimizationConfig | None = None) -> None:
        self.config = config or OptimizationConfig()
        required = {
            "distance", "engine_efficiency", "ship_type", "route_id", "month",
            "fuel_type", "weather_conditions", "fuel_consumption", "co2_emissions",
        }
        missing = sorted(required.difference(frame.columns))
        if missing:
            raise ValueError(f"Optimization data is missing required columns: {missing}")
        self.frame = frame.copy()
        numeric = self.frame[["distance", "engine_efficiency", "fuel_consumption", "co2_emissions"]].apply(
            pd.to_numeric, errors="coerce"
        )
        if numeric.isna().any().any():
            raise ValueError("Optimization data contains missing or non-numeric required numeric values.")
        self.frame[numeric.columns] = numeric
        self.month_numbers = {
            month: number for number, month in enumerate(
                ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"],
                start=1,
            )
        }
        self.categories = {
            name: sorted(self.frame[name].astype(str).unique().tolist())
            for name in ("route_id", "fuel_type", "ship_type", "month", "weather_conditions")
        }
        self.route_distances = self.frame.groupby("route_id")["distance"].median().to_dict()
        self.context = self._resolve_context()
        self.bounds = np.array([
            [0.0, float(len(self.categories["route_id"]) - 1)],
            [0.0, float(len(self.categories["fuel_type"]) - 1)],
        ])
        self.target_scales = {
            "fuel_consumption": float(self.frame["fuel_consumption"].mean()),
            "co2_emissions": float(self.frame["co2_emissions"].mean()),
        }
        design = self._design_frame(self.frame)
        matrix = np.column_stack([np.ones(len(design)), design.to_numpy(dtype=float)])
        self._feature_columns = list(design.columns)
        self._fuel_coefficients = np.linalg.lstsq(
            matrix, np.log1p(self.frame["fuel_consumption"].to_numpy(dtype=float)), rcond=None
        )[0]
        self._co2_coefficients = np.linalg.lstsq(
            matrix, np.log1p(self.frame["co2_emissions"].to_numpy(dtype=float)), rcond=None
        )[0]

    def _resolve_context(self) -> dict[str, Any]:
        def mode(column: str) -> str:
            return str(self.frame[column].mode().sort_values().iloc[0])

        context = {
            "ship_type": self.config.context_ship_type or mode("ship_type"),
            "month": self.config.context_month or mode("month"),
            "weather_conditions": self.config.context_weather_conditions or mode("weather_conditions"),
            "engine_efficiency": self.config.context_engine_efficiency
            if self.config.context_engine_efficiency is not None
            else float(self.frame["engine_efficiency"].median()),
        }
        for column in ("ship_type", "month", "weather_conditions"):
            if context[column] not in set(self.frame[column].astype(str)):
                raise ValueError(f"Context value {context[column]!r} is not present in {column}.")
        efficiency = float(context["engine_efficiency"])
        if not self.frame["engine_efficiency"].between(efficiency, efficiency).all():
            minimum = float(self.frame["engine_efficiency"].min())
            maximum = float(self.frame["engine_efficiency"].max())
            if not minimum <= efficiency <= maximum:
                raise ValueError("context_engine_efficiency must be within observed bounds.")
        return context

    def _decode(self, vector: np.ndarray) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for index, name in enumerate(DECISION_NAMES):
            category_index = int(np.clip(np.rint(vector[index]), 0, len(self.categories[name]) - 1))
            values[name] = self.categories[name][category_index]
        values["distance"] = float(self.route_distances[values["route_id"]])
        values.update(self.context)
        return values

    def _design_frame(self, scenarios: pd.DataFrame) -> pd.DataFrame:
        design = scenarios[list(DECISION_NAMES) + ["distance", *CONTEXT_NAMES]].copy()
        design["month_number"] = design["month"].map(self.month_numbers).fillna(1)
        design["distance_per_efficiency"] = design["distance"].div(
            design["engine_efficiency"].where(design["engine_efficiency"].ne(0))
        )
        design["efficiency_inverse"] = design["engine_efficiency"].where(
            design["engine_efficiency"].ne(0)
        ).rdiv(1)
        design = design.drop(columns=["month"])
        design = pd.get_dummies(design, columns=list(ONE_HOT_NAMES), dtype=float)
        return design.reindex(columns=self._feature_columns, fill_value=0.0) if hasattr(self, "_feature_columns") else design

    def decode(self, vector: np.ndarray) -> dict[str, Any]:
        return self._decode(np.asarray(vector, dtype=float))

    def _scenario_design_vector(self, scenario: dict[str, Any]) -> np.ndarray:
        values = np.zeros(len(self._feature_columns), dtype=float)
        positions = {column: index for index, column in enumerate(self._feature_columns)}
        values[positions["distance"]] = scenario["distance"]
        values[positions["engine_efficiency"]] = scenario["engine_efficiency"]
        values[positions["month_number"]] = self.month_numbers[scenario["month"]]
        values[positions["distance_per_efficiency"]] = scenario["distance"] / scenario["engine_efficiency"]
        values[positions["efficiency_inverse"]] = 1.0 / scenario["engine_efficiency"]
        for name in ONE_HOT_NAMES:
            column = f"{name}_{scenario[name]}"
            if column in positions:
                values[positions[column]] = 1.0
        return values

    def evaluate(self, vector: np.ndarray) -> dict[str, Any]:
        vector = np.asarray(vector, dtype=float)
        if vector.shape != (len(DECISION_NAMES),) or np.any(vector < self.bounds[:, 0]) or np.any(vector > self.bounds[:, 1]):
            return {"objective": float("inf"), "fuel_consumption": float("inf"), "co2_emissions": float("inf"), "feasible": False}
        row = np.concatenate([[1.0], self._scenario_design_vector(self._decode(vector))])
        fuel = float(np.expm1(row @ self._fuel_coefficients))
        co2 = float(np.expm1(row @ self._co2_coefficients))
        objective = (
            self.config.fuel_weight * fuel / self.target_scales["fuel_consumption"]
            + self.config.co2_weight * co2 / self.target_scales["co2_emissions"]
        )
        return {
            "objective": float(objective),
            "fuel_consumption": fuel,
            "co2_emissions": co2,
            "feasible": True,
        }

    def bounds_list(self) -> list[tuple[float, float]]:
        return [tuple(bound) for bound in self.bounds]

    def metadata(self) -> dict[str, Any]:
        return {
            "decision_names": list(DECISION_NAMES),
            "context_names": list(CONTEXT_NAMES),
            "fixed_context": self.context,
            "route_distance_medians": self.route_distances,
            "categories": self.categories,
            "bounds": self.bounds_list(),
            "objective": "weighted normalized surrogate fuel consumption and CO2 emissions",
            "target_scales": self.target_scales,
            "config": self.config.as_dict(),
            "assumptions": [
                "Route is controllable and determines distance by observed route median.",
                "Fuel type is controllable among observed fuel categories.",
                "Ship selection is unsupported because no fleet-assignment data exists.",
                "Month, weather, ship type, and engine efficiency are fixed context.",
                "Marine observations are not joined to fuel records.",
            ],
            "limitations": [
                "Engine efficiency is not treated as a controllable setting because causality is not established.",
                "Route median is descriptive, not a navigational distance guarantee.",
                "Results are surrogate experiments, not operational recommendations.",
            ],
            "marine_joined": False,
        }
