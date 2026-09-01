"""Sample: Knowsoft Church — full hierarchy + members + weekly stats at all visibility levels."""
from datetime import date, timedelta
from sqlmodel import Session, select
from app.models import (
    User, UserRole, ChurchUnit, ChurchLevel, ChurchMember, WeeklyStat, SpecialProgram
)
from app.auth import get_password_hash

FIRST = ["David", "Grace", "Samuel", "Ruth", "Michael", "Esther", "Daniel", "Hannah",
         "Joseph", "Mary", "Peter", "Sarah", "James", "Joy", "Emmanuel", "Faith",
         "Caleb", "Blessing", "Isaac", "Deborah", "Timothy", "Peace", "Paul", "Hope"]
LAST = ["Okonkwo", "Adeyemi", "Bello", "Okoro", "Mensah", "Nwachukwu", "Ibrahim",
        "Okafor", "Eze", "Chukwu", "Abdullahi", "Ogunleye", "Adebayo", "Nwosu"]

def seed_knowsoft_bible_church(session: Session) -> None:
    existing = session.exec(
        select(ChurchUnit).where(ChurchUnit.code == "KC-GLOBAL")
    ).first()
    if existing:
        print("ℹ️ Knowsoft Church sample already exists")
        return

    def unit(**kw):
        c = ChurchUnit(**kw)
        session.add(c)
        session.commit()
        session.refresh(c)
        return c

    global_c = unit(
        code="KC-GLOBAL", name="Knowsoft Church", level=ChurchLevel.global_church,
        global_code="KC-GLOBAL",
        doctrine="Scripture-based faith, salvation in Christ, discipleship and mission.",
        activity_days="Sunday, Wednesday, Friday",
        owner_name="Apostle David Knowsoft", resident_pastor="Apostle David Knowsoft",
        address="Knowsoft Global HQ, Abuja", phone="+234-800-100-0001",
        email="global@knowsoftchurch.org", country_name="Nigeria",
        approval_status="approved", is_active=True,
    )
    country = unit(
        code="KC-NG", name="Knowsoft Church – Nigeria", level=ChurchLevel.country,
        parent_id=global_c.id, global_code="KC-GLOBAL", country_code="KC-NG",
        country_name="Nigeria", resident_pastor="Rev. Samuel Okonkwo",
        email="nigeria@knowsoftchurch.org", approval_status="approved", is_active=True,
    )
    state = unit(
        code="KC-NG-LAG", name="Knowsoft Church – Lagos State", level=ChurchLevel.state,
        parent_id=country.id, global_code="KC-GLOBAL", country_code="KC-NG",
        state_code="KC-NG-LAG", country_name="Nigeria", state_name="Lagos",
        resident_pastor="Pastor Grace Adeyemi", email="lagos@knowsoftchurch.org",
        approval_status="approved", is_active=True,
    )
    group = unit(
        code="KC-NG-LAG-IKE", name="Knowsoft Church – Ikeja Group", level=ChurchLevel.group,
        parent_id=state.id, global_code="KC-GLOBAL", country_code="KC-NG",
        state_code="KC-NG-LAG", group_code="KC-NG-LAG-IKE",
        country_name="Nigeria", state_name="Lagos",
        resident_pastor="Pastor Michael Bello", email="ikeja@knowsoftchurch.org",
        approval_status="approved", is_active=True,
    )
    district = unit(
        code="KC-NG-LAG-IKE-ALLEN", name="Knowsoft Church – Allen Avenue District",
        level=ChurchLevel.district, parent_id=group.id,
        global_code="KC-GLOBAL", country_code="KC-NG", state_code="KC-NG-LAG",
        group_code="KC-NG-LAG-IKE", district_code="KC-NG-LAG-IKE-ALLEN",
        country_name="Nigeria", state_name="Lagos",
        doctrine=global_c.doctrine, activity_days="Sunday, Wednesday, Friday",
        owner_name="Apostle David Knowsoft", resident_pastor="Pastor Ruth Okoro",
        address="12 Allen Avenue, Ikeja, Lagos", phone="+234-801-234-5678",
        email="allen@knowsoftchurch.org", approval_status="approved", is_active=True,
    )

    def admin(email, name, cid, role=UserRole.church_admin, pwd="Church@12345", stats=False):
        if session.exec(select(User).where(User.email == email)).first():
            return
        session.add(User(
            email=email, hashed_password=get_password_hash(pwd), full_name=name,
            role=role, church_id=cid, is_active=True, can_enter_stats=stats
        ))

    admin("global@knowsoftchurch.org", "Apostle David Knowsoft", global_c.id)
    admin("nigeria@knowsoftchurch.org", "Rev. Samuel Okonkwo", country.id)
    admin("lagos@knowsoftchurch.org", "Pastor Grace Adeyemi", state.id)
    admin("ikeja@knowsoftchurch.org", "Pastor Michael Bello", group.id)
    admin("allen@knowsoftchurch.org", "Pastor Ruth Okoro", district.id)
    admin("data@allen.knowsoftchurch.org", "Bro. James Data Officer", district.id,
          UserRole.data_officer, "Data@12345", stats=True)
    session.commit()

    # ~80 sample members at district (approved) for charts/lists
    import itertools
    statuses = [
        ("member", None, None), ("member", None, None), ("member", None, None),
        ("worker", "usher", None), ("worker", "choir", None), ("worker", "prayer", None),
        ("worker", "evangelist", None), ("worker", "media", None),
        ("leader", None, "coordinator"), ("leader", None, "women_leader"),
        ("leader", None, "children_leader"), ("leader", None, "bible_study_teacher"),
        ("pastor", None, "group_pastor"),
    ]
    sexes = ["brother", "sister"]
    ages = ["child", "youth", "campus", "adult"]
    conf = ["saved", "saved", "saved", "restored", "backslidden"]
    n = 0
    for i, (fn, ln) in enumerate(itertools.product(FIRST, LAST)):
        if n >= 80:
            break
        st, wt, lt = statuses[i % len(statuses)]
        sex = sexes[i % 2]
        member = ChurchMember(
            church_id=district.id,
            global_church_id=global_c.id,
            country_church_id=country.id,
            state_church_id=state.id,
            group_church_id=group.id,
            full_name=f"{fn} {ln}",
            sex=sex,
            age_category=ages[i % 4],
            confession=conf[i % 5],
            member_since=date.today() - timedelta(days=30 * (i % 24)),
            whatsapp=f"+23480{1000000 + i}",
            phone=f"+23480{1000000 + i}",
            email=f"member{i}@knowsoftchurch.sample",
            address=f"{10 + i} Sample Street, Ikeja, Lagos",
            status=st, worker_type=wt, leader_type=lt,
            approval_status="approved", is_active=True,
            prayer_request="Family and ministry" if i % 5 == 0 else None,
        )
        session.add(member)
        n += 1
    session.commit()

    # Weekly stats 12 weeks
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    for w in range(12):
        ws = monday - timedelta(weeks=11 - w)
        base = 40 + (w % 5) * 3
        session.add(WeeklyStat(
            church_id=district.id, week_start=ws,
            adult_male=base, adult_female=base + 12,
            children_boys=10 + w % 4, children_girls=12 + w % 3,
            youth_male=15 + w % 5, youth_female=18 + w % 4,
            offering=80000 + w * 3000, tithe=110000 + w * 4000, donation=15000 + w * 1000,
            special_program_attendance=70 + w * 5, newcomers=3 + w % 4, converts=1 + w % 3,
            counseling=2 + w % 3, members_in_need=3 + w % 4,
            notes="Knowsoft Church Allen – sample week",
        ))
    session.commit()

    # Sample special program at district
    prog = SpecialProgram(
        church_id=district.id,
        title="Victory Sunday Thanksgiving",
        description="Special thanksgiving and healing service. All members of Ikeja Group invited.",
        program_date=date.today() + timedelta(days=7),
        location="Allen Avenue Auditorium",
        broadcast_to="group",
        is_active=True,
    )
    session.add(prog)
    session.commit()

    print("✅ Knowsoft Church sample ready (Global→NG→Lagos→Ikeja→Allen)")
    print("   District admin: allen@knowsoftchurch.org / Church@12345")
    print("   Data officer:   data@allen.knowsoftchurch.org / Data@12345")
    print(f"   Members seeded: {n}")
