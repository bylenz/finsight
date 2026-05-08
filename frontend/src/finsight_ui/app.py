"""FinSight Streamlit landing page."""

from __future__ import annotations

import streamlit as st

from finsight_ui.state import clear_token, get_user_email, is_logged_in

st.set_page_config(
    page_title="FinSight",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    st.markdown("### FinSight 💸")
    if is_logged_in():
        email = get_user_email() or "—"
        st.caption(f"Conectado como **{email}**")
        if st.button("Cerrar sesión", use_container_width=True):
            clear_token()
            st.rerun()
    else:
        st.caption("No has iniciado sesión.")
        st.page_link("pages/1_Login.py", label="Iniciar sesión", icon="🔐")

st.title("FinSight 💸")
st.subheader("Finanzas personales con IA para LATAM")

st.markdown("""
    Bienvenido a **FinSight**. Usa la barra lateral para navegar:

    - **Login** — registrarse o iniciar sesión
    - **Dashboard** — el mes de un vistazo
    - **Expenses** — registrar y revisar gastos
    - **Budgets** — fijar topes mensuales y alertas
    - **Insights** — observaciones semanales generadas por IA
    """)
