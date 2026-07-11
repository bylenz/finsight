"""Budgets management page."""

from __future__ import annotations

import streamlit as st
from finsight_ui.api_client import ApiError
from finsight_ui.state import get_client, require_login

st.set_page_config(page_title="FinSight · Budgets", page_icon="🎯", layout="wide")
st.title("Presupuestos 🎯")

require_login()
client = get_client()


def _all_categories() -> list[tuple[str, int | None]]:
    """Return [(label, category_id)] — "General" plus every available category."""
    options: list[tuple[str, int | None]] = [("General (sin categoría)", None)]
    try:
        categories = client.get_categories()
    except ApiError:
        return options
    for c in categories:
        cid = c.get("id")
        name = c.get("name")
        if cid is None or not name:
            continue
        options.append((name, cid))
    return options


cat_options = _all_categories()
cat_labels = [label for label, _ in cat_options]
cat_id_by_label = dict(cat_options)
cat_label_by_id: dict[int, str] = {cid: label for label, cid in cat_options if cid is not None}

st.subheader("Nuevo presupuesto")
with st.form("create_budget", clear_on_submit=True):
    c1, c2, c3, c4 = st.columns([1, 1, 2, 1])
    with c1:
        amount = st.number_input("Monto", min_value=0.01, step=10.0, format="%.2f")
    with c2:
        currency = st.selectbox("Moneda", ["PEN", "USD"], index=0)
    with c3:
        category_label = st.selectbox("Categoría", cat_labels)
    with c4:
        period = st.selectbox("Periodo", ["monthly"], index=0)
    submitted = st.form_submit_button("Crear presupuesto", use_container_width=True)

if submitted:
    try:
        client.create_budget(
            amount=float(amount),
            currency=currency,
            category_id=cat_id_by_label.get(category_label),
            period=period,
        )
    except ApiError as err:
        st.error(f"No se pudo crear el presupuesto: {err.detail}")
    else:
        st.toast("Presupuesto creado.", icon="✅")
        st.rerun()

st.divider()
st.subheader("Tus presupuestos")

try:
    budgets = client.list_budgets()
except ApiError as err:
    st.error(f"No se pudieron cargar los presupuestos: {err.detail}")
    budgets = []

if not budgets:
    st.caption("Aún no tienes presupuestos.")
else:
    for b in budgets:
        bid = int(b["id"])
        cid = b.get("category_id")
        name = cat_label_by_id.get(cid, "General") if cid else "General"
        currency = b.get("currency", "PEN")
        try:
            status = client.budget_status(bid)
        except ApiError as err:
            st.warning(f"No se pudo cargar estado de #{bid}: {err.detail}")
            continue

        spent = float(status.get("spent") or 0)
        limit_v = float(status.get("limit") or 0)
        pct = float(status.get("percentage") or 0)
        bar_value = min(max(pct, 0.0), 1.0)

        col_info, col_btn = st.columns([6, 1])
        with col_info:
            if pct >= 1.0:
                st.markdown(
                    f":red[**{name}** — {spent:,.2f} / {limit_v:,.2f} {currency} "
                    f"({pct * 100:.1f}%)]"
                )
            else:
                st.markdown(
                    f"**{name}** — {spent:,.2f} / {limit_v:,.2f} {currency} " f"({pct * 100:.1f}%)"
                )
            st.progress(bar_value)
        with col_btn:
            if st.button("Borrar", key=f"del_budget_{bid}"):
                try:
                    client.delete_budget(bid)
                except ApiError as err:
                    st.error(f"No se pudo borrar: {err.detail}")
                else:
                    st.toast("Presupuesto eliminado.", icon="🗑️")
                    st.rerun()
