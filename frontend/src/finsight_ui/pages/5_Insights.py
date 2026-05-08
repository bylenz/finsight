"""Insights placeholder + CSV export (FR-IO-01)."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from finsight_ui.api_client import ApiError
from finsight_ui.state import get_client, require_login

st.set_page_config(page_title="FinSight · Insights", page_icon="💡", layout="wide")
st.title("Insights 💡")

require_login()
client = get_client()

st.info(
    "Los insights semanales generados por IA llegan en v1.0 (semana 16). "
    "Mientras tanto, revisa el desglose por categoría y por semana en el Dashboard."
)

data = st.session_state.get("latest_dashboard")
if data is None:
    try:
        data = client.get_dashboard()
        st.session_state["latest_dashboard"] = data
    except ApiError as err:
        st.warning(f"No se pudo cargar el dashboard: {err.detail}")
        data = {}

by_week = (data or {}).get("by_week") or []
if by_week:
    st.subheader("Vista previa semanal")
    df = pd.DataFrame([{"Semana": w["week_start"], "Monto": float(w["amount"])} for w in by_week])
    fig = px.bar(df, x="Semana", y="Monto")
    fig.update_layout(margin={"t": 10, "b": 10, "l": 10, "r": 10})
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("Exportar a CSV")
st.caption("Descarga todos tus gastos como un archivo CSV (FR-IO-01).")

c1, c2 = st.columns(2)
with c1:
    from_date = st.date_input("Desde", value=None, key="csv_from")
with c2:
    to_date = st.date_input("Hasta", value=None, key="csv_to")

today = datetime.now(tz=UTC).date().isoformat()
if st.button("Generar CSV", use_container_width=True):
    try:
        blob = client.get_csv_bytes(
            from_date=from_date or None,
            to_date=to_date or None,
        )
    except ApiError as err:
        st.error(f"No se pudo exportar: {err.detail}")
    else:
        st.session_state["csv_blob"] = blob
        st.session_state["csv_filename"] = f"finsight-expenses-{today}.csv"

if "csv_blob" in st.session_state:
    st.download_button(
        "Descargar CSV",
        data=st.session_state["csv_blob"],
        file_name=st.session_state.get("csv_filename", f"finsight-expenses-{today}.csv"),
        mime="text/csv",
        use_container_width=True,
    )
