"""
Database layer — SQLAlchemy engine + ORM models + init_db().

Role of this file
-----------------
The app is DB-first: Excel files are an *input* to a one-off ETL, not a
runtime dependency. Everything the dashboard reads goes through the engine
configured here.

DATABASE_URL controls which backend we hit:

    sqlite:///viags.db                                (dev default)
    postgresql+psycopg2://user:pw@host:5432/viags     (docker-compose / Render)

Loaded from `.env` in dev (see `.env.example`); Render injects it as a real
environment variable in prod. The same model code runs against both.

Schema design — where do the Vietnamese names live?
---------------------------------------------------
`Employee` stores ONLY the FK codes (contract_code, english_code). The
Vietnamese names ("HĐLĐ không xác định...", "TOEIC", ...) live in exactly
one place — the lookup tables (contract_types, english_certs). Resolving
them happens at READ time via a LEFT JOIN in data.py.load_employees(),
not at write time. This is the textbook normalized design (3NF): every
fact lives in one place, no risk of the duplicate copy drifting from the
lookup.

`hr_no` is stored as String even though the source values are int64,
because it's an identifier (zero-padding, eventual non-numeric codes).
The same hr_no can legitimately exist at both TSN and KCQ, so uniqueness
is on the (hr_no, site) pair via UniqueConstraint, not on hr_no alone.

The PRAGMA-foreign-keys listener below is a no-op on Postgres (which
always enforces FKs) but mandatory on SQLite — without it SQLite would
silently accept rows pointing at non-existent contract / english codes.

How to verify (after `python -m db`)
------------------------------------
- viags.db appears next to this module; "Initialized schema on ..."
  prints to stdout.
- Three tables: employees, contract_types, english_certs.
- `employees` has an autoindex for the (hr_no, site) unique constraint
  plus named indexes on hr_no, site, dep_code, contract_code,
  english_code, labor_group.
- Foreign keys on employees point at contract_types.code /
  english_certs.code; an Employee insert with an unknown contract_code
  raises sqlalchemy.exc.IntegrityError (proves the PRAGMA listener fires).
"""

import pathlib
import os
from dotenv import load_dotenv
from sqlalchemy import (Boolean, Column, Date, Float, ForeignKey, Integer, UniqueConstraint, create_engine, event, String)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

#Set up the engine at import time so it's ready for the rest of the app to use.
load_dotenv()
DEFAULT_SQLITE_URL = "sqlite:///viags.db"
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)
connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite:///") else {}
engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

#Enforce foreign key constraints in SQLite
@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

Base = declarative_base()

# Lookup table for the "Contract type" 
class ContractType(Base):
    __tablename__ = "contract_types"
    code = Column(String, primary_key=True)        # "01"
    name_vn = Column(String, nullable=False)       # "HĐLĐ không xác định..."
    employees = relationship("Employee", back_populates="contract") # lets you write some_employee.contract.name_vn instead of doing a manual join

class EnglishCert(Base):
    __tablename__ = "english_certs"
    code = Column(String, primary_key=True)        # "01"
    name_vn = Column(String, nullable=False)       # "TOEIC"
    employees = relationship("Employee", back_populates="english") # lets you write some_employee.english.name_vn instead of doing a manual join

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    hr_no = Column(String, nullable=False, index=True)   # "3760" (Excel HR_No, cast to str by the ETL)
    site = Column(String, nullable=False, index=True)    # "TSN" or "KCQ"
    full_name = Column(String, nullable=False)
    sex = Column(String, nullable=False)           # "Nam" or "Nữ"
    work_type = Column(String, nullable=False)     # "TT" or "GT"
    birth_day = Column(Date)                       # ~20 of 2556 rows have no birthday in source
    age = Column(Integer)                          # NULL when birth_day is NULL
    age_group = Column(String)                     # NULL when age is NULL
    dep_code = Column(String, nullable=False, index=True)
    dep_name = Column(String, nullable=False)

    # "Chi tiết đơn vị" merged block — 3 TSN leadership rows have no
    # center/team/subteam assignment, so the whole block is nullable.
    center_code     = Column(String)
    center_name_vn  = Column(String)
    team_code       = Column(String)
    team_name       = Column(String)               # was "Tên Đội"
    subteam_code    = Column(String)
    subteam_name_vn = Column(String)

    job_code = Column(String, nullable=False)
    job_title = Column(String, nullable=False)
    contract_code = Column(String, ForeignKey("contract_types.code"), nullable=False, index=True)
    contract_duration_months = Column(Integer)
    contract_data_type_name = Column(String)
    begin_date = Column(Date)
    major_date = Column(Date)
    company_date = Column(Date)
    tenure_years = Column(Float)
    english_code = Column(String, ForeignKey("english_certs.code"), index=True)
    english_point = Column(Float)                  # IELTS values like 3.5 require Float, not Integer
    english_band = Column(String)                  # None/Basic/Intermediate/Upper-Int/Advanced
    education = Column(String)                     # Education_NameVN
    academic = Column(String)                      # Academic_NameVN
    labor_group = Column(String, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)

    contract = relationship("ContractType", back_populates="employees")
    english  = relationship("EnglishCert",  back_populates="employees")

    __table_args__ = (UniqueConstraint("hr_no", "site", name="uq_hr_site"),)


def init_db() -> None:
    """Create all tables. Idempotent — safe to call on every run."""
    if DATABASE_URL.startswith("sqlite:///"):
        sqlite_path = pathlib.Path(DATABASE_URL.removeprefix("sqlite:///"))
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print(f"Initialized schema on {DATABASE_URL}")