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
import pytest
import sqlalchemy
from sqlalchemy.orm import sessionmaker

import mlrun


@pytest.fixture
def alembic_engine():
    return sqlalchemy.create_engine(mlrun.mlconf.httpdb.dsn)


@pytest.fixture(autouse=True)
def drop_all_tables(alembic_engine):
    """Start every test with an *empty* schema – no tables at all."""
    with alembic_engine.connect() as conn:
        conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        for (name,) in conn.exec_driver_sql("SHOW TABLES"):
            conn.exec_driver_sql(f"DROP TABLE `{name}`")
        conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
    yield


@pytest.fixture
def alembic_session(alembic_engine, drop_all_tables):
    session_maker = sessionmaker()
    session_maker.configure(bind=alembic_engine)
    session = session_maker()
    return session
