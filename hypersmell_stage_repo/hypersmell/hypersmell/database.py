from sqlmodel import Session, create_engine

from hypersmell.settings import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, echo=False)


def get_session():
    with Session(engine) as session:
        yield session
