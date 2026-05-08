"""Streamlit session-state helpers for auth and API access."""

from __future__ import annotations

import streamlit as st

from finsight_ui.api_client import ApiClient


def get_token() -> str | None:
    return st.session_state.get("auth_token")


def set_token(token: str) -> None:
    st.session_state["auth_token"] = token


def clear_token() -> None:
    st.session_state.pop("auth_token", None)
    st.session_state.pop("user_email", None)


def is_logged_in() -> bool:
    return get_token() is not None


def set_user_email(email: str) -> None:
    st.session_state["user_email"] = email


def get_user_email() -> str | None:
    return st.session_state.get("user_email")


def get_client() -> ApiClient:
    """Return an ``ApiClient`` bound to the current session token."""
    return ApiClient(token=get_token())


def require_login() -> str:
    """Block the page if the user is not logged in.

    Returns the bearer token when logged in. When not, renders a warning,
    a link back to the login page, and stops the script.
    """
    token = get_token()
    if token is None:
        st.warning("Por favor inicia sesión para continuar.")
        st.page_link("pages/1_Login.py", label="Ir a iniciar sesión", icon="🔐")
        st.stop()
    return token  # type: ignore[return-value]
