"""
ETL: Excel (NhanSu - TSN.xlsx, NhanSu-KCQ.xlsx) -> validate -> upsert into DB.

Run as a one-off:  python -m etl

This is the only place Excel is read. The Streamlit app queries the DB via
data.py. Columns are selected by name (COLUMNS_TO_KEEP), never by position,
because TSN and KCQ have different column counts after the mentor removed
bank-account fields from TSN.
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
    "Center_Code", "Center_NameVN",
    "Team_Code", "TeamName",
    "Subteam_Code", "Subteam_NameVN",
]

EXCEL_RENAMES = {
    "Phòng/ Trung tâm": "Center_Code",
    "Tên Phòng/Trung tâm": "Center_NameVN",
    "Đội": "Team_Code",
    "Tên Đội": "TeamName",
    "Tổ/Kíp": "Subteam_Code",
    "Tên Tổ/Kíp": "Subteam_NameVN",
}

SCHEMA = pa.DataFrameSchema(
    {
        "HR_No": pa.Column(int, nullable=False, checks=pa.Check.ge(0)),
        "FullName": pa.Column(str, nullable=False),
        "site": pa.Column(str, checks=pa.Check.isin(["TSN", "KCQ"])),
        "Dep_Code": pa.Column(str, nullable=False),
        "Dep_Name_VN": pa.Column(str, nullable=False),
        "Code_Job_Title": pa.Column(str, nullable=False),
        "JobTitle_NameVN": pa.Column(str, nullable=False),
        "Code_Sex": pa.Column(str, checks=pa.Check.isin(["Nam", "Nữ"])),
        "Code_WorkingType": pa.Column(str, checks=pa.Check.isin(["TT", "GT"])),
        "BirthDay": pa.Column("datetime64[ns]", nullable=True),
        "Education_NameVN": pa.Column(str, nullable=True),
        "Academic_NameVN": pa.Column(str, nullable=True),
        "ForeignLanguage_NameVN": pa.Column(str, nullable=True),
        "Code_ForeignLanguage": pa.Column(str, nullable=True),
        "ForeignLanguage_Point": pa.Column(float, nullable=True, checks=pa.Check.ge(0)),
        "Contract_NameVN": pa.Column(str, nullable=False),
        "Code_Contract": pa.Column(int, nullable=False, checks=pa.Check.ge(0)),
        "Contract_Duration": pa.Column(int, nullable=False, checks=pa.Check.ge(0)),
        "Contract_Data_type_Name": pa.Column(
            str, checks=pa.Check.isin(["Đang làm việc", "Tạm hoãn"]),
        ),
        "BeginDate": pa.Column("datetime64[ns]", nullable=True),
        "MajorDate": pa.Column("datetime64[ns]", nullable=True),
        "CompanyDate": pa.Column("datetime64[ns]", nullable=True),
        "Labor_Group": pa.Column(
            str, checks=pa.Check.isin(["FULLTIME", "OUTSOURCE", "SUPPORT"]),
        ),
        "Center_Code": pa.Column(str, nullable=True),
        "Center_NameVN": pa.Column(str, nullable=True),
        "Team_Code": pa.Column(str, nullable=True),
        "TeamName": pa.Column(str, nullable=True),
        "Subteam_Code": pa.Column(str, nullable=True),
        "Subteam_NameVN": pa.Column(str, nullable=True),
    },
    strict=True,
    coerce=False,
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
    df["HR_No"] = df["HR_No"].astype(str)

    today = pd.Timestamp("today").normalize()
    df["age"] = np.floor((today - df["BirthDay"]).dt.days / 365.25).astype("Int64")
    df["age_group"] = pd.cut(
        df["age"],
        bins=[-1, 29, 45, float("inf")],
        labels=["<30", "30-45", ">45"],
    )
    df["tenure_years"] = np.floor((today - df["CompanyDate"]).dt.days / 365.25).astype("Int64")
    df["english_band"] = [
        _english_band(cert, point)
        for cert, point in zip(
            df["ForeignLanguage_NameVN"],
            df["ForeignLanguage_Point"],
        )
    ]
    df["is_active"] = True
    return df


def _english_band(cert: str | None, point: float | None) -> str | None:
    if cert is None or cert == "Không":
        return None
    if cert == "TOEIC":
        p = min(point or 0, 990)
        if p < 400:
            return "Basic"
        if p < 550:
            return "Intermediate"
        if p < 750:
            return "Upper-Int"
        return "Advanced"
    if cert == "IELTS":
        p = point or 0
        if p < 5:
            return "Basic"
        if p < 6:
            return "Intermediate"
        if p < 7:
            return "Upper-Int"
        return "Advanced"
    if cert == "TOEFL":
        p = point or 0
        if p < 60:
            return "Basic"
        if p < 80:
            return "Intermediate"
        if p < 100:
            return "Upper-Int"
        return "Advanced"
    cefr = {
        "A1": "Basic", "A2": "Basic",
        "B1": "Intermediate", "B2": "Upper-Int",
        "C1": "Advanced", "C2": "Advanced",
    }
    if cert in cefr:
        return cefr[cert]
    if cert == "Bằng ĐH ngoại ngữ":
        return "Advanced"
    return None


def _employee_records(df: pd.DataFrame) -> list[dict]:
    df = df.replace({np.nan: None})
    records = []
    for r in df.to_dict("records"):
        records.append({
            "hr_no": str(r["HR_No"]),
            "site": r["site"],
            "full_name": r["FullName"],
            "sex": r["Code_Sex"],
            "work_type": r["Code_WorkingType"],
            "birth_day": r["BirthDay"],
            "age": r["age"],
            "age_group": str(r["age_group"]) if r["age_group"] is not None else None,
            "dep_code": r["Dep_Code"],
            "dep_name": r["Dep_Name_VN"],
            "center_code": r["Center_Code"],
            "center_name_vn": r["Center_NameVN"],
            "team_code": r["Team_Code"],
            "team_name": r["TeamName"],
            "subteam_code": r["Subteam_Code"],
            "subteam_name_vn": r["Subteam_NameVN"],
            "job_code": r["Code_Job_Title"],
            "job_title": r["JobTitle_NameVN"],
            "contract_code": str(r["Code_Contract"]),
            "contract_duration_months": r["Contract_Duration"],
            "contract_data_type_name": r["Contract_Data_type_Name"],
            "begin_date": r["BeginDate"],
            "major_date": r["MajorDate"],
            "company_date": r["CompanyDate"],
            "tenure_years": r["tenure_years"],
            "english_code": r["Code_ForeignLanguage"],
            "english_point": r["ForeignLanguage_Point"],
            "english_band": r["english_band"],
            "education": r["Education_NameVN"],
            "academic": r["Academic_NameVN"],
            "labor_group": r["Labor_Group"],
            "is_active": bool(r["is_active"]),
        })
    return records


def upsert_employees(df: pd.DataFrame) -> None:
    with SessionLocal() as session:
        print("  → contract & english lookup tables…")
        for _, r in (
            df[["Code_Contract", "Contract_NameVN"]]
            .drop_duplicates()
            .dropna()
            .iterrows()
        ):
            session.merge(ContractType(
                code=str(r["Code_Contract"]),
                name_vn=r["Contract_NameVN"],
            ))
        for _, r in (
            df[["Code_ForeignLanguage", "ForeignLanguage_NameVN"]]
            .drop_duplicates()
            .dropna()
            .iterrows()
        ):
            session.merge(EnglishCert(
                code=r["Code_ForeignLanguage"],
                name_vn=r["ForeignLanguage_NameVN"],
            ))

        session.flush()
        print("  → clearing old employee rows…")
        session.query(Employee).delete()
        records = _employee_records(df)
        print(f"  → inserting {len(records):,} employees (remote DB — may take a few min)…")
        batch_size = 500
        for start in range(0, len(records), batch_size):
            session.bulk_insert_mappings(Employee, records[start:start + batch_size])
        session.commit()


def run(paths=(("NhanSu - TSN.xlsx", "TSN"), ("NhanSu-KCQ.xlsx", "KCQ"))) -> None:
    init_db()
    print("Reading Excel files…")
    df = pd.concat([load_one(p, s) for p, s in paths], ignore_index=True)
    print(f"  → {len(df):,} rows loaded")
    print("Validating schema…")
    df = SCHEMA.validate(df)
    print("Deriving age, tenure, english band…")
    df = derive(df)
    print("Writing to database…")
    upsert_employees(df)
    print(f"ETL complete: {len(df):,} rows upserted into employees.")


if __name__ == "__main__":
    run()
