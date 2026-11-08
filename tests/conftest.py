import pytest


@pytest.fixture
def db_url(tmp_path):
    return f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def engine(db_url):
    from superbot.core import db

    db.migrate(db_url)
    eng = db.use(db_url)
    yield eng
    eng.dispose()
