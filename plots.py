"""
Plot type registry — the single place that defines every plot option.

Each entry has: icon, title, inputs(cur), chart(p).
All charts read via data.load_employees() and honour universal filters
via data.filter_df(df, p).
"""
import streamlit as st
import plotly.express as px
import pandas as pd
from data import load_employees, filter_df

SITES: list[str] = ["All", "TSN", "KCQ"]

CATEGORICAL_VARS = {
    "Gender":           "sex",
    "Work type (TT/GT)": "work_type",
    "Age group":        "age_group",
    "Department":       "dep_name",
    "Team":             "team_name",
    "Job title":        "job_title",
    "Contract type":    "contract_type",
    "English band":     "english_band",
    "English cert":     "english_cert",
    "Education":        "education",
    "Field of study":   "academic",
    "Labor group":      "labor_group",
    "Site":             "site",
    "Tenure bucket":    "_tenure_bucket",
}
HIGH_CARDINALITY = {"dep_name", "job_title", "team_name", "contract_type"}
_CAT_LABELS = list(CATEGORICAL_VARS.keys())


def _index_of(options: list, value, default: int = 0) -> int:
    """Index of value in options, or default — used to pre-select widgets."""
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return default


def _resolve_col(df: pd.DataFrame, col_key: str) -> pd.DataFrame:
    """Return a copy of df with the requested column (or derived tenure bucket)."""
    out = df.copy()
    if col_key == "_tenure_bucket":
        out[col_key] = pd.cut(
            out.tenure_years,
            bins=[-1, 1, 3, 7, 100],
            labels=["<1y", "1-3y", "3-7y", "7y+"],
        )
    return out


def _donut(
    df: pd.DataFrame,
    by: str,
    *,
    title: str,
    hole: float = 0.55,
    height: int | None = None,
    legend_below: bool = False,
):
    counts = df.groupby(by).size().reset_index(name="count")
    fig = px.pie(counts, values="count", names=by, hole=hole, title=title)
    fig.update_traces(
        textposition="inside",
        textinfo="percent+label",
        textfont_size=13,
        insidetextorientation="horizontal",
    )
    layout: dict = {}
    if height is not None:
        layout["height"] = height
    if legend_below:
        n_cats = counts[by].nunique()
        layout["showlegend"] = n_cats > 2
        layout["legend"] = dict(
            orientation="h",
            yanchor="top",
            y=-0.08,
            xanchor="center",
            x=0.5,
        )
        layout["margin"] = dict(t=45, b=50 if n_cats <= 2 else 70, l=5, r=5)
    if layout:
        fig.update_layout(**layout)
    return fig


def _top_n_bar(df: pd.DataFrame, col: str, n: int = 10, *, title: str):
    counts = df[col].value_counts().head(n).reset_index()
    counts.columns = [col, "count"]
    fig = px.bar(counts, x="count", y=col, orientation="h", title=title)
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    return fig


def _cross_tab_bar(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    *,
    title: str,
    top_n: int | None = None,
):
    sub = df.dropna(subset=[x_col, y_col])
    if top_n is not None:
        top_x = sub[x_col].value_counts().head(top_n).index
        sub = sub[sub[x_col].isin(top_x)]
    grouped = sub.groupby([x_col, y_col]).size().reset_index(name="count")
    fig = px.bar(
        grouped, x=x_col, y="count", color=y_col,
        barmode="group", title=title,
    )
    fig.update_xaxes(categoryorder="total descending")
    return fig


def _counts_inputs(cur: dict):
    variable = st.selectbox(
        "Variable",
        _CAT_LABELS,
        index=_index_of(_CAT_LABELS, cur.get("variable"), default=0),
    )
    col = CATEGORICAL_VARS[variable]
    inputs = {"variable": variable}
    if col in HIGH_CARDINALITY:
        inputs["top_n"] = st.slider(
            "Top N",
            5, 30,
            int(cur.get("top_n", 15)),
        )
    return inputs


def _counts_chart(p: dict):
    df = filter_df(load_employees(), p)
    label = p.get("variable", _CAT_LABELS[0])
    col = CATEGORICAL_VARS[label]
    df = _resolve_col(df, col).dropna(subset=[col])
    site = p.get("site", "")
    title = f"{label} · {site}"
    if col in HIGH_CARDINALITY: #use bar chart for categories with many unique values
        return _top_n_bar(df, col, n=int(p.get("top_n", 15)), title=title)
    return _donut(df, col, title=title)


def _cross_tab_inputs(cur: dict):
    var_x = st.selectbox(
        "X-axis",
        _CAT_LABELS,
        index=_index_of(_CAT_LABELS, cur.get("var_x"), default=_CAT_LABELS.index("Department")),
    )
    var_y = st.selectbox(
        "Colour / group",
        _CAT_LABELS,
        index=_index_of(_CAT_LABELS, cur.get("var_y"), default=_CAT_LABELS.index("Gender")),
    )
    inputs = {"var_x": var_x, "var_y": var_y}
    x_col = CATEGORICAL_VARS[var_x]
    if x_col in HIGH_CARDINALITY:
        inputs["top_n"] = st.slider(
            "Top N (X-axis)",
            5, 30,
            int(cur.get("top_n", 15)),
        )
    return inputs


def _cross_tab_chart(p: dict):
    df = filter_df(load_employees(), p)
    x_label = p.get("var_x", "Department")
    y_label = p.get("var_y", "Gender")
    x_col = CATEGORICAL_VARS[x_label]
    y_col = CATEGORICAL_VARS[y_label]
    df = _resolve_col(df, x_col)
    df = _resolve_col(df, y_col)
    top_n = int(p["top_n"]) if x_col in HIGH_CARDINALITY else None
    title = f"{y_label} × {x_label} · {p.get('site', '')}"
    return _cross_tab_bar(df, x_col, y_col, title=title, top_n=top_n)


def _jobs_inputs(cur):
    return {}


def _jobs_chart(p):
    df = filter_df(load_employees(), p)
    sub = (
        df.dropna(subset=["team_name"])
        .groupby(["team_name", "job_title"])
        .size()
        .reset_index(name="count")
    )
    fig = px.treemap(
        sub, path=["team_name", "job_title"], values="count",
        title=f"Jobs by team · {p.get('site', '')}",
    )
    fig.update_traces(
        textinfo="label+value",
        texttemplate="<b>%{label}</b><br>%{value:,}",
        textfont=dict(size=12),
        hovertemplate="<b>%{label}</b><br>Count: %{value:,}<extra></extra>",
    )
    return fig


def _tenure_inputs(cur):
    return {}


def _tenure_chart(p):
    df = filter_df(load_employees(), p)
    sub = df.dropna(subset=["company_date"])
    by_year = (
        sub.assign(year=sub.company_date.dt.year)
        .groupby("year")
        .size()
        .reset_index(name="hires")
    )
    return px.line(
        by_year, x="year", y="hires", markers=True,
        title=f"Hires per year · {p.get('site', '')}",
    )


PLOT_TYPES: dict[str, dict] = {
    "counts": {"icon": "📊", "title": "Category counts", "inputs": _counts_inputs, "chart": _counts_chart},
    "cross_tab": {"icon": "🔀", "title": "Cross-tab counts", "inputs": _cross_tab_inputs, "chart": _cross_tab_chart},
    "jobs": {"icon": "🧑‍🔧", "title": "Job titles", "inputs": _jobs_inputs, "chart": _jobs_chart},
    "tenure": {"icon": "⏳", "title": "Hiring trend", "inputs": _tenure_inputs, "chart": _tenure_chart},
}
