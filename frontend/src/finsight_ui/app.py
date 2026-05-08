import streamlit as st

st.set_page_config(
    page_title="FinSight",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("FinSight 💸")
st.subheader("AI-powered personal finance for LATAM")

st.markdown(
    """
    Welcome to **FinSight**. Use the sidebar to navigate:

    - **Login** — register or sign in
    - **Dashboard** — month at a glance
    - **Expenses** — record and review
    - **Budgets** — set monthly caps and alerts
    - **Insights** — AI-generated weekly observations
    """
)
