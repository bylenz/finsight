"""Monthly dashboard — totals, breakdowns, budgets, alerts."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import plotly.express as px
import streamlit as st
from finsight_ui.api_client import ApiError
from finsight_ui.state import get_client, require_login

st.set_page_config(page_title="FinSight · Dashboard", page_icon="📊", layout="wide")
st.title("Dashboard 📊")

require_login()
client = get_client()

# Cache the latest dashboard payload so other pages can build category pickers.
today = datetime.now(tz=UTC).date()


def _month_options(n: int = 12) -> list[str]:
    options: list[str] = []
    year, month = today.year, today.month
    for _ in range(n):
        options.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return options


months = _month_options()
selected_month = st.selectbox("Mes", months, index=0)

try:
    data = client.get_dashboard(month=selected_month)
except ApiError as err:
    st.error(f"No se pudo cargar el dashboard: {err.detail}")
    st.stop()

# Save into session_state so Expenses/Budgets pages can reuse the categories.
st.session_state["latest_dashboard"] = data

currency = data.get("currency", "PEN")
total_spent = float(data.get("total_spent") or 0)
expense_count = int(data.get("expense_count") or 0)

k1, k2, k3 = st.columns(3)
k1.metric("Total gastado", f"{total_spent:,.2f} {currency}")
k2.metric("Gastos registrados", expense_count)
k3.metric("Moneda", currency)

st.divider()

col_pie, col_bar = st.columns(2)

by_category = data.get("by_category") or []
with col_pie:
    st.subheader("Por categoría")
    if by_category:
        df = pd.DataFrame(
            [
                {
                    "Categoría": c["category_name"],
                    "Monto": float(c["amount"]),
                }
                for c in by_category
            ]
        )
        fig = px.pie(df, names="Categoría", values="Monto", hole=0.35)
        fig.update_layout(margin={"t": 10, "b": 10, "l": 10, "r": 10})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos para este mes.")

by_week = data.get("by_week") or []
with col_bar:
    st.subheader("Por semana")
    if by_week:
        df = pd.DataFrame(
            [{"Semana": w["week_start"], "Monto": float(w["amount"])} for w in by_week]
        )
        fig = px.bar(df, x="Semana", y="Monto")
        fig.update_layout(margin={"t": 10, "b": 10, "l": 10, "r": 10})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sin datos para este mes.")

st.divider()
st.subheader("Presupuestos")

budgets = data.get("budgets") or []
if not budgets:
    st.caption("Aún no tienes presupuestos. Crea uno desde la página de Budgets.")
else:
    for b in budgets:
        limit_v = float(b.get("limit") or 0)
        spent_v = float(b.get("spent") or 0)
        pct = float(b.get("percentage") or 0)
        name = b.get("category_name") or "Total"
        bar_value = min(max(pct, 0.0), 1.0)
        if pct >= 1.0:
            st.markdown(
                f":red[**{name}** — {spent_v:,.2f} / {limit_v:,.2f} {currency} "
                f"({pct * 100:.1f}%)]"
            )
        else:
            st.markdown(
                f"**{name}** — {spent_v:,.2f} / {limit_v:,.2f} {currency} ({pct * 100:.1f}%)"
            )
        st.progress(bar_value)

st.divider()
st.subheader("Alertas recientes")

try:
    alerts = client.list_alerts()
except ApiError as err:
    st.warning(f"No se pudieron cargar alertas: {err.detail}")
    alerts = []

if not alerts:
    st.caption("Sin alertas por ahora.")
else:
    rows = []
    for a in alerts[-5:][::-1]:
        rows.append(
            {
                "Tipo": f"{a.get('type', '')}%",
                "Presupuesto": a.get("budget_id"),
                "Disparada": a.get("triggered_at"),
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
