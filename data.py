"""
Read side of the database — the bridge between db.py and the dashboard.

db.py defines how data is stored; etl.py loads it; data.py exposes a cached
DataFrame plus universal filters for the Streamlit app.
"""
import unicodedata

import pandas as pd
import streamlit as st
from db import engine

DATE_COLS = ("birth_day", "begin_date", "major_date", "company_date")


def _parse_active_only(value) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("false", "0", "no")


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

    # SQLite stores bool/date differently than Postgres; normalize dtypes.
    df["is_active"] = df["is_active"].astype(bool)
    for col in DATE_COLS:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def filter_df(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    if p.get("site") and p["site"] != "All":
        df = df[df.site == p["site"]]
    if _parse_active_only(p.get("active_only", True)):
        df = df[df.is_active]
    return df


SEARCH_RESULT_COLS = (
    "full_name",
    "sex",
    "birth_day",
    "dep_name",
    "job_title",
    "company_date",
    "tenure_years",
    "academic",
    "english_band",
)

SEARCH_DISPLAY_NAMES = {
    "full_name": "Name",
    "sex": "Sex",
    "birth_day": "BD",
    "dep_name": "dep_name",
    "job_title": "job_title",
    "company_date": "start_date",
    "tenure_years": "tenure_years",
    "academic": "academic",
    "english_band": "english_band",
}


def _norm_text(value: str) -> str:
    return unicodedata.normalize("NFC", str(value)).casefold()


def _hr_key(value) -> str:
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.lstrip("0") or "0"


def _name_match_mask(series: pd.Series, query: str) -> pd.Series:
    needle = _norm_text(query.strip())
    return series.fillna("").map(lambda v: needle in _norm_text(v))


def _hr_match_mask(series: pd.Series, query: str) -> pd.Series:
    q = query.strip()
    hr_str = series.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    q_key = _hr_key(q)
    hr_key = hr_str.map(_hr_key)
    return hr_str.str.contains(q, case=False, na=False, regex=False) | (hr_key == q_key)


def search_employees(
    df: pd.DataFrame,
    *,
    name: str = "",
    hr_no: str = "",
) -> pd.DataFrame:
    """Filter employees by partial name and/or HR number (case-insensitive)."""
    name = name.strip()
    hr_no = hr_no.strip()
    if not name and not hr_no:
        return df.iloc[0:0]

    mask = pd.Series(True, index=df.index)
    if name:
        mask &= _name_match_mask(df["full_name"], name)
    if hr_no:
        mask &= _hr_match_mask(df["hr_no"], hr_no)

    hits = df.loc[mask, list(SEARCH_RESULT_COLS)].copy()
    hits = hits.rename(columns=SEARCH_DISPLAY_NAMES)
    for col in ("BD", "start_date"):
        hits[col] = pd.to_datetime(hits[col], errors="coerce").dt.strftime("%d/%m/%Y")
    hits["tenure_years"] = hits["tenure_years"].apply(
        lambda v: int(v) if pd.notna(v) and v == int(v) else (round(v, 1) if pd.notna(v) else None)
    )
    return hits.fillna("—")
