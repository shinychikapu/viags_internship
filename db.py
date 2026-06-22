"""
Database layer — SQLAlchemy engine + ORM models + init_db().

The app is DB-first: Excel files are an input to a one-off ETL, not a
runtime dependency. Employee rows store FK codes only; Vietnamese names
are resolved at read time via LEFT JOINs in data.load_employees().
"""
import os
import pathlib
import streamlit as st

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean, Column, Date, Float, ForeignKey, Integer, String,
    UniqueConstraint, create_engine, event,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

load_dotenv()
DEFAULT_SQLITE_URL = "sqlite:///viags.db"
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or st.secrets.get("DATABASE_URL")
    or DEFAULT_SQLITE_URL
)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite:///") else {}
engine = create_engine(DATABASE_URL, future=True, connect_args=connect_args)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    if engine.dialect.name == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


Base = declarative_base()


class ContractType(Base):
    __tablename__ = "contract_types"
    code = Column(String, primary_key=True)
    name_vn = Column(String, nullable=False)
    employees = relationship("Employee", back_populates="contract")


class EnglishCert(Base):
    __tablename__ = "english_certs"
    code = Column(String, primary_key=True)
    name_vn = Column(String, nullable=False)
    employees = relationship("Employee", back_populates="english")


class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True)
    hr_no = Column(String, nullable=False, index=True)
    site = Column(String, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    sex = Column(String, nullable=False)
    work_type = Column(String, nullable=False)
    birth_day = Column(Date)
    age = Column(Integer)
    age_group = Column(String)
    dep_code = Column(String, nullable=False, index=True)
    dep_name = Column(String, nullable=False)
    center_code = Column(String)
    center_name_vn = Column(String)
    team_code = Column(String)
    team_name = Column(String)
    subteam_code = Column(String)
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
    english_point = Column(Float)
    english_band = Column(String)
    education = Column(String)
    academic = Column(String)
    labor_group = Column(String, nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)

    contract = relationship("ContractType", back_populates="employees")
    english = relationship("EnglishCert", back_populates="employees")

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
