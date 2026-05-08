"""Login / sign-up page."""

from __future__ import annotations

import streamlit as st
from finsight_ui.api_client import ApiClient, ApiError
from finsight_ui.state import (
    clear_token,
    get_user_email,
    is_logged_in,
    set_token,
    set_user_email,
)

st.set_page_config(page_title="FinSight · Login", page_icon="🔐", layout="centered")
st.title("Acceso")


def _friendly_error(err: ApiError) -> str:
    if err.status_code == 401:
        return "Credenciales inválidas."
    if err.status_code == 409:
        return "Este correo ya está registrado."
    if err.status_code == 422:
        return f"Datos inválidos: {err.detail}"
    return f"Error ({err.status_code}): {err.detail}"


if is_logged_in():
    email = get_user_email() or "—"
    st.success(f"Sesión activa como **{email}**.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Ir al dashboard", use_container_width=True):
            st.switch_page("pages/2_Dashboard.py")
    with col2:
        if st.button("Cerrar sesión", use_container_width=True):
            clear_token()
            st.rerun()
    st.stop()


tab_login, tab_signup = st.tabs(["Iniciar sesión", "Registrarse"])

with tab_login:
    with st.form("login_form"):
        email = st.text_input("Correo", key="login_email", autocomplete="email")
        password = st.text_input(
            "Contraseña", type="password", key="login_password", autocomplete="current-password"
        )
        submitted = st.form_submit_button("Entrar", use_container_width=True)
    if submitted:
        if not email or not password:
            st.error("Ingresa correo y contraseña.")
        else:
            client = ApiClient()
            try:
                data = client.login(email, password)
            except ApiError as err:
                st.error(_friendly_error(err))
            else:
                set_token(data["access_token"])
                set_user_email(email)
                st.success("¡Bienvenido!")
                st.switch_page("pages/2_Dashboard.py")

with tab_signup:
    st.caption("La contraseña debe tener al menos 8 caracteres.")
    with st.form("signup_form"):
        new_email = st.text_input("Correo", key="signup_email", autocomplete="email")
        new_password = st.text_input(
            "Contraseña",
            type="password",
            key="signup_password",
            autocomplete="new-password",
            help="Mínimo 8 caracteres.",
        )
        submitted = st.form_submit_button("Crear cuenta", use_container_width=True)
    if submitted:
        if not new_email or not new_password:
            st.error("Ingresa correo y contraseña.")
        elif len(new_password) < 8:
            st.error("La contraseña debe tener al menos 8 caracteres.")
        else:
            client = ApiClient()
            try:
                client.register(new_email, new_password)
                data = client.login(new_email, new_password)
            except ApiError as err:
                st.error(_friendly_error(err))
            else:
                set_token(data["access_token"])
                set_user_email(new_email)
                st.success("Cuenta creada. ¡Bienvenido!")
                st.switch_page("pages/2_Dashboard.py")
