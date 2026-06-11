"""
Plot type registry — the SINGLE place that defines every plot option.

Pattern (kept identical to the placeholder version we just deleted):
    icon   : emoji shown on the home button
    title  : header text shown on the menu / plot screens
    inputs : function(cur) that draws the option-specific widgets (pre-filled
             from `cur`) and returns a dict of params
    chart  : function(p) that takes those params and returns a Plotly figure

Adding a new plot = ONE entry to PLOT_TYPES; no other edits needed.

All chart functions read the cached employees DataFrame via
data.load_employees() and apply the global filters via data.filter_df(df, p),
so every chart honours the universal Site / Active / Labor-group filters
from the settings dialog automatically.

----------------------------------------------------------------------------
What you need to build (in order)
----------------------------------------------------------------------------

TODO 1: SITES = ["All", "TSN", "KCQ"]
    Replaces the deleted `AIRPORTS = ["SGN", "NBA", "DAD"]`. Used by
    ui._settings_dialog to populate the global Site selector. The "All"
    sentinel means "don't filter on site" — see data.filter_df.

TODO 2: Shared chart helpers (private, `_underscore` prefix)
    Three small builders the deep-dive charts reuse:

      _donut(df, by, *, title, hole=0.55) -> px.pie figure
          df.groupby(by).size() -> px.pie(values=..., names=..., hole=hole).

      _age_pyramid(df) -> diverging horizontal bars
          Pivot to age_group × sex, negate the Nam column so it grows
          left, leave Nữ positive so it grows right, then
          px.bar(barmode='relative', orientation='h').

      _top_n_bar(df, col, n=10, *, title) -> horizontal bar
          df[col].value_counts().head(n) rendered with px.bar(orientation='h').

TODO 3: Deep-dive charts — one PLOT_TYPES entry each
    Each follows the inputs(cur) + chart(p) shape; all chart() bodies start
    with `df = filter_df(load_employees(), p)`:

      _sex_inputs / _sex_chart           donut + grouped bar by department
      _worktype_inputs / _chart          donut + stacked bar TT/GT per dep
      _age_inputs / _age_chart           histogram + age pyramid
      _jobs_inputs / _jobs_chart         treemap: team_name parent,
                                         job_title leaves
      _contract_inputs / _chart          donut + stacked bar
                                         contract × tenure_bucket
      _english_inputs / _chart           cert-type bar + TOEIC histogram
                                         with reference lines at 400/550/750
      _tenure_inputs / _chart            tenure_years histogram +
                                         "hires per year" line chart
      _education_inputs / _chart         Education donut +
                                         Academic top-N bar
      _site_compare_inputs / _chart      pick a metric, render TSN vs KCQ
                                         side-by-side (this one ignores
                                         the global Site filter on purpose)

TODO 4: Analytics chart
    Wraps analytics.pca_explorer(df). Single entry on the registry:

      _pca_inputs(cur)
        - colour_by: selectbox over
          ['sex', 'site', 'english_band', 'age_group']

      _pca_chart(p)
        - df       = filter_df(load_employees(), p)
        - pcs, evr = pca_explorer(df)
        - px.scatter(pcs, x='pc1', y='pc2', color=p['colour_by'],
                     hover_data=['hr_no', 'site', 'sex', 'age',
                                 'english_band', 'job_title'],
                     title=f"PCA explorer — variance "
                           f"{evr[0]:.0%} / {evr[1]:.0%}")

TODO 5: PLOT_TYPES registry
    Insertion order = order shown in the home grid.

        PLOT_TYPES = {
            "sex":          {"icon": "♂♀",  "title": "Sex split",
                              "inputs": _sex_inputs,
                              "chart":  _sex_chart},
            "worktype":     {"icon": "🧰",  "title": "Work type (TT/GT)",
                              "inputs": _worktype_inputs,
                              "chart":  _worktype_chart},
            "age":          {"icon": "🎂",  "title": "Age distribution",
                              "inputs": _age_inputs,
                              "chart":  _age_chart},
            "jobs":         {"icon": "🧑‍🔧", "title": "Job titles",
                              "inputs": _jobs_inputs,
                              "chart":  _jobs_chart},
            "contract":     {"icon": "📄",  "title": "Contracts",
                              "inputs": _contract_inputs,
                              "chart":  _contract_chart},
            "english":      {"icon": "🔤",  "title": "English certs",
                              "inputs": _english_inputs,
                              "chart":  _english_chart},
            "tenure":       {"icon": "⏳",  "title": "Tenure",
                              "inputs": _tenure_inputs,
                              "chart":  _tenure_chart},
            "education":    {"icon": "🎓",  "title": "Education",
                              "inputs": _education_inputs,
                              "chart":  _education_chart},
            "site_compare": {"icon": "🆚",  "title": "Site compare (TSN vs KCQ)",
                              "inputs": _site_compare_inputs,
                              "chart":  _site_compare_chart},
            "pca":          {"icon": "🧬",  "title": "PCA explorer",
                              "inputs": _pca_inputs,
                              "chart":  _pca_chart},
        }

----------------------------------------------------------------------------
How to verify
----------------------------------------------------------------------------
- Each chart() returns a plotly Figure (px.* or go.Figure).
- `streamlit run app.py` — every entry in PLOT_TYPES shows up as a button
  on the home grid; clicking opens the settings dialog; "Open plot in new
  tab" renders the chart in its own tab driven only by URL query params.
- During development, ship one entry at a time. The registry-with-stubs
  pattern means a half-built plots.py still launches the app — buttons
  for unfinished entries simply raise from inside their chart() body.
"""
import streamlit as st
import plotly.express as px

def _index_of(options: list, value, default: int = 0) -> int:
    """Index of value in options, or default — used to pre-select widgets."""
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return default


# TODO 1: SITES = ["All", "TSN", "KCQ"]
SITES: list[str] = ["All", "TSN", "KCQ"]


# TODO 2: shared chart helpers (_donut, _age_pyramid, _top_n_bar)
def _donut(df: pd.DataFrame, by: str, *, title: str, hole: float = 0.55):
    counts = df.groupby(by).size().reset_index(name="count")
    fig = px.pie(counts, values="count", names=by, hole=hole, title=title)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig

def _age_pyramid(df: pd.DataFrame):
    pyramid = df.groupby(["age_group", "sex"]).size().reset_index(name="count")

# TODO 3: deep-dive inputs() + chart() functions
#   _sex_*, _worktype_*, _age_*, _jobs_*, _contract_*,
#   _english_*, _tenure_*, _education_*, _site_compare_*


# TODO 4: analytics inputs() + chart() — wraps analytics.pca_explorer
#   _pca_inputs, _pca_chart


# TODO 5: registry — insertion order = home-grid order
PLOT_TYPES: dict[str, dict] = {}
