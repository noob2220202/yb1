import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401  (모델 등록을 위해 import)
from app.db import Base

TEST_DATABASE_URL = "postgresql://oddsapp:devlocalpass@localhost/oddsapp_test"

_engine = create_engine(TEST_DATABASE_URL)
_TestSessionLocal = sessionmaker(bind=_engine)


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.create_all(_engine)
    yield
    Base.metadata.drop_all(_engine)


@pytest.fixture()
def db_session():
    session = _TestSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
        session.close()
