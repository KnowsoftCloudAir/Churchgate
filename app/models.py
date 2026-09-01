from typing import Optional, List
from datetime import datetime, date
from sqlmodel import SQLModel, Field, Relationship, Column, JSON
from sqlalchemy import Text, UniqueConstraint
import enum

class UserRole(str, enum.Enum):
    general_admin = "general_admin"
    church_admin = "church_admin"
    data_officer = "data_officer"
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
    pastor = "pastor"

class SexType(str, enum.Enum):
    brother = "brother"
    sister = "sister"

class AgeCategory(str, enum.Enum):
    child = "child"           # 1-15
    youth = "youth"           # 16-20
    campus = "campus"         # 21-40 young adult/campus
    adult = "adult"           # 30-100

class Confession(str, enum.Enum):
    saved = "saved"
    unsaved = "unsaved"
    backslidden = "backslidden"
    restored = "restored"

class ApprovalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    discontinued = "discontinued"

class ChurchUnit(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("code", name="uq_church_code"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True)
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
    activity_days: Optional[str] = None
    owner_name: Optional[str] = None
    resident_pastor: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    # Remittance accounts (shown on member dashboard)
    tithe_account_name: Optional[str] = None
    tithe_account_number: Optional[str] = None
    tithe_bank_name: Optional[str] = None
    offering_account_name: Optional[str] = None
    offering_account_number: Optional[str] = None
    offering_bank_name: Optional[str] = None
    pastor_phone: Optional[str] = None
    pastor_email: Optional[str] = None
    weekly_activities_note: Optional[str] = Field(default=None, sa_column=Column(Text))
    approval_status: str = Field(default="pending")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    members: List["ChurchMember"] = Relationship(back_populates="church")
    stats: List["WeeklyStat"] = Relationship(back_populates="church")
    programs: List["SpecialProgram"] = Relationship(back_populates="church")

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    full_name: str
    role: UserRole = Field(default=UserRole.member)
    church_id: Optional[int] = Field(default=None, foreign_key="churchunit.id")
    member_id: Optional[int] = Field(default=None, foreign_key="churchmember.id")
    can_enter_stats: bool = Field(default=False)  # designated for weekly attendance
    can_create_churches: bool = Field(default=False)  # GA grants: create child churches
    can_approve_members: bool = Field(default=False)  # GA grants: approve member registrations
    can_see_member_count: bool = Field(default=False)  # see district member totals
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None

class ChurchMember(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    church_id: int = Field(foreign_key="churchunit.id")  # district (or unit) they belong to
    global_church_id: Optional[int] = None
    country_church_id: Optional[int] = None
    state_church_id: Optional[int] = None
    group_church_id: Optional[int] = None
    full_name: str
    sex: Optional[str] = None              # brother / sister
    age_category: Optional[str] = None     # child, youth, campus, adult
    confession: Optional[str] = None       # saved, unsaved, backslidden, restored
    member_since: Optional[date] = None
    prayer_request: Optional[str] = Field(default=None, sa_column=Column(Text))
    address: Optional[str] = None
    whatsapp: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = Field(default=None, index=True)
    profile_pic: Optional[str] = None
    status: str = Field(default="member")  # member, worker, leader, pastor
    worker_type: Optional[str] = None
    leader_type: Optional[str] = None
    custom_title: Optional[str] = None  # editable title from sub-admin
    approval_status: str = Field(default="pending")  # pending, approved, rejected, discontinued
    discontinue_requested: bool = Field(default=False)
    is_active: bool = Field(default=True)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    church: Optional[ChurchUnit] = Relationship(back_populates="members")

class WeeklyStat(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    church_id: int = Field(foreign_key="churchunit.id")
    week_start: date
    adult_male: int = 0
    adult_female: int = 0
    children_boys: int = 0
    children_girls: int = 0
    youth_male: int = 0
    youth_female: int = 0
    offering: float = 0.0
    tithe: float = 0.0
    donation: float = 0.0
    special_program_attendance: int = 0
    newcomers: int = 0
    converts: int = 0
    counseling: int = 0
    members_in_need: int = 0
    notes: Optional[str] = None
    entered_by: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    church: Optional[ChurchUnit] = Relationship(back_populates="stats")

class SpecialProgram(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    church_id: int = Field(foreign_key="churchunit.id")  # creating unit
    title: str
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    program_date: Optional[date] = None
    location: Optional[str] = None
    broadcast_to: str = Field(default="district")  # district | group | state | country | global
    created_by: Optional[int] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    church: Optional[ChurchUnit] = Relationship(back_populates="programs")
    photos: List["ProgramPhoto"] = Relationship(back_populates="program")

class ProgramPhoto(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    program_id: int = Field(foreign_key="specialprogram.id")
    file_path: str
    caption: Optional[str] = None
    uploaded_by: Optional[int] = None  # church admin only
    created_at: datetime = Field(default_factory=datetime.utcnow)

    program: Optional[SpecialProgram] = Relationship(back_populates="photos")
    likes: List["PhotoLike"] = Relationship(back_populates="photo")
    comments: List["PhotoComment"] = Relationship(back_populates="photo")

class PhotoLike(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    photo_id: int = Field(foreign_key="programphoto.id")
    user_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    photo: Optional[ProgramPhoto] = Relationship(back_populates="likes")

class PhotoComment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    photo_id: int = Field(foreign_key="programphoto.id")
    user_id: int = Field(foreign_key="user.id")
    body: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    photo: Optional[ProgramPhoto] = Relationship(back_populates="comments")

class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    church_id: Optional[int] = None
    user_id: Optional[int] = None
    action: str
    detail: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class SpecialProject(SQLModel, table=True):
    """Fundraising / special project with collection tracking for admin dashboard."""
    id: Optional[int] = Field(default=None, primary_key=True)
    church_id: int = Field(foreign_key="churchunit.id")
    title: str
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    target_amount: float = Field(default=0.0)
    account_name: Optional[str] = None
    account_number: Optional[str] = None
    bank_name: Optional[str] = None
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class SpecialProjectContribution(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="specialproject.id")
    amount: float = Field(default=0.0)
    contributor_name: Optional[str] = None
    note: Optional[str] = None
    recorded_by: Optional[int] = None
    contributed_at: datetime = Field(default_factory=datetime.utcnow)
