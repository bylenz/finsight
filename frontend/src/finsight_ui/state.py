import streamlit as st


def get_token() -> str | None:
    return st.session_state.get("auth_token")


def set_token(token: str) -> None:
    st.session_state["auth_token"] = token


def clear_token() -> None:
    st.session_state.pop("auth_token", None)


def is_logged_in() -> bool:
    return get_token() is not None
