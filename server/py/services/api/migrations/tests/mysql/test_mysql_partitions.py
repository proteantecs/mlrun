# tests/db/test_mysql_partitions.py
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


@pytest.mark.usefixtures("pmr_mysql_container")
def test_create_partitions_mysql(alembic_engine):
    session_maker = sessionmaker(bind=alembic_engine)
    session = session_maker()
    table = "dyn_table"

    # 1) create a RANGE-partitioned table with a dummy initial partition
    session.execute(
        text(f"""
    CREATE TABLE `{table}` (
        id   INT NOT NULL,
        data TEXT
    ) PARTITION BY RANGE (id) (
        PARTITION p0 VALUES LESS THAN (1)
    );
    """)
    )

    # 2) generate two daily partitions starting Jan 1, 2025
    start = datetime(2025, 1, 1)
    parts = mlrun.common.schemas.PartitionInterval.DAY.get_partition_info(
        start, partition_number=2
    )
    # e.g. [("20250101","20250102"), ("20250102","20250103")]

    framework.db.sqldb.db.MySQLDB.create_partitions(session, table, parts)

    # 3) verify new partitions show up in INFORMATION_SCHEMA
    rows = session.execute(
        text("""
        SELECT PARTITION_NAME
        FROM information_schema.PARTITIONS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = :table
    """),
        {"table": table},
    ).fetchall()
    existing = {r[0] for r in rows if r[0] is not None}

    # both of our generated names must now exist
    assert {name for name, _ in parts} <= existing

    session.close()


@pytest.mark.usefixtures("pmr_mysql_container")
def test_drop_partitions_mysql(alembic_engine):
    session_maker = sessionmaker(bind=alembic_engine)
    session = session_maker()
    table = "dyn_table_drop"

    # 1) create table with dummy initial partition
    session.execute(
        text(f"""
    CREATE TABLE `{table}` (
        id   INT NOT NULL,
        data TEXT
    ) PARTITION BY RANGE (id) (
        PARTITION p0 VALUES LESS THAN (1)
    );
    """)
    )

    # 2) add three weekly partitions starting Jan 6, 2025 (a Monday)
    start = datetime(2025, 1, 6)
    parts = mlrun.common.schemas.PartitionInterval.YEARWEEK.get_partition_info(
        start, partition_number=3
    )
    # e.g. [("202501","202502"), ("202502","202503"), ("202503","202504")]

    framework.db.sqldb.db.MySQLDB.create_partitions(session, table, parts)

    # 3) drop any partition whose name < the second one
    cutoff = parts[1][0]
    framework.db.sqldb.db.MySQLDB.drop_partitions(
        session, table, cutoff_partition_name=cutoff
    )

    # 4) verify only partitions ≥ cutoff remain
    rows = session.execute(
        text("""
        SELECT PARTITION_NAME
        FROM information_schema.PARTITIONS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = :table
    """),
        {"table": table},
    ).fetchall()
    remaining = {r[0] for r in rows if r[0] is not None}

    assert cutoff in remaining
    assert parts[0][0] not in remaining

    session.close()
