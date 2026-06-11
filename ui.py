"""
UI building blocks: navigation bar, footer, styling, the settings pop-up,
and the two screens (home menu + standalone plot view).

The plot view is driven entirely by the URL query params, which is what makes
the "open in a new tab" comparison flow work.
"""
import os
import time
from urllib.parse import urlencode

import streamlit as st

from plots import PLOT_TYPES, SITES, _index_of


def go(page: str) -> None:
    """Switch screen and redraw."""
    st.session_state.page = page
    st.rerun()


# ----------------------------------------------------------------------------
# Top navigation bar
# ----------------------------------------------------------------------------
def _navbar() -> None:
    """Global navigation bar spanning across the top of the application."""
    nav_links = [
        {"label": "🏠 Home", "page": "home", "choice_trigger": None, "key": "nav_home"},
    ]

    # Column widths: logo | nav links | spacer | profile | logout
    col_weights = [1.8] + [1.2] * len(nav_links) + [1.5] + [2.5, 1.2]
    cols = st.columns(col_weights, vertical_alignment="center")

    with cols[0]:
        logo_path = "viags_logo.png"
        if os.path.exists(logo_path):
            brand_cols = st.columns([1, 2.2], vertical_alignment="center")
            with brand_cols[0]:
                st.image(logo_path, width=45)
            with brand_cols[1]:
                st.markdown(
                    "<h4 style='margin:0; padding:0; line-height:1.2;'>VIAGS Stats</h4>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown("### ✈️ VIAGS Stats")

    # Render dynamic links
    for i, link in enumerate(nav_links):
        with cols[i + 1]:
            if link["choice_trigger"] is None:
                is_active = st.session_state.page == link["page"]
            else:
                is_active = (st.session_state.choice == link["choice_trigger"]
                             and st.session_state.page != "home")
            button_type = "primary" if is_active else "secondary"
            if st.button(link["label"], key=link["key"], use_container_width=True, type=button_type):
                if link["choice_trigger"] is not None:
                    st.session_state.choice = link["choice_trigger"]
                go(link["page"])

    spacer_idx = len(nav_links) + 1
    profile_idx = spacer_idx + 1
    logout_idx = profile_idx + 1

    with cols[profile_idx]:
        st.markdown(
            f"<div style='text-align: right;'><span class='user-profile'>"
            f"👤 <b>{st.session_state.username}</b></span></div>",
            unsafe_allow_html=True,
        )

    with cols[logout_idx]:
        if st.button("Log out", key="nav_logout", use_container_width=True, type="secondary"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.page = "home"
            st.session_state.choice = None
            st.rerun()

    st.markdown("---")


# ----------------------------------------------------------------------------
# Footer
# ----------------------------------------------------------------------------
def _footer() -> None:
    """Fixed footer pinned to the bottom-right corner, shown on every screen."""
    st.markdown(
        """
        <style>
        .app-footer {
            position: fixed;
            right: 16px;
            bottom: 8px;
            z-index: 1000;
            font-size: 0.8rem;
            color: rgba(150, 150, 150, 0.9);
        }
        /* keep page content from hiding behind the footer */
        .block-container { padding-bottom: 3rem; }
        </style>
        <div class="app-footer">Made by <b>Le Gia Thy</b></div>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------------
# Styling for the big home buttons + the "open in new tab" link
# ----------------------------------------------------------------------------
def _inject_button_css() -> None:
    st.markdown(
        """
        <style>
        /* Big icon-above-text buttons (scoped to the home grid container) */
        .st-key-home_grid div[data-testid="stButton"] > button {
            height: 150px;
            white-space: pre-line;        /* honor the newline between icon and label */
            font-size: 1.05rem;
            font-weight: 600;
            line-height: 1.6;
            border-radius: 14px;
        }
        .st-key-home_grid div[data-testid="stButton"] > button p::first-line {
            font-size: 2.2rem;            /* enlarge the icon (first line) */
        }
        /* A link styled as a button, used to open the plot in a new tab */
        a.open-plot-btn {
            display: inline-block; width: 100%; text-align: center;
            padding: 0.55rem 1rem; margin-top: 0.4rem;
            background: #ff4b4b; color: #fff !important;
            border-radius: 8px; text-decoration: none; font-weight: 600;
        }
        a.open-plot-btn:hover { background: #e63b3b; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------------
# Query-param helpers — the plot tab is driven entirely by the URL
# ----------------------------------------------------------------------------
def _flatten_params(choice: str, params: dict) -> dict:
    """Turn a params dict into flat string values suitable for a URL query string."""
    flat = {"view": "plot", "choice": choice}
    for k, v in params.items():
        flat[k] = ",".join(str(x) for x in v) if isinstance(v, (list, tuple)) else str(v)
    return flat


def _plot_url(choice: str, params: dict) -> str:
    """Relative URL that opens the standalone plot view for these params."""
    return "?" + urlencode(_flatten_params(choice, params))


def _new_tab_link(url: str, label: str) -> str:
    """
    A link that opens `url` in a new tab AND closes the Streamlit dialog in the
    current tab. The onclick clicks the dialog's close button (falling back to
    an Escape keypress), since opening a plain link doesn't trigger a rerun.
    """
    close_js = (
        "var d=document;"
        "var b=d.querySelector('[data-testid=stDialog] button[aria-label=Close]')"
        "||d.querySelector('[role=dialog] button[aria-label=Close]');"
        "if(b){b.click();}"
        "else{d.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true}));}"
    )
    return (
        '<a href="' + url + '" target="_blank" class="open-plot-btn" '
        'onclick="' + close_js + '">' + label + "</a>"
    )


# ----------------------------------------------------------------------------
# Settings pop-up (used both from the home menu and from a plot tab)
# ----------------------------------------------------------------------------
@st.dialog("Plot settings")
def _settings_dialog(choice: str, in_plot_tab: bool = False, current: dict = None) -> None:
    """
    Universal filters live here, on top of every per-plot input form.
    Whatever this dialog stuffs into `params` is flattened into the URL
    by `_plot_url`, then unpacked back into `p` by `plot_view` and threaded
    through `data.filter_df(df, p)` by every chart in plots.py.

    TODO (settings_filters in the plan):
      - Active-only toggle, default True
            active_only = st.toggle("Active only", value=cur.get("active_only", "True") != "False")
            params["active_only"] = active_only
      - Labor-group multiselect over ['FULLTIME', 'OUTSOURCE', 'SUPPORT'],
        empty = no filter
            preset = (cur.get("labor_groups") or "").split(",") if cur.get("labor_groups") else []
            labor_groups = st.multiselect("Labor group",
                                          ["FULLTIME", "OUTSOURCE", "SUPPORT"],
                                          default=[g for g in preset if g])
            if labor_groups:
                params["labor_groups"] = labor_groups
        Note: lists are joined with "," by `_flatten_params`, so the receiving
        side (data.filter_df) needs to split them back — keep that in mind
        when the chart functions read `p["labor_groups"]`.
    """
    cfg = PLOT_TYPES[choice]
    cur = current or {}
    st.caption(cfg["title"])

    site = st.selectbox("Site", SITES, index=_index_of(SITES, cur.get("site")))
    params = {"site": site, **cfg["inputs"](cur)}
    url = _plot_url(choice, params)

    if in_plot_tab:
        # On a plot tab: "Apply" updates the URL and re-renders the chart in place.
        if st.button("Apply", type="primary", use_container_width=True):
            st.query_params.clear()
            for k, v in _flatten_params(choice, params).items():
                st.query_params[k] = v
            st.rerun()
        st.markdown(_new_tab_link(url, "↗ Open as a new tab instead"), unsafe_allow_html=True)
    else:
        # From the home menu: open the plot in a NEW browser tab, then close this pop-up.
        st.markdown(_new_tab_link(url, "📈 Open plot in new tab"), unsafe_allow_html=True)
        st.caption("Open several to compare them side by side.")


# ----------------------------------------------------------------------------
# Home menu — big buttons that open the settings pop-up
# ----------------------------------------------------------------------------
def home_screen() -> None:
    _inject_button_css()
    st.title("Home")

    # ------------------------------------------------------------------
    # TODO (overview_home in the plan): render the at-a-glance overview
    # ABOVE the deep-dive button grid, all built from data.load_employees().
    #
    #   df = filter_df(load_employees(), {})  # no global filters here
    #
    # 1) 6 KPI cards in one row of st.metric():
    #       Total headcount        len(df)
    #       % Female               (df.sex == "Nữ").mean()
    #       % TT (direct)          (df.work_type == "TT").mean()
    #       Avg age                df.age.mean()
    #       % English-certified    df.english_band.notna().mean()
    #       % Permanent contract   (df.contract_type == "HĐLĐ không xác định...").mean()
    #
    # 2) 4 mini donuts in one row, via plots._donut(df, by, ...):
    #       Sex            by="sex"
    #       Work type      by="work_type"
    #       Contract type  by="contract_type"
    #       Labor group    by="labor_group"
    #
    # 3) Age pyramid       plots._age_pyramid(df)
    # 4) Top-10 job titles plots._top_n_bar(df, "job_title", n=10, title=...)
    #
    # The deep-dive button grid below stays as the entry point for the
    # per-topic charts.
    # ------------------------------------------------------------------

    st.write("Choose what you want to plot:")
    with st.container(key="home_grid"):
        n_cols = 3
        cols = st.columns(n_cols)
        for i, (choice, cfg) in enumerate(PLOT_TYPES.items()):
            col = cols[i % n_cols]  # wrap onto a new row every n_cols buttons
            label = f"{cfg['icon']}\n{cfg['title']}"
            if col.button(label, key=f"btn_{choice}", use_container_width=True):
                _settings_dialog(choice)


# ----------------------------------------------------------------------------
# Standalone plot view — what a new tab (?view=plot&...) renders
# ----------------------------------------------------------------------------
def plot_view() -> None:
    _inject_button_css()
    qp = st.query_params
    choice = qp.get("choice")
    if choice not in PLOT_TYPES:
        st.error("Unknown or missing plot type in the URL.")
        return

    cfg = PLOT_TYPES[choice]
    # Everything except routing keys becomes the chart params.
    p = {k: qp.get(k) for k in qp.keys() if k not in ("view", "choice")}

    head = st.columns([4, 1.3], vertical_alignment="center")
    with head[0]:
        st.title(f"{cfg['icon']} {cfg['title']} · {p.get('site', '')}")
    with head[1]:
        if st.button("⚙️ Change parameters", use_container_width=True):
            _settings_dialog(choice, in_plot_tab=True, current=p)

    with st.spinner("Loading data and building plot..."):
        time.sleep(1.0)  # simulate loading data
        fig = cfg["chart"](p)
    st.plotly_chart(fig, use_container_width=True)
