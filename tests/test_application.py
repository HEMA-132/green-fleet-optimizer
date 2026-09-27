import pytest
import pandas as pd
from pathlib import Path

from src.application.service import FleetOptimizationService, DEFAULT_DATASET


def test_service_initialization_and_options():
    service = FleetOptimizationService(DEFAULT_DATASET)
    options = service.get_available_options()
    
    assert "ship_types" in options
    assert "months" in options
    assert "weather_conditions" in options
    assert "routes" in options
    assert "fuel_types" in options
    assert "engine_efficiency_bounds" in options
    assert "route_distances" in options

    min_eff, max_eff = options["engine_efficiency_bounds"]
    assert min_eff < max_eff
    assert len(options["ship_types"]) > 0
    assert len(options["routes"]) > 0


def test_valid_input_handling_and_context_validation():
    service = FleetOptimizationService(DEFAULT_DATASET)
    options = service.get_available_options()
    
    valid_ship = options["ship_types"][0]
    valid_month = options["months"][0]
    valid_weather = options["weather_conditions"][0]
    min_eff, max_eff = options["engine_efficiency_bounds"]
    valid_eff = (min_eff + max_eff) / 2.0

    validated = service.validate_context(
        ship_type=valid_ship,
        month=valid_month,
        weather_conditions=valid_weather,
        engine_efficiency=valid_eff,
    )
    
    assert validated["ship_type"] == valid_ship
    assert validated["month"] == valid_month
    assert validated["weather_conditions"] == valid_weather
    assert validated["engine_efficiency"] == valid_eff


def test_invalid_categorical_input_rejection():
    service = FleetOptimizationService(DEFAULT_DATASET)
    
    with pytest.raises(ValueError, match="Unknown ship type"):
        service.validate_context(ship_type="NonExistentShip")

    with pytest.raises(ValueError, match="Invalid month"):
        service.validate_context(month="Smarch")

    with pytest.raises(ValueError, match="Unknown weather condition"):
        service.validate_context(weather_conditions="Tornado")

    with pytest.raises(ValueError, match="Unknown route"):
        service.validate_context(route_id="Mars-Route")

    with pytest.raises(ValueError, match="Unknown fuel type"):
        service.validate_context(fuel_type="Unobtanium")


def test_engine_efficiency_bounds_enforcement():
    service = FleetOptimizationService(DEFAULT_DATASET)
    options = service.get_available_options()
    min_eff, max_eff = options["engine_efficiency_bounds"]

    with pytest.raises(ValueError, match="outside observed bounds"):
        service.validate_context(engine_efficiency=min_eff - 10.0)

    with pytest.raises(ValueError, match="outside observed bounds"):
        service.validate_context(engine_efficiency=max_eff + 10.0)


def test_run_optimization_schema_context_and_predictions():
    service = FleetOptimizationService(DEFAULT_DATASET)
    options = service.get_available_options()
    
    ship_type = options["ship_types"][0]
    month = options["months"][0]
    weather = options["weather_conditions"][0]
    eff = (options["engine_efficiency_bounds"][0] + options["engine_efficiency_bounds"][1]) / 2.0

    result = service.run_optimization(
        ship_type=ship_type,
        month=month,
        weather_conditions=weather,
        engine_efficiency=eff,
        population_size=6,
        iterations=2,
        seed=123,
    )

    assert "problem_metadata" in result
    assert "fixed_context" in result
    assert "results" in result
    assert "differential_evolution" in result["results"]
    assert "qpso" in result["results"]

    ctx = result["fixed_context"]
    assert ctx["ship_type"] == ship_type
    assert ctx["month"] == month
    assert ctx["weather_conditions"] == weather
    assert ctx["engine_efficiency"] == eff

    route_distances = options["route_distances"]

    for opt_name in ("differential_evolution", "qpso"):
        opt_res = result["results"][opt_name]
        assert opt_res["fuel_consumption"] >= 0.0
        assert opt_res["co2_emissions"] >= 0.0
        assert opt_res["best_objective"] >= 0.0
        assert opt_res["selected_route_id"] in options["routes"]
        assert opt_res["selected_fuel_type"] in options["fuel_types"]
        assert opt_res["derived_distance"] == route_distances[opt_res["selected_route_id"]]
        assert len(opt_res["convergence_history"]) == 2


def test_custom_dataset_file_not_found():
    with pytest.raises(FileNotFoundError):
        FleetOptimizationService(Path("non_existent_dataset.csv"))
