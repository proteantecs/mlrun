import pytest
import os
os.environ["MLRUN_HTTPDB__HTTP__DSN"] = "mysql+pymysql://root:pass@localhost:3306/mlrun"
import sqlalchemy.orm
from pytest_mock_resources import create_mysql_fixture, MysqlConfig
MysqlConfig(password='password', ci_port=3306, host='host.docker.internal', port=3406, username='root', image='mysql:5.6', root_database='dev')
mysql = create_mysql_fixture()


@pytest.fixture(scope="session")
def pmr_mysql_config():
    return MysqlConfig(image="mysql:8.0", host="localhost", port=3306, username="root", password="pass", root_database="mlrun")

@pytest.fixture
def alembic_engine(mysql):
    return mysql.engine


@pytest.fixture
def alembic_session(alembic_engine):
    session_class = sqlalchemy.orm.sessionmaker(bind=alembic_engine)
    session = session_class()
    try:
        yield session
    finally:
        session.close()

