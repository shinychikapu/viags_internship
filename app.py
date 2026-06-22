"""
VIAGS HR Dashboard — app entry point.

Responsibilities kept here: page config, session state, the auth gate, and the
router. The plot definitions live in plots.py; the UI building blocks in ui.py.

Run with:  streamlit run app.py
"""
import streamlit as st

from ui import _footer, _navbar, go, home_screen, plot_view

st.set_page_config(page_title="VIAGS HR Dashboard", page_icon="✈️", layout="wide")

if "users" not in st.session_state:
    st.session_state.users = {"admin": "admin"}

st.session_state.setdefault("logged_in", False)
st.session_state.setdefault("username", "")
st.session_state.setdefault("page", "home")
st.session_state.setdefault("choice", None)
st.session_state.setdefault("params", {})


def auth_screen() -> None:
    st.title("✈️ VIAGS HR Dashboard")
    st.caption("Sign in to view workforce statistics for TSN and KCQ.")
    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        u = st.text_input("Username", key="li_u")
        p = st.text_input("Password", type="password", key="li_p")
        if st.button("Log in", type="primary"):
            if st.session_state.users.get(u) == p:
                st.session_state.logged_in = True
                st.session_state.username = u
                go("home")
            else:
                st.error("Wrong username or password.")

    with tab_signup:
        new_u = st.text_input("Choose a username", key="su_u")
        new_p = st.text_input("Choose a password", type="password", key="su_p")
        if st.button("Create account"):
            if not new_u or not new_p:
                st.warning("Fill in both fields.")
            elif new_u in st.session_state.users:
                st.error("Username already taken.")
            else:
                st.session_state.users[new_u] = new_p
                st.success("Account created — switch to the Log in tab.")


if st.query_params.get("view") == "plot":
    plot_view()
    _footer()
    st.stop()

if not st.session_state.logged_in:
    auth_screen()
else:
    _navbar()
    home_screen()

_footer()
