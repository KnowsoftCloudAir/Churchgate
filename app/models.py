from datetime import datetime, timedelta
from typing import Optional
from sqlmodel import SQLModel, Field, Column, Text
import enum

class UserRole(str, enum.Enum):
    general_admin = "general_admin"
    presenter = "presenter"

class UserStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    suspended = "suspended"

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    full_name: str = ""
    hashed_password: str
    role: UserRole = Field(default=UserRole.presenter)
    status: UserStatus = Field(default=UserStatus.pending)
    login_number: Optional[str] = Field(default=None, index=True, unique=True)  # approved login number
    access_expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class LoginCode(SQLModel, table=True):
    """Admin-issued access codes: week / month / year."""
    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(index=True, unique=True)
    duration: str = Field(default="month")  # week | month | year
    issued_to_email: Optional[str] = None
    issued_to_user_id: Optional[int] = None
    is_used: bool = False
    created_by: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None  # code claim expiry (optional)
    notes: str = ""

class Presentation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    owner_id: int = Field(index=True)
    title: str = "Untitled presentation"
    theme: str = Field(default="midnight")  # midnight | aurora | churchgate
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    share_token: Optional[str] = Field(default=None, index=True)
    logo_path: Optional[str] = None
    footer_text: str = Field(default="")
    default_pattern: str = Field(default="gradient_teal")

class Slide(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    presentation_id: int = Field(index=True)
    position: int = Field(default=0)
    title: str = ""
    body: str = Field(default="", sa_column=Column(Text))
    extra_data: str = Field(default="", sa_column=Column(Text))  # Eleon Q&A source
    image_path: Optional[str] = None
    animation_in: str = Field(default="fade")   # fade | slideLeft | slideUp | zoom | flip
    animation_out: str = Field(default="fade")
    bg_color: str = Field(default="#0f172a")
    accent: str = Field(default="#14b8a6")
    notes: str = Field(default="", sa_column=Column(Text))
    layout_style: str = Field(default="title_body")  # title_body | image_left | image_right | image_bg | centered | chart
    icon_name: str = Field(default="")
    chart_type: str = Field(default="")  # bar | pie | line | doughnut
    chart_data: str = Field(default="", sa_column=Column(Text))  # JSON labels/values
    keyword_animation: bool = Field(default=True)
    word_animation: str = Field(default="fadeUp")  # none | fadeUp | typewriter | cascade
    online_image_url: Optional[str] = None
    pattern: str = Field(default="gradient_teal")
    image_style: str = Field(default="frame")
    word_emphasis: bool = Field(default=True)


class EvalSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    presentation_id: int = Field(index=True)
    owner_id: int = Field(index=True)
    title: str = Field(default="Training evaluation")
    token: str = Field(index=True, unique=True)
    is_active: bool = Field(default=True)
    allow_certificates: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvalQuestion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)
    position: int = Field(default=0)
    prompt: str = Field(sa_column=Column(Text))
    options: str = Field(default="", sa_column=Column(Text))  # JSON list or newline choices
    correct_answer: str = Field(default="")  # for scoring; empty = survey only


class EvalResponse(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)
    participant_name: str = Field(default="")
    participant_email: str = Field(default="")
    answers_json: str = Field(default="{}", sa_column=Column(Text))
    score_pct: float = Field(default=0.0)
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class PresentationQANote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    presentation_id: int = Field(index=True)
    question: str = Field(sa_column=Column(Text))
    answer: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LiveSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    presentation_id: int = Field(index=True)
    owner_id: int = Field(index=True)
    token: str = Field(index=True, unique=True)
    is_active: bool = Field(default=True)
    current_index: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LiveViewer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)
    name: str = Field(default="Guest")
    status: str = Field(default="pending")  # pending | admitted | denied
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LiveQuestion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)
    viewer_name: str = Field(default="Guest")
    text: str = Field(sa_column=Column(Text))
    answered: bool = Field(default=False)
    answer: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AppSetting(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    value: str = Field(default="", sa_column=Column(Text))
