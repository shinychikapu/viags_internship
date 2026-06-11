"""
ETL: Excel (NhanSu - TSN.xlsx, NhanSu-KCQ.xlsx) -> validate -> upsert into DB.

Run as a one-off:  python -m etl

Role of this file
-----------------
Reads each Excel file, validates the columns we care about, derives the
columns the schema needs but the spreadsheet doesn't store directly
(age, tenure_years, english_band, is_active, ...), and upserts the result
into the `employees` table — plus populates the small lookup tables
(contract_types, english_certs).

This module is the ONLY place Excel is read. The Streamlit app never
touches xlsx files at runtime; it queries the database via data.py.

Why the source file looks weird
-------------------------------
Two unrelated quirks in the raw export, both worth knowing before touching
anything in this module:

1. Column-count drift between TSN and KCQ.
   TSN has 46 columns, KCQ has 49 — the mentor stripped bank columns from
   TSN for PII, and a handful of 'Unnamed: N' gaps shift around because of
   the merged-header structure. Selecting columns by positional index would
   silently misalign rows between files, so we MUST select by name from a
   hardcoded allowlist (COLUMNS_TO_KEEP).

2. Dual-header layout.
   - Row 8 is the visible Vietnamese sub-header row ("Đơn vị",
     "Tên đơn vị", ...) — what a human sees when they open the file.
   - Row 9 is a hidden English code-style header row (`HR_No`, `FullName`,
     ...) sitting underneath it.
   `skiprows=8` lands pandas on row 9, which is why most column names in
   this pipeline are English. Wherever the hidden English row has a gap,
   pandas surfaces the column as `Unnamed: N` instead. The EXCEL_RENAMES
   dict below patches those gaps in-memory — the xlsx file itself is
   never edited.

Two distinct rename passes — keep them straight:

  - EXCEL_RENAMES (applied in load_one) fixes Excel-side quirks:
    "Tên Đội" -> "TeamName" and similar. By the time the DataFrame
    reaches `upsert_employees`, every column in COLUMNS_TO_KEEP is
    already under its English name.
  - The schema-name renames happen INSIDE `upsert_employees`, when
    mapping pandas columns onto ORM fields:
        HR_No (int64 in Excel)  -> hr_no  (str on the model)
        Code_Contract            -> contract_code
        Code_ForeignLanguage     -> english_code
    The int64->str cast on HR_No is done in `derive()` — Employee.hr_no
    is a String column, so the cast must run before `bulk_save_objects`.

Reload strategy
---------------
Simplest first pass: DELETE all rows from `employees`, then bulk INSERT.
The dataset is ~2.5k rows and the app is read-mostly, so a full reload
per ETL run is fine. Later we can switch to a real upsert keyed by
(hr_no, site) if incremental loads become a thing.

How to verify (after `python -m etl`)
-------------------------------------
- "ETL complete: <N> rows upserted into employees." prints to stdout
  (~2.5k for the current snapshot).
- `from db import SessionLocal, Employee` then `s.query(Employee).count()`
  matches that number.
- Spot-checks: `tenure_years` ≈ (today - company_date).days / 365.25;
  `age_group` matches `age` against the [<30, 30-45, >45] bins.
- FK join works:

    SELECT e.hr_no, ct.name_vn
    FROM employees e
    LEFT JOIN contract_types ct ON e.contract_code = ct.code
    LIMIT 5;

  Every row should have a non-NULL name_vn — proves the lookup table
  got populated and the FK codes on employees match.
"""
import numpy as np
import pandas as pd
import pandera as pa
from db import SessionLocal, ContractType, EnglishCert, Employee, init_db

COLUMNS_TO_KEEP = [
    "HR_No", "FullName", "Dep_Code", "Dep_Name_VN",
    "Code_Job_Title", "JobTitle_NameVN", "Code_WorkingType",
    "BirthDay", "Code_Sex",
    "Education_NameVN", "Academic_NameVN",
    "ForeignLanguage_NameVN", "Code_ForeignLanguage", "ForeignLanguage_Point",
    "Contract_NameVN", "Code_Contract", "Contract_Duration",
    "BeginDate", "MajorDate", "CompanyDate",
    "Contract_Data_type_Name", "Labor_Group",
    # "Chi tiết đơn vị" merged block — Vietnamese-only on row 8, patched
    # into English by EXCEL_RENAMES in load_one() (TSN indices 36-41;
    # KCQ indices 39-44 because of the bank-column shift).
    "Center_Code", "Center_NameVN",
    "Team_Code",   "TeamName",
    "Subteam_Code", "Subteam_NameVN",
]

EXCEL_RENAMES = {
    "Phòng/ Trung tâm":     "Center_Code",
    "Tên Phòng/Trung tâm":  "Center_NameVN",
    "Đội":                  "Team_Code",
    "Tên Đội":              "TeamName",
    "Tổ/Kíp":               "Subteam_Code",
    "Tên Tổ/Kíp":           "Subteam_NameVN",
}


SCHEMA = pa.DataFrameSchema(
    {
        # Identifiers — both int at this stage; derive() casts to str later
        "HR_No":        pa.Column(int,  nullable=False, checks=pa.Check.ge(0)),
        "FullName":     pa.Column(str,  nullable=False),
        "site":         pa.Column(str,  checks=pa.Check.isin(["TSN", "KCQ"])),

        # Department / job
        "Dep_Code":         pa.Column(str, nullable=False),
        "Dep_Name_VN":      pa.Column(str, nullable=False),
        "Code_Job_Title":   pa.Column(str, nullable=False),
        "JobTitle_NameVN":  pa.Column(str, nullable=False),

        # Personal
        "Code_Sex":         pa.Column(str, checks=pa.Check.isin(["Nam", "Nữ"])),
        "Code_WorkingType": pa.Column(str, checks=pa.Check.isin(["TT", "GT"])),
        "BirthDay":         pa.Column("datetime64[ns]", nullable=True),

        # Education (sparse)
        "Education_NameVN": pa.Column(str, nullable=True),
        "Academic_NameVN":  pa.Column(str, nullable=True),

        # English cert (sparse)
        "ForeignLanguage_NameVN": pa.Column(str,   nullable=True),
        "Code_ForeignLanguage":   pa.Column(str,   nullable=True),  # already str ('00','02',...)
        "ForeignLanguage_Point":  pa.Column(float, nullable=True, checks=pa.Check.ge(0)),

        # Contract — Code_Contract is int here; derive() will cast to str
        "Contract_NameVN":         pa.Column(str, nullable=False),
        "Code_Contract":           pa.Column(int, nullable=False, checks=pa.Check.ge(0)),
        "Contract_Duration":       pa.Column(int, nullable=False, checks=pa.Check.ge(0)),
        "Contract_Data_type_Name": pa.Column(
            str, checks=pa.Check.isin(["Đang làm việc", "Tạm hoãn"]),
        ),

        # Dates (all nullable — esp. CompanyDate matters for tenure/forecast)
        "BeginDate":   pa.Column("datetime64[ns]", nullable=True),
        "MajorDate":   pa.Column("datetime64[ns]", nullable=True),
        "CompanyDate": pa.Column("datetime64[ns]", nullable=True),

        # Labor group
        "Labor_Group": pa.Column(
            str, checks=pa.Check.isin(["FULLTIME", "OUTSOURCE", "SUPPORT"]),
        ),

        # "Chi tiết đơn vị" block — patched by EXCEL_RENAMES, 3 nulls in TSN
        "Center_Code":    pa.Column(str, nullable=True),
        "Center_NameVN":  pa.Column(str, nullable=True),
        "Team_Code":      pa.Column(str, nullable=True),
        "TeamName":       pa.Column(str, nullable=True),
        "Subteam_Code":   pa.Column(str, nullable=True),
        "Subteam_NameVN": pa.Column(str, nullable=True),
    },
    strict=True,    # any extra column = error (catches drift)
    coerce=False,   # don't silently cast; raise on type mismatch
)

def load_one(path: str, site: str) -> pd.DataFrame:
    vn = pd.read_excel(
        path, sheet_name="Data_Import",
        header=None, skiprows=7, nrows=1,
    ).iloc[0].tolist()
    df = pd.read_excel(path, sheet_name="Data_Import", skiprows=8)

    renames = {
        en: EXCEL_RENAMES[vn_name]
        for en, vn_name in zip(df.columns, vn)
        if isinstance(en, str) and en.startswith("Unnamed")
        and isinstance(vn_name, str) and vn_name in EXCEL_RENAMES
    }
    df = df.rename(columns=renames)

    missing_cols = set(COLUMNS_TO_KEEP) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing columns in {path}: {missing_cols}")

    df = df[COLUMNS_TO_KEEP].copy()
    df["site"] = site
    return df

def derive(df) -> pd.DataFrame:
    # HR_No is int in Excel but str on the model — cast it here before upsert.
    df["HR_No"] = df["HR_No"].astype(str)

    # age, age_group — np.floor (Series has no .floor() method)
    today = pd.Timestamp("today").normalize()
    df["age"] = np.floor((today - df["BirthDay"]).dt.days / 365.25).astype("Int64")
    df["age_group"] = pd.cut(
        df["age"],
        bins=[-1, 29, 45, float("inf")],
        labels=["<30", "30-45", ">45"],
    )

    # tenure_years
    df["tenure_years"] = np.floor((today - df["CompanyDate"]).dt.days / 365.25).astype("Int64")

    # english_band — pass cert + point explicitly via lambda (df.apply gives a
    # full row Series, not unpacked args)
    df["english_band"] = df.apply(
        lambda r: _english_band(r["ForeignLanguage_NameVN"], r["ForeignLanguage_Point"]),
        axis=1,
    )

    # is_active (first pass: everyone in the snapshot is active)
    df["is_active"] = True

    return df

#helpers
def _english_band(cert: str | None, point: float | None) -> str | None:
    if cert is None or cert == "Không":
        return None
    if cert == "TOEIC":
        # cap absurd values like 8150 at the legitimate TOEIC max of 990
        p = min(point or 0, 990)
        if p < 400:   return "Basic"
        if p < 550:   return "Intermediate"
        if p < 750:   return "Upper-Int"
        return "Advanced"
    if cert == "IELTS":
        # IELTS bands map roughly: <5 Basic, 5-6 Int, 6-7 Upper, >=7 Advanced
        p = point or 0
        if p < 5:     return "Basic"
        if p < 6:     return "Intermediate"
        if p < 7:     return "Upper-Int"
        return "Advanced"
    if cert == "TOEFL":  # iBT 0-120
        p = point or 0
        if p < 60:    return "Basic"
        if p < 80:    return "Intermediate"
        if p < 100:   return "Upper-Int"
        return "Advanced"
    # CEFR levels — point column is meaningless, use the cert itself
    cefr = {"A1": "Basic", "A2": "Basic",
            "B1": "Intermediate", "B2": "Upper-Int",
            "C1": "Advanced", "C2": "Advanced"}
    if cert in cefr:
        return cefr[cert]
    # Bằng ĐH ngoại ngữ, Khác — treat as Advanced (degree) / None (other)
    if cert == "Bằng ĐH ngoại ngữ":
        return "Advanced"
    return None  # 'Khác' and anything else

def upsert_employees(df: pd.DataFrame) -> None:
    # Pandas NaN -> Python None so SQLAlchemy stores NULL, not "nan"
    df = df.replace({np.nan: None})
    with SessionLocal() as session:
        # ---- (a) lookups first (FK requirement) ----
        for _, r in (df[["Code_Contract", "Contract_NameVN"]]
                       .drop_duplicates().dropna().iterrows()):
            session.merge(ContractType(
                code    = str(r["Code_Contract"]),
                name_vn = r["Contract_NameVN"],
            ))
        for _, r in (df[["Code_ForeignLanguage", "ForeignLanguage_NameVN"]]
                       .drop_duplicates().dropna().iterrows()):
            session.merge(EnglishCert(
                code    = r["Code_ForeignLanguage"],
                name_vn = r["ForeignLanguage_NameVN"],
            ))

        # Flush the merged lookup rows so they're physically in the DB before
        # bulk_save_objects fires below. Required because (1) autoflush=False
        # on our SessionLocal and (2) bulk_save_objects bypasses the unit of
        # work entirely — without this, SQLite's FK PRAGMA rejects every
        # employees INSERT with "FOREIGN KEY constraint failed".
        session.flush()

        # ---- (b) full-snapshot replace of employees ----
        session.query(Employee).delete()
        records = [
            Employee(
                hr_no         = str(r["HR_No"]),
                site          = r["site"],
                full_name     = r["FullName"],
                sex           = r["Code_Sex"],
                work_type     = r["Code_WorkingType"],
                birth_day     = r["BirthDay"],
                age           = r["age"],
                age_group     = str(r["age_group"]) if r["age_group"] is not None else None,
                dep_code      = r["Dep_Code"],
                dep_name      = r["Dep_Name_VN"],
                center_code     = r["Center_Code"],
                center_name_vn  = r["Center_NameVN"],
                team_code       = r["Team_Code"],
                team_name       = r["TeamName"],
                subteam_code    = r["Subteam_Code"],
                subteam_name_vn = r["Subteam_NameVN"],
                job_code      = r["Code_Job_Title"],
                job_title     = r["JobTitle_NameVN"],
                contract_code = str(r["Code_Contract"]),
                contract_duration_months = r["Contract_Duration"],
                contract_data_type_name  = r["Contract_Data_type_Name"],
                begin_date    = r["BeginDate"],
                major_date    = r["MajorDate"],
                company_date  = r["CompanyDate"],
                tenure_years  = r["tenure_years"],
                english_code  = r["Code_ForeignLanguage"],
                english_point = r["ForeignLanguage_Point"],
                english_band  = r["english_band"],
                education     = r["Education_NameVN"],
                academic      = r["Academic_NameVN"],
                labor_group   = r["Labor_Group"],
                is_active     = bool(r["is_active"]),
            )
            for _, r in df.iterrows()
        ]
        session.bulk_save_objects(records)
        session.commit()


def run(paths=(("NhanSu - TSN.xlsx", "TSN"),
               ("NhanSu-KCQ.xlsx",   "KCQ"))) -> None:
    init_db()
    df = pd.concat([load_one(p, s) for p, s in paths], ignore_index=True)
    df = SCHEMA.validate(df)
    df = derive(df)
    upsert_employees(df)
    print(f"ETL complete: {len(df)} rows upserted into employees.")


if __name__ == "__main__":
    run()
