"""Complete sample data: Knowsoft Bible Church hierarchy + members + weekly stats."""
from datetime import date, timedelta
from sqlmodel import Session, select
from app.models import (
    User, UserRole, ChurchUnit, ChurchLevel, ChurchMember,
    WeeklyStat, MemberStatus
)
from app.auth import get_password_hash


def seed_knowsoft_bible_church(session: Session) -> None:
    # Skip if already seeded
    existing = session.exec(
        select(ChurchUnit).where(ChurchUnit.name == "Knowsoft Bible Church")
    ).first()
    if existing:
        print("ℹ️ Sample church already exists – skip seed")
        return

    # ---------- Hierarchy ----------
    # Global
    global_c = ChurchUnit(
        code="KBC-GLOBAL",
        name="Knowsoft Bible Church",
        level=ChurchLevel.global_church,
        global_code="KBC-GLOBAL",
        doctrine="We believe in the authority of Scripture, salvation by grace through faith in Jesus Christ, the Trinity, and the mission to make disciples of all nations.",
        activity_days="Sunday, Wednesday, Friday",
        owner_name="Apostle David Knowsoft",
        resident_pastor="Apostle David Knowsoft",
        address="Knowsoft Global HQ, Abuja, Nigeria",
        phone="+234-800-000-0001",
        email="global@knowsoftbible.org",
        country_name="Nigeria",
        approval_status="approved",
        is_active=True,
    )
    session.add(global_c)
    session.commit()
    session.refresh(global_c)

    # Country – Nigeria
    country = ChurchUnit(
        code="KBC-NG",
        name="Knowsoft Bible Church – Nigeria",
        level=ChurchLevel.country,
        parent_id=global_c.id,
        global_code="KBC-GLOBAL",
        country_code="KBC-NG",
        country_name="Nigeria",
        resident_pastor="Rev. Samuel Okonkwo",
        email="nigeria@knowsoftbible.org",
        approval_status="approved",
        is_active=True,
    )
    session.add(country)
    session.commit()
    session.refresh(country)

    # State – Lagos
    state = ChurchUnit(
        code="KBC-NG-LAG",
        name="Knowsoft Bible Church – Lagos State",
        level=ChurchLevel.state,
        parent_id=country.id,
        global_code="KBC-GLOBAL",
        country_code="KBC-NG",
        state_code="KBC-NG-LAG",
        country_name="Nigeria",
        state_name="Lagos",
        resident_pastor="Pastor Grace Adeyemi",
        email="lagos@knowsoftbible.org",
        approval_status="approved",
        is_active=True,
    )
    session.add(state)
    session.commit()
    session.refresh(state)

    # Group – Ikeja
    group = ChurchUnit(
        code="KBC-NG-LAG-IKE",
        name="Knowsoft Bible Church – Ikeja Group",
        level=ChurchLevel.group,
        parent_id=state.id,
        global_code="KBC-GLOBAL",
        country_code="KBC-NG",
        state_code="KBC-NG-LAG",
        group_code="KBC-NG-LAG-IKE",
        country_name="Nigeria",
        state_name="Lagos",
        resident_pastor="Pastor Michael Bello",
        email="ikeja@knowsoftbible.org",
        approval_status="approved",
        is_active=True,
    )
    session.add(group)
    session.commit()
    session.refresh(group)

    # District – Allen Avenue (primary unit)
    district = ChurchUnit(
        code="KBC-NG-LAG-IKE-ALLEN",
        name="Knowsoft Bible Church – Allen Avenue District",
        level=ChurchLevel.district,
        parent_id=group.id,
        global_code="KBC-GLOBAL",
        country_code="KBC-NG",
        state_code="KBC-NG-LAG",
        group_code="KBC-NG-LAG-IKE",
        district_code="KBC-NG-LAG-IKE-ALLEN",
        country_name="Nigeria",
        state_name="Lagos",
        doctrine=global_c.doctrine,
        activity_days="Sunday, Wednesday, Friday",
        owner_name="Apostle David Knowsoft",
        resident_pastor="Pastor Ruth Okoro",
        address="12 Allen Avenue, Ikeja, Lagos",
        phone="+234-801-234-5678",
        email="allen@knowsoftbible.org",
        approval_status="approved",
        is_active=True,
    )
    session.add(district)
    session.commit()
    session.refresh(district)

    # ---------- Admin users for each level ----------
    def add_admin(email, name, church_id, password="Church@12345"):
        if session.exec(select(User).where(User.email == email)).first():
            return
        u = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=name,
            role=UserRole.church_admin,
            church_id=church_id,
            is_active=True,
        )
        session.add(u)

    add_admin("global@knowsoftbible.org", "Apostle David Knowsoft", global_c.id)
    add_admin("nigeria@knowsoftbible.org", "Rev. Samuel Okonkwo", country.id)
    add_admin("lagos@knowsoftbible.org", "Pastor Grace Adeyemi", state.id)
    add_admin("ikeja@knowsoftbible.org", "Pastor Michael Bello", group.id)
    add_admin("allen@knowsoftbible.org", "Pastor Ruth Okoro", district.id)
    # Data officer at district
    if not session.exec(select(User).where(User.email == "data@allen.knowsoftbible.org")).first():
        session.add(User(
            email="data@allen.knowsoftbible.org",
            hashed_password=get_password_hash("Data@12345"),
            full_name="Bro. James Data Officer",
            role=UserRole.data_officer,
            church_id=district.id,
            is_active=True,
        ))
    session.commit()

    # ---------- Members at Allen Avenue District ----------
    sample_members = [
        ("Pastor Ruth Okoro", "female", "leader", None, "group_pastor", "+234-801-111-0001"),
        ("Elder Joseph Mensah", "male", "leader", None, "coordinator", "+234-801-111-0002"),
        ("Sis. Mary Choir", "female", "worker", "choir", None, "+234-801-111-0003"),
        ("Bro. Peter Usher", "male", "worker", "usher", None, "+234-801-111-0004"),
        ("Sis. Hannah Prayer", "female", "worker", "prayer", None, "+234-801-111-0005"),
        ("Bro. Daniel Evangelist", "male", "worker", "evangelist", None, "+234-801-111-0006"),
        ("Sis. Grace Drama", "female", "worker", "drama", None, "+234-801-111-0007"),
        ("Bro. Paul Media", "male", "worker", "media", None, "+234-801-111-0008"),
        ("Sis. Esther Women", "female", "leader", None, "women_leader", "+234-801-111-0009"),
        ("Bro. Timothy Children", "male", "leader", None, "children_leader", "+234-801-111-0010"),
        ("Sis. Ruth Campus", "female", "leader", None, "campus_leader", "+234-801-111-0011"),
        ("Bro. John Bible Study", "male", "leader", None, "bible_study_teacher", "+234-801-111-0012"),
        ("Mr. David Member", "male", "member", None, None, "+234-801-111-0013"),
        ("Mrs. Sarah Member", "female", "member", None, None, "+234-801-111-0014"),
        ("Mr. Isaac Youth", "male", "member", None, None, "+234-801-111-0015"),
        ("Miss Joy Youth", "female", "member", None, None, "+234-801-111-0016"),
        ("Master Caleb Child", "male", "member", None, None, "+234-801-111-0017"),
        ("Miss Faith Child", "female", "member", None, None, "+234-801-111-0018"),
        ("Bro. Emmanuel Protocol", "male", "worker", "protocol", None, "+234-801-111-0019"),
        ("Sis. Deborah Representative", "female", "leader", None, "representative", "+234-801-111-0020"),
    ]
    for name, gender, status, worker, leader, phone in sample_members:
        session.add(ChurchMember(
            church_id=district.id,
            full_name=name,
            gender=gender,
            phone=phone,
            status=MemberStatus(status),
            worker_type=worker,
            leader_type=leader,
            joined_date=date.today() - timedelta(days=180),
            is_active=True,
        ))
    session.commit()

    # ---------- Weekly stats (last 8 weeks) for district ----------
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    # Realistic-ish varying numbers
    base = [
        (42, 58, 12, 15, 18, 22, 85000, 120000, 25000, 90, 5, 2, 3, 4),
        (45, 60, 14, 16, 20, 24, 92000, 135000, 18000, 110, 7, 3, 2, 5),
        (40, 55, 11, 13, 17, 20, 78000, 110000, 30000, 75, 4, 1, 4, 3),
        (48, 62, 15, 18, 22, 25, 105000, 150000, 22000, 130, 8, 4, 3, 6),
        (44, 59, 13, 14, 19, 23, 88000, 128000, 20000, 95, 6, 2, 2, 4),
        (50, 65, 16, 19, 24, 28, 115000, 160000, 35000, 150, 10, 5, 5, 7),
        (46, 61, 14, 17, 21, 26, 98000, 142000, 28000, 120, 7, 3, 3, 5),
        (43, 57, 12, 15, 18, 21, 82000, 125000, 15000, 85, 5, 2, 2, 4),
    ]
    for i, row in enumerate(base):
        ws = this_monday - timedelta(weeks=7 - i)
        session.add(WeeklyStat(
            church_id=district.id,
            week_start=ws,
            adult_male=row[0], adult_female=row[1],
            children_boys=row[2], children_girls=row[3],
            youth_male=row[4], youth_female=row[5],
            offering=float(row[6]), tithe=float(row[7]), donation=float(row[8]),
            special_program_attendance=row[9],
            newcomers=row[10], converts=row[11],
            counseling=row[12], members_in_need=row[13],
            notes="Sample week data – Knowsoft Bible Church Allen Avenue",
        ))
    session.commit()
    print("✅ Sample data loaded: Knowsoft Bible Church (Global → Nigeria → Lagos → Ikeja → Allen Avenue)")
    print("   District login: allen@knowsoftbible.org / Church@12345")
    print("   Data officer:   data@allen.knowsoftbible.org / Data@12345")
