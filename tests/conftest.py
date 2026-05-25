import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

from db.models import Base


@pytest.fixture
def in_memory_db():
    """
    Creates a fresh SQLite in-memory database with all tables.
    Patches the db/operations.py engine to use this in-memory DB.
    Yields the session factory. Tears down after each test.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with patch("db.operations.SessionLocal", TestSession):
        yield TestSession

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def sample_booking_data():
    return {
        "guest_name": "Test Guest",
        "guest_email": "test@example.com",
        "check_in": "2099-01-10",
        "check_out": "2099-01-15",
    }
