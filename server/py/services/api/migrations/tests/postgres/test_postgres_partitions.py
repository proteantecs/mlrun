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
from datetime import datetime

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import mlrun.common.schemas

import framework.db.sqldb.db


@pytest.mark.usefixtures("pmr_postgres_container")
def test_create_partitions_via_interval(alembic_engine):
    Session = sessionmaker(bind=alembic_engine)
    session = Session()
    table = "dyn_table"
    # 1) create a RANGE-partitioned table
    session.execute(
        text(f"""
        CREATE TABLE {table} (
            id   INTEGER NOT NULL,
            data TEXT
        ) PARTITION BY RANGE (id);
    """)
    )

    # 2) generate two daily partitions starting Jan 1, 2025
    start = datetime(2025, 1, 1)
    parts = mlrun.common.schemas.PartitionInterval.DAY.get_partition_info(
        start,
        partition_number=2,
    )
    # parts looks like [("20250101","20250102"), ("20250102","20250103")]

    framework.db.sqldb.db.PostgreSQLDB.create_partitions(session, table, parts)

    # 3) verify attachments
    attached = {
        row[0]
        for row in session.execute(
            text("""
                  SELECT c.relname
                  FROM pg_inherits inh
                           JOIN pg_class AS c ON inh.inhrelid = c.oid
                  WHERE inh.inhparent = (:table)::regclass
            """),
            {"table": table},
        )
    }
    assert {name for name, _ in parts} <= attached
    session.close()


@pytest.mark.usefixtures("pmr_postgres_container")
def test_drop_partitions_via_interval(alembic_engine):
    Session = sessionmaker(bind=alembic_engine)
    session = Session()
    table = "dyn_table_drop"
    # setup: table + three weekly partitions
    session.execute(
        text(f"""
        CREATE TABLE {table} (
            id   INTEGER NOT NULL,
            data TEXT
        ) PARTITION BY RANGE (id);
    """)
    )
    start = datetime(2025, 1, 6)  # a Monday
    parts = mlrun.common.schemas.PartitionInterval.YEARWEEK.get_partition_info(
        start,
        partition_number=3,
    )
    # e.g. [("202501","202502"),("202502","202503"),("202503","202504")]

    framework.db.sqldb.db.PostgreSQLDB.create_partitions(session, table, parts)
    # drop those < the second one (cutoff = parts[1][0])
    cutoff = parts[1][0]
    framework.db.sqldb.db.PostgreSQLDB.drop_partitions(
        session,
        table,
        cutoff_partition_name=cutoff,
    )

    # only partitions ≥ cutoff should remain
    remaining = {
        row[0]
        for row in session.execute(
            text("""
                  SELECT c.relname
                  FROM pg_inherits AS inh
                           JOIN pg_class AS c ON inh.inhrelid = c.oid
                  WHERE inh.inhparent = (:table)::regclass
            """),
            {"table": table},
        )
    }
    assert cutoff in remaining
    assert parts[0][0] not in remaining
    session.close()
