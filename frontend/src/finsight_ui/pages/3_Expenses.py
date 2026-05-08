"""Expenses CRUD page."""

from __future__ import annotations

from datetime import UTC, datetime, time

import pandas as pd
import streamlit as st
from finsight_ui.api_client import ApiError
from finsight_ui.state import get_client, require_login

st.set_page_config(page_title="FinSight · Expenses", page_icon="🧾", layout="wide")
st.title("Gastos 🧾")

require_login()
client = get_client()


def _categories_from_dashboard() -> list[tuple[str, int | None]]:
    """Return [(label, category_id)] derived from the cached dashboard payload."""
    options: list[tuple[str, int | None]] = [("Auto (LLM)", None)]
    data = st.session_state.get("latest_dashboard")
    if data is None:
        try:
            data = client.get_dashboard()
            st.session_state["latest_dashboard"] = data
        except ApiError:
            return options
    seen: set[int] = set()
    for c in data.get("by_category") or []:
        cid = c.get("category_id")
        name = c.get("category_name")
        if cid is None or cid in seen or not name:
            continue
        seen.add(cid)
        options.append((name, cid))
    return options


cat_options = _categories_from_dashboard()
cat_labels = [label for label, _ in cat_options]

st.subheader("Nuevo gasto")
with st.form("create_expense", clear_on_submit=True):
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        amount = st.number_input("Monto", min_value=0.01, step=1.0, format="%.2f")
    with c2:
        currency = st.selectbox("Moneda", ["PEN", "USD"], index=0)
    with c3:
        description = st.text_input("Descripción", max_chars=255)

    c4, c5, c6 = st.columns([1, 1, 1])
    with c4:
        occurred_date = st.date_input("Fecha", value=datetime.now(tz=UTC).date())
    with c5:
        category_label = st.selectbox("Categoría", cat_labels)
    with c6:
        is_business = st.checkbox("Gasto de negocio", value=False)

    submitted = st.form_submit_button("Guardar gasto", use_container_width=True)

if submitted:
    cat_id = dict(cat_options).get(category_label)
    occurred_at = datetime.combine(occurred_date, time(12, 0, tzinfo=UTC))
    try:
        client.create_expense(
            amount=float(amount),
            currency=currency,
            description=description or None,
            occurred_at=occurred_at,
            category_id=cat_id,
            is_business=is_business,
        )
    except ApiError as err:
        st.error(f"No se pudo crear el gasto: {err.detail}")
    else:
        st.toast("Gasto registrado.", icon="✅")
        st.rerun()

st.divider()
st.subheader("Filtros")

f1, f2, f3 = st.columns([1, 1, 1])
with f1:
    from_date = st.date_input("Desde", value=None, key="exp_from")
with f2:
    to_date = st.date_input("Hasta", value=None, key="exp_to")
with f3:
    filter_label = st.selectbox("Categoría", ["Todas", *cat_labels[1:]], key="exp_cat")

filter_cat_id = None
if filter_label != "Todas":
    filter_cat_id = dict(cat_options).get(filter_label)

try:
    items = client.list_expenses(
        limit=50,
        from_date=from_date or None,
        to_date=to_date or None,
        category_id=filter_cat_id,
    )
except ApiError as err:
    st.error(f"No se pudieron cargar los gastos: {err.detail}")
    items = []

st.subheader("Últimos 50 gastos")

if not items:
    st.caption("Aún no hay gastos para mostrar.")
else:
    cat_name_by_id: dict[int, str] = {cid: label for label, cid in cat_options if cid is not None}

    rows = []
    for it in items:
        cid = it.get("category_id")
        rows.append(
            {
                "Fecha": (it.get("occurred_at") or "")[:10],
                "Descripción": it.get("description") or "",
                "Categoría": cat_name_by_id.get(cid, "—") if cid else "—",
                "Monto": f"{float(it.get('amount') or 0):,.2f} {it.get('currency', '')}",
                "Negocio": "Sí" if it.get("is_business") else "No",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.caption("Eliminar un gasto:")
    for it in items[:20]:
        col_label, col_button = st.columns([5, 1])
        col_label.markdown(
            f"**{(it.get('occurred_at') or '')[:10]}** — "
            f"{it.get('description') or '(sin descripción)'} — "
            f"{float(it.get('amount') or 0):,.2f} {it.get('currency', '')}"
        )
        if col_button.button("Borrar", key=f"del_exp_{it['id']}"):
            try:
                client.delete_expense(int(it["id"]))
            except ApiError as err:
                st.error(f"No se pudo borrar: {err.detail}")
            else:
                st.toast("Gasto eliminado.", icon="🗑️")
                st.rerun()
