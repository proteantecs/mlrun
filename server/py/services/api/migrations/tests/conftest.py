# Copyright 2025 Iguazio
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import os

import pytest

os.environ["MLRUN_HTTPDB__HTTP__DSN"] = "mysql+pymysql://root:pass@localhost:3306/mlrun"
import sqlalchemy.orm
from pytest_mock_resources import MysqlConfig, create_mysql_fixture

MysqlConfig(
    password="password",
    ci_port=3306,
    host="host.docker.internal",
    port=3406,
    username="root",
    image="mysql:5.6",
    root_database="dev",
)
mysql = create_mysql_fixture()


@pytest.fixture(scope="session")
def pmr_mysql_config():
    return MysqlConfig(
        image="mysql:8.0",
        host="localhost",
        port=3306,
        username="root",
        password="pass",
        root_database="mlrun",
    )


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
