"""
UI building blocks: navigation bar, footer, styling, the settings pop-up,
and the two screens (home menu + standalone plot view).

The plot view is driven entirely by the URL query params, which is what makes
the "open in a new tab" comparison flow work.
"""
import os
from urllib.parse import urlencode

import streamlit as st

from data import filter_df, load_employees, search_employees
from plots import PLOT_TYPES, SITES, _donut, _index_of, _top_n_bar


def go(page: str) -> None:
    """Switch screen and redraw."""
    st.session_state.page = page
    st.rerun()


def _parse_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("false", "0", "no")


def _parse_plot_params(p: dict) -> dict:
    """Normalize URL query params before they reach filter_df / chart functions."""
    parsed = dict(p)
    parsed["active_only"] = _parse_bool(p.get("active_only"), default=True)
    for key in ("top_n",):
        if key in parsed and parsed[key] is not None:
            try:
                parsed[key] = int(parsed[key])
            except (TypeError, ValueError):
                pass
    return parsed


def _navbar() -> None:
    """Global navigation bar spanning across the top of the application."""
    nav_links = [
        {"label": "🏠 Home", "page": "home", "choice_trigger": None, "key": "nav_home"},
    ]

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
                    "<h4 style='margin:0; padding:0; line-height:1.2;'>VIAGS HR</h4>",
                    unsafe_allow_html=True,
                )
        else:
            st.markdown("### ✈️ VIAGS HR")

    for i, link in enumerate(nav_links):
        with cols[i + 1]:
            is_active = st.session_state.page == link["page"]
            button_type = "primary" if is_active else "secondary"
            if st.button(
                link["label"],
                key=link["key"],
                use_container_width=True,
                type=button_type,
            ):
                go(link["page"])

    with cols[-2]:
        st.markdown(
            f"<div style='text-align: right;'>👤 <b>{st.session_state.username}</b></div>",
            unsafe_allow_html=True,
        )

    with cols[-1]:
        if st.button("Log out", key="nav_logout", use_container_width=True, type="secondary"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.page = "home"
            st.session_state.choice = None
            st.rerun()

    st.markdown("---")


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
        .block-container { padding-bottom: 3rem; }
        </style>
        <div class="app-footer">Made by <b>Le Gia Thy</b></div>
        """,
        unsafe_allow_html=True,
    )


def _inject_button_css() -> None:
    st.markdown(
        """
        <style>
        .st-key-home_grid div[data-testid="stButton"] > button {
            height: 150px;
            white-space: pre-line;
            font-size: 1.05rem;
            font-weight: 600;
            line-height: 1.6;
            border-radius: 14px;
        }
        .st-key-home_grid div[data-testid="stButton"] > button p::first-line {
            font-size: 2.2rem;
        }
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


def _flatten_params(choice: str, params: dict) -> dict:
    """Turn a params dict into flat string values suitable for a URL query string."""
    flat = {"view": "plot", "choice": choice}
    for k, v in params.items():
        if isinstance(v, bool):
            flat[k] = str(v)
        elif isinstance(v, (list, tuple)):
            flat[k] = ",".join(str(x) for x in v)
        else:
            flat[k] = str(v)
    return flat


def _plot_url(choice: str, params: dict) -> str:
    """Relative URL that opens the standalone plot view for these params."""
    return "?" + urlencode(_flatten_params(choice, params))


def _new_tab_link(url: str, label: str) -> str:
    close_js = (
        "var d=document;"
        "var b=d.querySelector('[data-testid=stDialog] button[aria-label=Close]')"
        "||d.querySelector('[role=dialog] button[aria-label=Close]');"
        "if(b){b.click();}"
        "else{d.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',keyCode:27,bubbles:true}));}"
    )
    return (
        f'<a href="{url}" target="_blank" class="open-plot-btn" '
        f'onclick="{close_js}">{label}</a>'
    )


@st.dialog("Plot settings")
def _settings_dialog(choice: str, in_plot_tab: bool = False, current: dict = None) -> None:
    cfg = PLOT_TYPES[choice]
    cur = current or {}
    st.caption(cfg["title"])

    site = st.selectbox("Site", SITES, index=_index_of(SITES, cur.get("site")))
    active_only = st.toggle(
        "Active only",
        value=_parse_bool(cur.get("active_only"), default=True),
    )

    params = {"site": site, "active_only": active_only, **cfg["inputs"](cur)}

    url = _plot_url(choice, params)

    if in_plot_tab:
        if st.button("Apply", type="primary", use_container_width=True):
            st.query_params.clear()
            for k, v in _flatten_params(choice, params).items():
                st.query_params[k] = v
            st.rerun()
        st.markdown(_new_tab_link(url, "↗ Open as a new tab instead"), unsafe_allow_html=True)
    else:
        st.markdown(_new_tab_link(url, "📈 Open plot in new tab"), unsafe_allow_html=True)
        st.caption("Open several to compare them side by side.")


def _render_overview() -> None:
    df = filter_df(load_employees(), {"active_only": True})
    if df.empty:
        st.warning("No employee records found. Run `python -m etl` first.")
        return

    st.subheader("Workforce overview")

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Headcount", f"{len(df):,}")
    k2.metric("% Female", f"{(df.sex == 'Nữ').mean():.0%}")
    k3.metric("% Direct (TT)", f"{(df.work_type == 'TT').mean():.0%}")
    avg_age = df.age.mean()
    k4.metric("Avg age", f"{avg_age:.1f}" if avg_age == avg_age else "—")
    k5.metric("% English certified", f"{df.english_band.notna().mean():.0%}")
    k6.metric(
        "% Permanent contract",
        f"{(df.contract_type == 'Không xác định thời hạn').mean():.0%}",
    )

    _STACKED_DONUT_H = 300
    _CONTRACT_DONUT_H = _STACKED_DONUT_H * 2

    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            _donut(df, "sex", title="Sex", height=_STACKED_DONUT_H, legend_below=True),
            use_container_width=True,
            key="ov_sex",
        )
        st.plotly_chart(
            _donut(df, "site", title="Sites", height=_STACKED_DONUT_H, legend_below=True),
            use_container_width=True,
            key="ov_site",
        )
    with right:
        st.plotly_chart(
            _donut(
                df.dropna(subset=["contract_type"]),
                "contract_type",
                title="Contract type",
                height=_CONTRACT_DONUT_H,
            ),
            use_container_width=True,
            key="ov_ct",
        )

    st.plotly_chart(
        _top_n_bar(df, "job_title", n=10, title="Top 10 job titles"),
        use_container_width=True,
        key="ov_jobs",
    )

    st.markdown("---")


def _render_employee_search() -> None:
    st.subheader("Employee search")
    name_q, hr_q, btn_col = st.columns([2, 2, 1])
    with name_q:
        name_input = st.text_input("Name", key="emp_search_name", placeholder="Full or partial name")
    with hr_q:
        hr_input = st.text_input("HR no.", key="emp_search_hr", placeholder="HR number")
    with btn_col:
        st.write("")
        search = st.button("Search", type="primary", use_container_width=True, key="emp_search_btn")

    if not search:
        return

    if not name_input.strip() and not hr_input.strip():
        st.warning("Enter a name or HR number.")
        return

    results = search_employees(
        load_employees(),
        name=name_input,
        hr_no=hr_input,
    )
    if results.empty:
        st.info("No employees found.")
        return

    st.dataframe(results, use_container_width=True, hide_index=True)
    if len(results) > 1:
        st.caption(f"{len(results)} matches — refine your search to narrow results.")


def home_screen() -> None:
    _inject_button_css()
    st.title("HR Dashboard")
    _render_overview()

    st.write("Choose a deep-dive chart:")
    with st.container(key="home_grid"):
        cols = st.columns(3)
        for i, (choice, cfg) in enumerate(PLOT_TYPES.items()):
            label = f"{cfg['icon']}\n{cfg['title']}"
            if cols[i % 3].button(label, key=f"btn_{choice}", use_container_width=True):
                _settings_dialog(choice)

    st.markdown("---")
    _render_employee_search()


def plot_view() -> None:
    _inject_button_css()
    choice = st.query_params.get("choice")
    if choice not in PLOT_TYPES:
        st.error("Unknown or missing plot type in the URL.")
        return

    cfg = PLOT_TYPES[choice]
    raw = {
        k: st.query_params.get(k)
        for k in st.query_params.keys()
        if k not in ("view", "choice")
    }
    p = _parse_plot_params(raw)

    head = st.columns([4, 1.3], vertical_alignment="center")
    with head[0]:
        st.title(f"{cfg['icon']} {cfg['title']} · {p.get('site', 'All')}")
    with head[1]:
        if st.button("⚙️ Change parameters", use_container_width=True):
            _settings_dialog(choice, in_plot_tab=True, current=raw)

    with st.spinner("Loading data and building plot..."):
        fig = cfg["chart"](p)
    st.plotly_chart(fig, use_container_width=True)
