from typing import Optional, List
from datetime import datetime, date
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from sqlalchemy import Text, UniqueConstraint
import enum

class UserRole(str, enum.Enum):
    general_admin = "general_admin"
    church_admin = "church_admin"      # Admin of a registered church unit
    data_officer = "data_officer"      # Can enter weekly stats at district
    member = "member"

class ChurchLevel(str, enum.Enum):
    global_church = "global"
    country = "country"
    state = "state"
    group = "group"
    district = "district"

class MemberStatus(str, enum.Enum):
    member = "member"
    worker = "worker"
    leader = "leader"

class WorkerType(str, enum.Enum):
    usher = "usher"
    choir = "choir"
    prayer = "prayer"
    drama = "drama"
    evangelist = "evangelist"
    media = "media"
    protocol = "protocol"
    other = "other"

class LeaderType(str, enum.Enum):
    global_pastor = "global_pastor"
    country_pastor = "country_pastor"
    state_pastor = "state_pastor"
    group_pastor = "group_pastor"
    coordinator = "coordinator"
    student_leader = "student_leader"
    campus_leader = "campus_leader"
    children_leader = "children_leader"
    women_leader = "women_leader"
    bible_study_teacher = "bible_study_teacher"
    representative = "representative"
    other = "other"

class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

# ---------- Core hierarchy unit ----------
class ChurchUnit(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("code", name="uq_church_code"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True)                    # Universal code e.g. GLB-001, NG-LAG-GRP1-DST3
    name: str
    level: ChurchLevel
    parent_id: Optional[int] = Field(default=None, foreign_key="churchunit.id")
    global_code: Optional[str] = None
    country_code: Optional[str] = None
    state_code: Optional[str] = None
    group_code: Optional[str] = None
    district_code: Optional[str] = None
    country_name: Optional[str] = None
    state_name: Optional[str] = None
    doctrine: Optional[str] = Field(default=None, sa_column=Column(Text))
    activity_days: Optional[str] = None              # e.g. "Sunday,Wednesday,Friday"
    owner_name: Optional[str] = None
    resident_pastor: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    approval_status: str = Field(default="pending")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    members: List["ChurchMember"] = Relationship(back_populates="church")
    stats: List["WeeklyStat"] = Relationship(back_populates="church")

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    full_name: str
    role: UserRole = Field(default=UserRole.church_admin)
    church_id: Optional[int] = Field(default=None, foreign_key="churchunit.id")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

class ChurchMember(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    church_id: int = Field(foreign_key="churchunit.id")
    full_name: str
    gender: Optional[str] = None          # male / female
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    date_of_birth: Optional[date] = None
    status: MemberStatus = Field(default=MemberStatus.member)
    worker_type: Optional[str] = None     # if worker
    leader_type: Optional[str] = None     # if leader
    joined_date: Optional[date] = None
    is_active: bool = Field(default=True)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    church: ChurchUnit = Relationship(back_populates="members")

class WeeklyStat(SQLModel, table=True):
    """Primary data entered at District level – aggregates upward."""
    id: Optional[int] = Field(default=None, primary_key=True)
    church_id: int = Field(foreign_key="churchunit.id")
    week_start: date                       # Monday of the week
    # Attendance
    adult_male: int = 0
    adult_female: int = 0
    children_boys: int = 0
    children_girls: int = 0
    youth_male: int = 0
    youth_female: int = 0
    # Finance
    offering: float = 0.0
    tithe: float = 0.0
    donation: float = 0.0
    # Growth
    special_program_attendance: int = 0
    newcomers: int = 0
    converts: int = 0
    counseling: int = 0
    members_in_need: int = 0
    notes: Optional[str] = None
    entered_by: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    church: ChurchUnit = Relationship(back_populates="stats")

class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    church_id: Optional[int] = None
    user_id: Optional[int] = None
    action: str
    detail: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
