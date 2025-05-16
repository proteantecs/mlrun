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
# server/py/services/api/migrations/tests/conftest.py
import pytest
import sqlalchemy
from sqlalchemy.orm import sessionmaker

import mlrun


@pytest.fixture
def alembic_engine():
    return sqlalchemy.create_engine(mlrun.mlconf.httpdb.dsn)


@pytest.fixture
def alembic_session(alembic_engine):
    session_class = sessionmaker(bind=alembic_engine)
    session = session_class()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _clean_schema_before_every_migration(monkeypatch, alembic_runner, alembic_engine):
    """
    Patch alembic_runner.migrate_up_to so every call first drops all tables
    in the current schema.  Works with the tests we import from
    pytest_alembic.tests and with MySQL’s non-transactional DDL.
    """
    real_migrate = alembic_runner.migrate_up_to

    def _drop_then_migrate(revision="heads", *args, **kwargs):
        with alembic_engine.begin() as conn:
            meta = sqlalchemy.MetaData()
            meta.reflect(bind=conn)

            if meta.tables:
                if conn.dialect.name == "mysql":
                    conn.execute(sqlalchemy.text("SET FOREIGN_KEY_CHECKS=0"))

                meta.drop_all(bind=conn)

                if conn.dialect.name == "mysql":
                    conn.execute(sqlalchemy.text("SET FOREIGN_KEY_CHECKS=1"))

        # now do the real migration
        return real_migrate(revision, *args, **kwargs)

    monkeypatch.setattr(alembic_runner, "migrate_up_to", _drop_then_migrate)
