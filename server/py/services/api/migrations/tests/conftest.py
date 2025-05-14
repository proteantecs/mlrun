import pytest
import sqlalchemy

import mlrun
@pytest.fixture(autouse=True)
def truncate_all_tables():
    engine = sqlalchemy.create_engine(mlrun.mlconf.httpdb.dsn)
    with engine.connect() as conn:
        conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        for name, in conn.exec_driver_sql("SHOW TABLES"):
            conn.exec_driver_sql(f"TRUNCATE TABLE `{name}`")
        conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
    yield
