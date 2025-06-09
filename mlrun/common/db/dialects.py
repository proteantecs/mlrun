import mlrun.common.types


class Dialects(mlrun.common.types.StrEnum):
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"

    @classmethod
    def all(cls) -> list[str]:
        """Return all dialects as a list of strings."""
        return [dialect.value for dialect in cls]
