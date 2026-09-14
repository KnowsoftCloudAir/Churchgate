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
