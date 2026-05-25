from sqlalchemy import create_engine, Column, Integer, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from core.config import settings

Base = declarative_base()


class Guest(Base):
    __tablename__ = "guests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    email_hash = Column(Text, nullable=False, unique=True)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Text, primary_key=True)
    guest_id = Column(Integer, ForeignKey("guests.id"), nullable=False)
    check_in = Column(Text, nullable=False)
    check_out = Column(Text, nullable=False)
    room_type = Column(Text, nullable=False, default="standard")
    status = Column(Text, nullable=False, default="confirmed")
    created_at = Column(Text, nullable=False, server_default="(datetime('now'))")


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(engine)
