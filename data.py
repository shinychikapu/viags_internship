"""
Read side of the database — the bridge between db.py and the dashboard.

Role of this file
-----------------
db.py defines HOW the data is stored (engine + ORM models).
etl.py defines HOW the data gets in (Excel -> validate -> upsert).
data.py defines HOW the dashboard reads it (cached DataFrame + filters).

The Streamlit app (ui.py / plots.py) imports from data.py only — it
never touches engine, Session, or any ORM model directly. This keeps
"how data is loaded" as a single concern in one file, so caching and
query tuning can change without rippling through the app.

Why a separate file from db.py
------------------------------
db.py is pure SQLAlchemy — no Streamlit imports — so it stays testable
in a notebook or a unit test. The @st.cache_data decorator below is a
Streamlit concern (cache lifetime, hashing of args, rerun semantics).
Keeping it out of db.py preserves that boundary.

----------------------------------------------------------------------------
What you need to build (in order)
----------------------------------------------------------------------------

TODO 1: Imports
    - pandas as pd
    - streamlit as st
    - from db import engine

TODO 2: load_employees() -> pd.DataFrame

    The single most important function in this file. Resolves the
    Vietnamese names from the lookup tables AT READ TIME, so the
    dashboard sees a flat DataFrame with these columns:

        e.* (everything on the employees table)
        + contract_type   <- joined from contract_types.name_vn
        + english_cert    <- joined from english_certs.name_vn

    Implementation:

        @st.cache_data(ttl=3600)
        def load_employees() -> pd.DataFrame:
            sql = '''
                SELECT
                    e.*,
                    ct.name_vn AS contract_type,
                    ec.name_vn AS english_cert
                FROM employees AS e
                LEFT JOIN contract_types AS ct ON e.contract_code = ct.code
                LEFT JOIN english_certs  AS ec ON e.english_code  = ec.code
            '''
            with engine.begin() as conn:
                return pd.read_sql(sql, conn)

    Why every piece is there:

      LEFT JOIN (not INNER):
        an employee with a missing contract_code still appears in the
        result, just with contract_type = NaN. INNER JOIN would silently
        drop them, which is a real foot-gun for KPI tiles.

      AS contract_type / AS english_cert:
        the rest of the app expects column names without the table
        prefix, and "ct.name_vn" would land in the DataFrame as a
        confusing column. Aliasing keeps the contract intact.

      with engine.begin() as conn:
        opens a connection, runs the SELECT in a transaction, closes
        the connection on exit. We don't need a Session here because
        we're doing a raw read, not ORM work — pd.read_sql wants a
        DBAPI/SQLAlchemy connection, not a Session.

      @st.cache_data(ttl=3600):
        first call hits the DB; subsequent calls within an hour serve
        the cached DataFrame. Without this, every Streamlit rerun
        (which happens on every interaction) would re-issue the query.
        ttl=3600 is one hour — long enough to be cheap, short enough
        that re-running the ETL shows up in the dashboard quickly.

TODO 3: filter_df(df, p) -> pd.DataFrame

    Apply the universal filters from the settings dialog. Pure pandas,
    no DB call — the cached DataFrame already has everything we need.

        def filter_df(df, p):
            if p.get("site") and p["site"] != "All":
                df = df[df.site == p["site"]]
            if p.get("active_only", True):
                df = df[df.is_active]
            if p.get("labor_groups"):
                df = df[df.labor_group.isin(p["labor_groups"])]
            return df

    Notes:
      - Each conditional is opt-in: missing/empty params mean "don't
        filter on this dimension".
      - active_only defaults to True (matches the settings-dialog default).
      - We never mutate the input df — every step returns a new view.

----------------------------------------------------------------------------
How to verify
----------------------------------------------------------------------------
After db.py + etl.py are done, in a Python shell:

    from data import load_employees, filter_df
    df = load_employees()
    print(df.shape)                            # ~(2556, 35) on the current snapshot
    print(df[["hr_no", "contract_code",
              "contract_type", "english_code",
              "english_cert"]].head())
    # contract_type and english_cert should be populated for most rows;
    # NaN only where the FK code on the employee was itself null.

    sub = filter_df(df, {"site": "TSN", "active_only": True})
    print(sub.site.unique(), sub.is_active.all())

----------------------------------------------------------------------------
Backend-portability notes (read before "fixing" the post-read casts)
----------------------------------------------------------------------------
SQLite has no native Boolean or Date types — it stores them as int(0/1)
and ISO-formatted strings respectively. pd.read_sql therefore returns
`is_active` as int64 and date columns as object/str when DATABASE_URL
points at SQLite. On Postgres the same query returns native bool /
datetime64[ns] dtypes. The casts inside load_employees() exist to
normalize that difference so the rest of the app sees one dtype contract
regardless of backend; in particular `df[df.is_active]` only works as a
boolean mask once `is_active` is actually bool, and chart code that
calls `df.company_date.dt.year` only works once dates are real datetimes.

----------------------------------------------------------------------------
Future query notes (write these later as new plots / KPIs are added)
----------------------------------------------------------------------------
- KPIs on the home overview can keep using load_employees() + groupby —
  pandas is plenty fast at this scale.
- If the data ever grows past tens of thousands of rows, consider:
    * pushing aggregations into SQL (e.g. COUNT(*) GROUP BY ...) rather
      than pandas, and exposing them as their own helpers here;
    * narrowing load_employees() to only the columns the dashboard reads;
    * dropping ttl=3600 in favor of a manual cache-bust after the ETL.
"""
import pandas as pd
import streamlit as st
from db import engine

DATE_COLS = ("birth_day", "begin_date", "major_date", "company_date")


@st.cache_data(ttl=3600)
def load_employees() -> pd.DataFrame:
    sql = """
        SELECT
            e.*,
            ct.name_vn AS contract_type,
            ec.name_vn AS english_cert
        FROM employees AS e
        LEFT JOIN contract_types AS ct ON e.contract_code = ct.code
        LEFT JOIN english_certs  AS ec ON e.english_code  = ec.code
    """
    with engine.begin() as conn:
        df = pd.read_sql(sql, conn)

    # SQLite returns Boolean as int64 and Date as ISO-string; normalize to
    # the dtypes Postgres would have produced natively. See the
    # "Backend-portability notes" section in the module docstring.
    df["is_active"] = df["is_active"].astype(bool)
    for col in DATE_COLS:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def filter_df(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    if p.get("site") and p["site"] != "All":
        df = df[df.site == p["site"]]
    if p.get("active_only", True):
        df = df[df.is_active]
    if p.get("labor_groups"):
        # _flatten_params in ui.py joins multiselect lists with "," for the
        # URL roundtrip, so accept either a list (called from home_screen)
        # or a comma-joined string (called from a plot tab via plot_view).
        groups = p["labor_groups"]
        if isinstance(groups, str):
            groups = [g for g in groups.split(",") if g]
        df = df[df.labor_group.isin(groups)]
    return df

