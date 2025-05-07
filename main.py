from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from passlib.context import CryptContext
from fastapi.middleware.cors import CORSMiddleware

DATABASE_URL = "sqlite:///./carbon_tracker.db"

connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password = Column(String(200), nullable=False)
    transports = relationship("Transport", back_populates="user", cascade="all, delete-orphan")

class Transport(Base):
    __tablename__ = "transport"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    transport_type = Column(String(50), nullable=False)
    distance = Column(Integer, nullable=False)
    carbon_emission = Column(Float, nullable=False)
    user = relationship("User", back_populates="transports")

Base.metadata.create_all(bind=engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TransportData(BaseModel):
    user_id: int
    transport_type: str
    distance: int
    carbon_emission: float

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/signup")
def signup(user: SignupRequest, db: Session = Depends(get_db)):
    if not user.name.strip() or not user.email.strip() or not user.password.strip():
        raise HTTPException(status_code=400, detail="All fields are required")
    
    existing_user = db.query(User).filter(User.email == user.email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = pwd_context.hash(user.password)
    db_user = User(name=user.name, email=user.email, password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return {"message": "User created successfully", "user_id": db_user.id}

@app.post("/login")
def login(user: LoginRequest, db: Session = Depends(get_db)):
    if not user.email.strip() or not user.password.strip():
        raise HTTPException(status_code=400, detail="Email and password are required")
    
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not pwd_context.verify(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return {"message": "Login successful", "user_id": db_user.id}

@app.post("/transport")
def save_transport(data: TransportData, db: Session = Depends(get_db)):
    db_transport = Transport(
        user_id=data.user_id,
        transport_type=data.transport_type,
        distance=data.distance,
        carbon_emission=data.carbon_emission
    )
    db.add(db_transport)
    db.commit()
    return {"message": "Transport data saved successfully"}

# New API: Fetch total carbon emissions per user
@app.get("/transport/emissions/{user_id}")
def get_transport_emissions(user_id: int, db: Session = Depends(get_db)):
    emissions = db.query(
        Transport.transport_type,
        func.sum(Transport.carbon_emission).label("total_emission")
    ).filter(Transport.user_id == user_id).group_by(Transport.transport_type).all()
    
    if not emissions:
        return {"message": "No transport data found", "total": 0, "breakdown": {}}
    
    total_emission = sum(entry.total_emission for entry in emissions)
    breakdown = {entry.transport_type: entry.total_emission for entry in emissions}
    
    return {"total": total_emission, "breakdown": breakdown}
