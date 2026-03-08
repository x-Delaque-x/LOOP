from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from geoalchemy2 import Geography
from datetime import datetime
from config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Municipality(Base):
    """A Rhode Island municipality — the organizing unit for source discovery."""
    __tablename__ = "municipalities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    county = Column(String)
    population = Column(Integer)
    has_library = Column(Boolean, default=True)
    has_recreation = Column(Boolean, default=True)
    library_status = Column(String, default="not_scouted")    # not_scouted | scouted | active | no_events | unreachable
    recreation_status = Column(String, default="not_scouted")

    sources = relationship("Source", back_populates="municipality")


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
    municipality_id = Column(Integer, ForeignKey("municipalities.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    municipality = relationship("Municipality", back_populates="sources")
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


class URLSubmission(Base):
    """User-submitted source URLs for admin review."""
    __tablename__ = "url_submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    municipality_id = Column(Integer, ForeignKey("municipalities.id"))
    url = Column(String, nullable=False)
    source_type = Column(String)        # "library" | "recreation"
    submitter_note = Column(Text)
    status = Column(String, default="pending")  # pending | approved | rejected
    created_at = Column(DateTime, default=datetime.utcnow)

    municipality = relationship("Municipality")


class Feedback(Base):
    """User feedback submitted through the dashboard."""
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    feedback = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Backwards-compatible alias so app.py import doesn't break during migration
GoldenEvent = Event


def init_db():
    """Create tables if they don't exist. Safe to call repeatedly."""
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
