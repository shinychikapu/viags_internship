"""
VIAGS Scheduling Statistics — app entry point.

Responsibilities kept here: page config, session state, the auth gate, and the
router. The plot definitions live in plots.py; the UI building blocks in ui.py.

Run with:  streamlit run app.py
"""
import streamlit as st

from ui import _footer, _navbar, go, home_screen, plot_view

# Wide layout for a spacious dashboard. Must run before other st output.
st.set_page_config(page_title="VIAGS Scheduling Stats", page_icon="✈️", layout="wide")

# ----------------------------------------------------------------------------
# Fake user store + session defaults
# (placeholder auth — replace with streamlit-authenticator for the real app)
# ----------------------------------------------------------------------------
if "users" not in st.session_state:
    st.session_state.users = {"admin": "admin"}  # username: password

st.session_state.setdefault("logged_in", False)
st.session_state.setdefault("username", "")
st.session_state.setdefault("page", "home")
st.session_state.setdefault("choice", None)
st.session_state.setdefault("params", {})


# ----------------------------------------------------------------------------
# Auth gate
# ----------------------------------------------------------------------------
def auth_screen() -> None:
    st.title("✈️ VIAGS Scheduling Statistics")
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


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------
# Standalone plot view: this is what a NEW TAB opened from the menu renders.
# It's driven entirely by the URL (?view=plot&choice=...&unit=...), so it works
# in its own browser session without the app shell or login.
if st.query_params.get("view") == "plot":
    plot_view()
    _footer()
    st.stop()

# Normal app flow
if not st.session_state.logged_in:
    auth_screen()
else:
    _navbar()
    home_screen()

# Footer renders on every screen (login included)
_footer()
