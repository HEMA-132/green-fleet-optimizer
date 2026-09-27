"""Streamlit application UI for Green Fleet Optimizer."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.application.service import FleetOptimizationService


def main() -> None:
    st.set_page_config(
        page_title="Green Fleet Optimizer",
        page_icon="🚢",
        layout="wide",
    )

    st.title("🚢 Quantum-Inspired Green Fleet Optimizer")
    st.markdown(
        """
    Compare classical **Differential Evolution** and **Quantum-Inspired Particle Swarm Optimization (QPSO)** 
    surrogate fuel and CO₂ emissions optimization for maritime operations.
    """
    )

    @st.cache_resource
    def get_service() -> FleetOptimizationService:
        return FleetOptimizationService()

    try:
        service = get_service()
        options = service.get_available_options()
    except Exception as err:
        st.error(f"Failed to load optimization service: {err}")
        return

    st.sidebar.header("⚙️ Fixed Context Settings")
    st.sidebar.caption("These operating conditions remain fixed and cannot be changed by the optimizer.")

    ship_type = st.sidebar.selectbox("Ship Type", options["ship_types"], index=0)
    month = st.sidebar.selectbox("Month", options["months"], index=0)
    weather_conditions = st.sidebar.selectbox("Weather Condition", options["weather_conditions"], index=0)

    min_eff, max_eff = options["engine_efficiency_bounds"]
    engine_efficiency = st.sidebar.slider(
        "Engine Efficiency",
        min_value=float(min_eff),
        max_value=float(max_eff),
        value=float((min_eff + max_eff) / 2.0),
        step=0.5,
    )

    st.sidebar.header("🎛️ Optimization Parameters")
    fuel_weight = st.sidebar.slider("Fuel Weight", 0.0, 1.0, 0.7, step=0.05)
    co2_weight = round(1.0 - fuel_weight, 2)
    st.sidebar.text(f"CO₂ Weight: {co2_weight}")

    population_size = st.sidebar.number_input("Population Size", min_value=4, max_value=100, value=24, step=2)
    iterations = st.sidebar.number_input("Iterations", min_value=1, max_value=200, value=40, step=5)
    seed = st.sidebar.number_input("Random Seed", min_value=0, max_value=999999, value=42, step=1)

    st.info(
        "**Optimization Formulation:** Decision Variables = `route_id`, `fuel_type` | "
        "Fixed Context = `ship_type`, `month`, `weather_conditions`, `engine_efficiency` | "
        "Distance = *derived from route data median*."
    )

    if st.button("🚀 Run Fleet Optimization", type="primary"):
        with st.spinner("Executing Classical DE and Quantum-Inspired QPSO optimizers..."):
            try:
                results = service.run_optimization(
                    ship_type=ship_type,
                    month=month,
                    weather_conditions=weather_conditions,
                    engine_efficiency=engine_efficiency,
                    fuel_weight=fuel_weight,
                    co2_weight=co2_weight,
                    population_size=int(population_size),
                    iterations=int(iterations),
                    seed=int(seed),
                )
            except Exception as err:
                st.error(f"Optimization execution error: {err}")
                return

        st.subheader("📊 Optimization Results Comparison")

        de_res = results["results"]["differential_evolution"]
        qpso_res = results["results"]["qpso"]

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### 🔹 Differential Evolution (Classical)")
            st.metric("Objective Value", f"{de_res['best_objective']:.6f}")
            st.metric("Predicted Fuel (t)", f"{de_res['fuel_consumption']:.2f}")
            st.metric("Predicted CO₂ (t)", f"{de_res['co2_emissions']:.2f}")
            st.metric("Optimal Route", de_res["selected_route_id"])
            st.metric("Optimal Fuel Type", de_res["selected_fuel_type"])
            st.metric("Derived Distance (nmi)", f"{de_res['derived_distance']:.2f}")
            st.metric("Runtime (seconds)", f"{de_res['runtime_seconds']:.4f}")

        with col2:
            st.markdown("### ⚛️ QPSO (Quantum-Inspired)")
            st.metric("Objective Value", f"{qpso_res['best_objective']:.6f}")
            st.metric("Predicted Fuel (t)", f"{qpso_res['fuel_consumption']:.2f}")
            st.metric("Predicted CO₂ (t)", f"{qpso_res['co2_emissions']:.2f}")
            st.metric("Optimal Route", qpso_res["selected_route_id"])
            st.metric("Optimal Fuel Type", qpso_res["selected_fuel_type"])
            st.metric("Derived Distance (nmi)", f"{qpso_res['derived_distance']:.2f}")
            st.metric("Runtime (seconds)", f"{qpso_res['runtime_seconds']:.4f}")

        st.subheader("📉 Convergence Comparison")
        de_history = pd.DataFrame(de_res["convergence_history"]).rename(columns={"best_objective": "Differential Evolution"})
        qpso_history = pd.DataFrame(qpso_res["convergence_history"]).rename(columns={"best_objective": "QPSO"})
        
        merged_history = pd.merge(de_history, qpso_history, on="iteration")
        st.line_chart(merged_history.set_index("iteration"))

        st.warning(f"**Scientific Disclaimer:** {results['disclaimer']}")

    with st.expander("📍 Route Reference Distances"):
        st.json(options["route_distances"])


if __name__ == "__main__":
    main()
