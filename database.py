from sqlmodel import SQLModel, create_engine, Session
from dotenv import load_dotenv
from sqlalchemy import text
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////tmp/churchgate.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args, pool_pre_ping=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    # Add missing columns on existing Postgres/SQLite DBs (no Alembic)
    alters = [
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS tithe_account_name VARCHAR",
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS tithe_account_number VARCHAR",
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS tithe_bank_name VARCHAR",
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS offering_account_name VARCHAR",
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS offering_account_number VARCHAR",
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS offering_bank_name VARCHAR",
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS pastor_phone VARCHAR",
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS pastor_email VARCHAR",
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS weekly_activities_note TEXT",
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS latitude FLOAT",
        "ALTER TABLE churchunit ADD COLUMN IF NOT EXISTS longitude FLOAT",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS can_create_churches BOOLEAN DEFAULT FALSE",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS can_approve_members BOOLEAN DEFAULT FALSE",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS can_enter_stats BOOLEAN DEFAULT FALSE",
        "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS can_see_member_count BOOLEAN DEFAULT FALSE",
        "ALTER TABLE churchmember ADD COLUMN IF NOT EXISTS custom_title VARCHAR",
        "ALTER TABLE churchmember ADD COLUMN IF NOT EXISTS sex VARCHAR",
        "ALTER TABLE churchmember ADD COLUMN IF NOT EXISTS age_category VARCHAR",
        "ALTER TABLE churchmember ADD COLUMN IF NOT EXISTS confession VARCHAR",
        "ALTER TABLE churchmember ADD COLUMN IF NOT EXISTS prayer_request TEXT",
        "ALTER TABLE churchmember ADD COLUMN IF NOT EXISTS whatsapp VARCHAR",
        "ALTER TABLE churchmember ADD COLUMN IF NOT EXISTS discontinue_requested BOOLEAN DEFAULT FALSE",
    ]
    # SQLite does not support IF NOT EXISTS on ADD COLUMN the same way in older versions
    is_sqlite = DATABASE_URL.startswith("sqlite")
    with engine.begin() as conn:
        for stmt in alters:
            try:
                if is_sqlite:
                    # SQLite: ignore duplicate column errors
                    s = stmt.replace(" IF NOT EXISTS", "").replace('\"user\"', "user")
                    conn.execute(text(s))
                else:
                    conn.execute(text(stmt))
            except Exception:
                pass


def get_session():
    with Session(engine) as session:
        yield session
