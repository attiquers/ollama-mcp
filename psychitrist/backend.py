from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta, date

from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session
from sqlalchemy import text as sa_text
from sqlalchemy.exc import IntegrityError, NoResultFound

# Initialize FastAPI app
app = FastAPI(title="Psych Appointment API", version="1.0.0")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SQLAlchemy setup
DATABASE_URL = "sqlite:///./appointments.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Database Models
class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, unique=True, nullable=False, index=True)
    notes = Column(String)
    appointments = relationship("Appointment", back_populates="patient")

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    note = Column(String)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    patient = relationship("Patient", back_populates="appointments")

class AvailabilityException(Base):
    __tablename__ = "availability_exceptions"
    id = Column(Integer, primary_key=True, index=True)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    reason = Column(String)

# Pydantic Schemas
class PatientBase(BaseModel):
    name: str = Field(..., examples=["Alice"])
    phone: str = Field(..., examples=["+923001234567"])
    notes: Optional[str] = ""
    class Config:
        from_attributes = True

class PatientOut(PatientBase):
    id: int
    class Config:
        from_attributes = True

class AppointmentBase(BaseModel):
    phone: str = Field(..., examples=["+923001234567"])
    start_time: str = Field(..., description="ISO datetime e.g. 2025-08-20T10:00:00")
    note: Optional[str] = ""
    class Config:
        from_attributes = True

class AppointmentOut(BaseModel):
    id: int
    patient_id: int
    start_time: datetime
    end_time: datetime
    note: Optional[str]
    created_at: datetime
    class Config:
        from_attributes = True

class UpdateAppointment(BaseModel):
    new_start_time: str = Field(..., description="ISO datetime on 30-min grid")
    class Config:
        from_attributes = True

class AvailabilityBlockBase(BaseModel):
    start_time: str = Field(..., description="ISO datetime")
    end_time: str = Field(..., description="ISO datetime")
    reason: Optional[str] = ""
    class Config:
        from_attributes = True

class AvailabilityBlockOut(BaseModel):
    id: int
    start_time: datetime
    end_time: datetime
    reason: Optional[str]
    class Config:
        from_attributes = True

# Helper functions
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _has_overlap(s1, e1, s2, e2):
    return s1 < e2 and s2 < e1

def get_office_hours():
    # Hardcoded for simplicity, could be from DB
    return datetime.strptime("09:00", "%H:%M").time(), datetime.strptime("17:00", "%H:%M").time()

def next_date_for_dow(dow: str, ref_date: Optional[str] = None) -> date:
    dow_map = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    key = dow.strip().lower()[:3]
    if key not in dow_map:
        raise ValueError("Invalid day of week")
    
    today = date.fromisoformat(ref_date) if ref_date else datetime.now().date()
    target_weekday = dow_map[key]
    delta = (target_weekday - today.weekday()) % 7
    return today if delta == 0 else today + timedelta(days=delta)

# Startup event
@app.on_event("startup")
def startup_db():
    Base.metadata.create_all(bind=engine)

# Endpoints
@app.get("/health")
def health():
    start, end = get_office_hours()
    return {"ok": True, "office_hours": {"start": start.strftime("%H:%M"), "end": end.strftime("%H:%M")}}

@app.post("/patients/upsert", response_model=PatientOut)
def upsert_patient(p: PatientBase, db: Session = Depends(get_db)):
    try:
        patient = db.query(Patient).filter(Patient.phone == p.phone).one()
        patient.name = p.name
        patient.notes = p.notes
    except NoResultFound:
        patient = Patient(name=p.name, phone=p.phone, notes=p.notes)
        db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient

@app.get("/patients/{phone}", response_model=PatientOut)
def get_patient(phone: str, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.phone == phone).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

@app.get("/patients/{phone}/appointments", response_model=List[AppointmentOut])
def get_patient_appointments(phone: str, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.phone == phone).first()
    if not patient:
        return []
    return db.query(Appointment).filter(Appointment.patient_id == patient.id).order_by(Appointment.start_time).all()

@app.post("/appointments/book", response_model=AppointmentOut)
def book_appointment(b: AppointmentBase, db: Session = Depends(get_db)):
    start_dt = datetime.fromisoformat(b.start_time)
    if start_dt.minute not in (0, 30):
        raise HTTPException(status_code=400, detail="Start time must align on 30-minute boundaries.")
    end_dt = start_dt + timedelta(minutes=30)
    
    office_start_t, office_end_t = get_office_hours()
    office_start_dt = datetime.combine(start_dt.date(), office_start_t)
    office_end_dt = datetime.combine(start_dt.date(), office_end_t)
    if not (office_start_dt <= start_dt and end_dt <= office_end_dt):
        raise HTTPException(status_code=400, detail="Time is outside office hours.")

    if db.query(AvailabilityException).filter(
        AvailabilityException.start_time < end_dt,
        AvailabilityException.end_time > start_dt
    ).first():
        raise HTTPException(status_code=400, detail="Time falls within a blocked period.")

    if db.query(Appointment).filter(
        Appointment.start_time < end_dt,
        Appointment.end_time > start_dt
    ).first():
        raise HTTPException(status_code=400, detail="Slot already booked.")

    patient = db.query(Patient).filter(Patient.phone == b.phone).first()
    if not patient:
        patient = Patient(name=b.phone, phone=b.phone, notes="")
        db.add(patient)
        db.commit()
        db.refresh(patient)
    
    appointment = Appointment(
        patient_id=patient.id,
        start_time=start_dt,
        end_time=end_dt,
        note=b.note
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment

@app.put("/appointments/{appt_id}", response_model=AppointmentOut)
def update_appointment(appt_id: int, payload: UpdateAppointment, db: Session = Depends(get_db)):
    new_start_dt = datetime.fromisoformat(payload.new_start_time)
    if new_start_dt.minute not in (0, 30):
        raise HTTPException(status_code=400, detail="Start time must align on 30-minute boundaries.")
    new_end_dt = new_start_dt + timedelta(minutes=30)

    office_start_t, office_end_t = get_office_hours()
    office_start_dt = datetime.combine(new_start_dt.date(), office_start_t)
    office_end_dt = datetime.combine(new_start_dt.date(), office_end_t)
    if not (office_start_dt <= new_start_dt and new_end_dt <= office_end_dt):
        raise HTTPException(status_code=400, detail="Time is outside office hours.")

    appointment = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    if db.query(AvailabilityException).filter(
        AvailabilityException.start_time < new_end_dt,
        AvailabilityException.end_time > new_start_dt
    ).first():
        raise HTTPException(status_code=400, detail="Time falls within a blocked period.")

    if db.query(Appointment).filter(
        Appointment.start_time < new_end_dt,
        Appointment.end_time > new_start_dt,
        Appointment.id != appt_id
    ).first():
        raise HTTPException(status_code=400, detail="Slot already booked.")
    
    appointment.start_time = new_start_dt
    appointment.end_time = new_end_dt
    db.commit()
    db.refresh(appointment)
    return appointment

@app.delete("/appointments/{appt_id}")
def delete_appointment(appt_id: int, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).filter(Appointment.id == appt_id).first()
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    db.delete(appointment)
    db.commit()
    return {"deleted": True}

@app.get("/availability")
def get_available_slots(date: Optional[str] = None, day_of_week: Optional[str] = None, ref_date: Optional[str] = None, db: Session = Depends(get_db)):
    if not date and not day_of_week:
        raise HTTPException(status_code=400, detail="Provide either date or day_of_week")
    
    if day_of_week:
        try:
            target_date = next_date_for_dow(day_of_week, ref_date)
            date = target_date.isoformat()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        try:
            target_date = datetime.fromisoformat(date).date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    
    start_office_t, end_office_t = get_office_hours()
    current = datetime.combine(target_date, start_office_t)
    base_end = datetime.combine(target_date, end_office_t)
    
    all_slots = []
    while current < base_end:
        all_slots.append((current, current + timedelta(minutes=30)))
        current += timedelta(minutes=30)
    
    booked_appointments = db.query(Appointment).filter(
        Appointment.start_time >= datetime.combine(target_date, start_office_t),
        Appointment.end_time <= datetime.combine(target_date, end_office_t)
    ).all()
    
    blocked_exceptions = db.query(AvailabilityException).filter(
        AvailabilityException.start_time >= datetime.combine(target_date, start_office_t),
        AvailabilityException.end_time <= datetime.combine(target_date, end_office_t)
    ).all()
    
    free_slots = []
    for s_start, s_end in all_slots:
        is_booked = any(_has_overlap(s_start, s_end, b.start_time, b.end_time) for b in booked_appointments)
        is_blocked = any(_has_overlap(s_start, s_end, b.start_time, b.end_time) for b in blocked_exceptions)
        
        if not is_booked and not is_blocked:
            free_slots.append({
                "start": s_start.isoformat(),
                "end": s_end.isoformat(),
                "label": f"{s_start.strftime('%I:%M %p')} - {s_end.strftime('%I:%M %p')}"
            })
            
    return {"date": date, "slots": free_slots}

@app.post("/availability/block", response_model=AvailabilityBlockOut)
def block_availability(b: AvailabilityBlockBase, db: Session = Depends(get_db)):
    start_dt = datetime.fromisoformat(b.start_time)
    end_dt = datetime.fromisoformat(b.end_time)
    
    if start_dt >= end_dt:
        raise HTTPException(status_code=400, detail="start_time must be before end_time")
    
    if start_dt.minute not in (0, 30) or end_dt.minute not in (0, 30):
        raise HTTPException(status_code=400, detail="Blocks must align to 30-minute boundaries.")

    # FIX: Add a check for existing appointments before creating a block
    if db.query(Appointment).filter(
        Appointment.start_time < end_dt,
        Appointment.end_time > start_dt
    ).first():
        raise HTTPException(status_code=400, detail="Cannot block this time; it is already booked by an existing appointment.")

    # Check for existing blocks
    if db.query(AvailabilityException).filter(
        AvailabilityException.start_time < end_dt,
        AvailabilityException.end_time > start_dt
    ).first():
        raise HTTPException(status_code=400, detail="Time falls within a pre-existing blocked period.")

    block = AvailabilityException(
        start_time=start_dt,
        end_time=end_dt,
        reason=b.reason
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return block

@app.get("/availability/blocks", response_model=List[AvailabilityBlockOut])
def get_blocks(date: str, db: Session = Depends(get_db)):
    try:
        target_date = datetime.fromisoformat(date).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
        
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    
    return db.query(AvailabilityException).filter(
        AvailabilityException.start_time >= start_of_day,
        AvailabilityException.end_time <= end_of_day
    ).order_by(AvailabilityException.start_time).all()

@app.delete("/availability/blocks/{block_id}")
def delete_block(block_id: int, db: Session = Depends(get_db)):
    block = db.query(AvailabilityException).filter(AvailabilityException.id == block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found.")
    db.delete(block)
    db.commit()
    return {"deleted": True}