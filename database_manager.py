from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from geoalchemy2 import Geography
from datetime import datetime
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Source(Base):
    """A data source — a library or recreation department website."""
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    type = Column(String)               # "library" | "recreation"
    website = Column(String)
    platform = Column(String)           # "LibCal" | "RecDesk" | "WhoFi" | "WordPress" | etc.
    events_url = Column(String)
    api_endpoint = Column(String)
    cal_id = Column(String)             # LibCal calendar ID
    adapter_name = Column(String)       # "libcal" | "recdesk" | "whofi" | "wordpress" | "drupal"
    is_active = Column(Boolean, default=True)
    notes = Column(Text)
    last_harvested = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    venues = relationship("Venue", back_populates="source")
    events = relationship("Event", back_populates="source")


class Venue(Base):
    """A physical location where events take place."""
    __tablename__ = "venues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    address = Column(String)
    city = Column(String)
    state = Column(String, default="RI")
    zip_code = Column(String)
    location = Column(Geography(geometry_type="POINT", srid=4326))
    source_id = Column(Integer, ForeignKey("sources.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("Source", back_populates="venues")
    events = relationship("Event", back_populates="venue")


class Event(Base):
    """A single event occurrence."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    event_date = Column(String)
    event_time = Column(String)
    description = Column(Text)
    tags = Column(String)
    source_url = Column(String)
    venue_id = Column(Integer, ForeignKey("venues.id"))
    source_id = Column(Integer, ForeignKey("sources.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    venue = relationship("Venue", back_populates="events")
    source = relationship("Source", back_populates="events")


# Backwards-compatible alias so app.py import doesn't break during migration
GoldenEvent = Event


def init_db():
    """Create tables if they don't exist. Safe to call repeatedly."""
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
