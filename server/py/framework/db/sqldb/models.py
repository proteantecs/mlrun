# Copyright 2023 Iguazio
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

import json
import os
import pickle
import uuid
import warnings
from datetime import datetime, timezone
from typing import Optional

import orjson
from sqlalchemy import (
    BOOLEAN,
    JSON,
    Column,
    Connection,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Table,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, Mapper, declared_attr, mapped_column, relationship

import mlrun.common.schemas
import mlrun.db.sql_types
import mlrun.utils.db

Base = declarative_base()
NULL = None  # Avoid flake8 issuing warnings when comparing in filter

_tagged = None
_labeled = None
_with_notifications = None
_classes = None


def post_table_definitions(base_cls):
    global _tagged
    global _labeled
    global _with_notifications
    global _classes
    _tagged = [cls for cls in base_cls.__subclasses__() if hasattr(cls, "Tag")]
    _labeled = [cls for cls in base_cls.__subclasses__() if hasattr(cls, "Label")]
    _with_notifications = [
        cls for cls in base_cls.__subclasses__() if hasattr(cls, "Notification")
    ]
    _classes = [cls for cls in base_cls.__subclasses__()]


def make_label(parent_cls):
    table = parent_cls.__tablename__

    class Label(Base, mlrun.utils.db.BaseModel):
        __tablename__ = f"{table}_labels"
        __table_args__ = (
            UniqueConstraint("name", "parent", name=f"_{table}_labels_uc"),
            Index(f"idx_{table}_labels_name_value", "name", "value"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        value: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )

        parent: Mapped[Optional[int]] = mapped_column(
            Integer,
            ForeignKey(
                f"{table}.id",
                name=f"_{table}_labels_parent_fk",
                ondelete="CASCADE",
            ),
            nullable=True,
        )

        parent_rel = relationship(
            parent_cls,
            back_populates="labels",
            passive_deletes=True,
        )

        def get_identifier_string(self) -> str:
            return f"{self.parent}/{self.name}/{self.value}"

    return Label


def make_tag(parent_cls):
    table = parent_cls.__tablename__

    class Tag(Base, mlrun.utils.db.BaseModel):
        __tablename__ = f"{table}_tags"
        __table_args__ = (
            UniqueConstraint("project", "name", "obj_id", name=f"_{table}_tags_uc"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        name: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )

        obj_id: Mapped[Optional[int]] = mapped_column(
            Integer,
            ForeignKey(
                f"{table}.id",
                name=f"_{table}_tags_obj_id_fk",
                ondelete="CASCADE",
            ),
            nullable=True,
        )

        parent_rel = relationship(
            parent_cls,
            back_populates="tags",
            passive_deletes=True,
        )

    return Tag


class TagMixin:
    __tablename__ = None

    @declared_attr
    def Tag(cls):  # noqa: N805 N802
        return make_tag(cls)

    @declared_attr
    def tags(cls):  # noqa: N805
        return relationship(
            cls.Tag,
            back_populates="parent_rel",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )


def make_tag_v2(parent_cls):
    table = parent_cls.__tablename__

    class TagV2(Base, mlrun.utils.db.BaseModel):
        __tablename__ = f"{table}_tags"
        __table_args__ = (
            UniqueConstraint("project", "name", "obj_name", name=f"_{table}_tags_uc"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        name: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        obj_id: Mapped[Optional[int]] = mapped_column(
            Integer,
            ForeignKey(f"{table}.id", ondelete="CASCADE"),
            nullable=True,
        )
        obj_name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}"

        parent_rel = relationship(
            parent_cls,
            back_populates="tags",
            passive_deletes=True,
        )

    return TagV2


class TagV2Mixin:
    __tablename__ = None

    @declared_attr
    def Tag(cls):  # noqa: N805 N802
        return make_tag_v2(cls)

    @declared_attr
    def tags(cls):  # noqa: N805
        return relationship(
            cls.Tag,
            back_populates="parent_rel",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )


def make_artifact_tag(cls):
    """
    For artifacts, we cannot use tag_v2 because different artifacts with the same key can have the same tag.
    therefore we need to use the obj_id as the unique constraint.
    """
    table = cls.__tablename__

    class ArtifactTag(Base, mlrun.utils.db.BaseModel):
        __tablename__ = f"{table}_tags"
        __table_args__ = (
            UniqueConstraint("project", "name", "obj_id", name=f"_{table}_tags_uc"),
            Index(
                f"idx_{table}_tags_project_name_obj_name",
                "project",
                "name",
                "obj_name",
            ),
            ForeignKeyConstraint(
                ["obj_id"],
                [f"{table}.id"],
                name="artifacts_v2_tags_ibfk_1",
                ondelete="CASCADE",
            ),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        project: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        obj_id: Mapped[Optional[int]] = mapped_column(
            Integer,
            nullable=True,
        )
        obj_name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )

        parent_rel = relationship(
            cls,
            back_populates="tags",
            passive_deletes=True,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}"

    return ArtifactTag


class ArtifactTagMixin:
    __tablename__ = None

    @declared_attr
    def Tag(cls):  # noqa: N805 N802
        return make_artifact_tag(cls)

    @declared_attr
    def tags(cls):  # noqa: N805
        return relationship(
            cls.Tag,
            back_populates="parent_rel",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )


def make_notification(cls):
    table = cls.__tablename__

    class Notification(Base, mlrun.utils.db.BaseModel):
        __tablename__ = f"{table}_notifications"
        __table_args__ = (
            UniqueConstraint("name", "parent_id", name=f"_{table}_notifications_uc"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        kind: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        message: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        severity: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        when: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        condition: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        secret_params: Mapped[dict] = mapped_column(
            "secret_params",
            JSON,
        )
        params: Mapped[dict] = mapped_column(
            "params",
            JSON,
        )
        parent_id: Mapped[int] = mapped_column(
            Integer,
            ForeignKey(f"{table}.id", ondelete="CASCADE"),
            nullable=False,
        )
        parent_rel = relationship(cls, back_populates="notifications")

        # TODO: Separate table for notification state.
        #   Currently, we are only supporting one notification being sent per DB row (either on completion or on error).
        #   In the future, we might want to support multiple notifications per DB row, and we might want to support on
        #   start, therefore we need to separate the state from the notification itself (e.g. this table can be  table
        #   with notification_id, state, when, last_sent, etc.). This will require some refactoring in the code.
        sent_time: Mapped[Optional[datetime]] = mapped_column(
            mlrun.db.sql_types.DateTime,
            nullable=True,
        )
        status: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        reason: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )

    return Notification


class NotificationMixin:
    __tablename__ = None

    @declared_attr
    def Notification(cls):  # noqa: N805 N802
        return make_notification(cls)

    @declared_attr
    def notifications(cls):  # noqa: N805
        return relationship(
            cls.Notification,
            back_populates="parent_rel",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )


class LabelMixin:
    __tablename__ = None

    @declared_attr
    def Label(cls):  # noqa: N805 N802
        return make_label(cls)

    @declared_attr
    def labels(cls):  # noqa: N805
        return relationship(
            cls.Label,
            back_populates="parent_rel",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )


# quell SQLAlchemy warnings on duplicate class name (Label)
with warnings.catch_warnings():
    warnings.simplefilter("ignore")

    # deprecated, use ArtifactV2 instead
    # TODO: Remove once data migration v5 is obsolete and add schema migration to remove this table
    class Artifact(Base, LabelMixin, TagMixin, mlrun.utils.db.HasStruct):
        __tablename__ = "artifacts"
        __table_args__ = (
            UniqueConstraint("uid", "project", "key", name="_artifacts_uc"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        key: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        uid: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        updated: Mapped[Optional[datetime]] = mapped_column(
            mlrun.db.sql_types.DateTime,
            nullable=True,
        )
        # TODO: change to JSON, see mlrun/common/schemas/function.py::FunctionState for reasoning
        body: Mapped[bytes] = mapped_column(
            mlrun.db.sql_types.Blob,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.key}/{self.uid}"

    class ArtifactV2(Base, LabelMixin, ArtifactTagMixin, mlrun.utils.db.BaseModel):
        __tablename__ = "artifacts_v2"
        __table_args__ = (
            UniqueConstraint("uid", "project", "key", name="_artifacts_v2_uc"),
            # Used when enriching workflow status with run artifacts. See https://iguazio.atlassian.net/browse/ML-6770
            Index(
                "idx_artifacts_producer_id_best_iteration_and_project",
                "project",
                "producer_id",
                "best_iteration",
            ),
            # Used to speed up querying artifact tags which is frequently done by UI with project and category.
            # See https://iguazio.atlassian.net/browse/ML-7266
            Index(
                "idx_project_kind",
                "project",
                "kind",
            ),
            # Used for calculating the project counters more efficiently.
            # See https://iguazio.atlassian.net/browse/ML-8556
            Index("idx_project_kind_key", "project", "kind", "key"),
            # Used explicitly in list_artifacts, as most of the queries request best_iteration, and all always sort by
            # updated. See https://iguazio.atlassian.net/browse/ML-9189
            Index("idx_project_bi_updated", "project", "best_iteration", "updated"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        key: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            index=True,
        )
        project: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        kind: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            index=True,
            nullable=True,
        )
        producer_id: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        producer_uri: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        iteration: Mapped[Optional[int]] = mapped_column(
            Integer,
            nullable=True,
        )
        best_iteration: Mapped[bool] = mapped_column(
            BOOLEAN,
            default=False,
            index=True,
        )
        uid: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        parent_id: Mapped[Optional[int]] = mapped_column(
            Integer,
            ForeignKey("artifacts_v2.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )
        created: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )
        updated: Mapped[Optional[datetime]] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
            nullable=True,
        )
        _full_object: Mapped[bytes] = mapped_column(
            "object",
            mlrun.db.sql_types.Blob,
        )

        parent = relationship(
            "ArtifactV2",
            remote_side=[id],
            backref="child_artifacts",
            passive_deletes=True,
        )

        @property
        def full_object(self):
            if self._full_object:
                artifact_struct = pickle.loads(self._full_object)

                # These fields are saved in full_object as timestamps with fsp=6, while the corresponding columns
                # in the database have fsp=3. Since 'ORDER BY' is applied to the column, we return the value from
                # the column (not from the full_object) to ensure the ordering is correct.
                # In SQLite, the updated and created columns return timestamps with fsp=6.
                artifact_struct["metadata"]["updated"] = mlrun.utils.format_datetime(
                    self.updated
                )
                artifact_struct["metadata"]["created"] = mlrun.utils.format_datetime(
                    self.created
                )
                return artifact_struct

        @full_object.setter
        def full_object(self, value):
            self._full_object = pickle.dumps(value)

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.key}/{self.uid}"

    class Function(Base, LabelMixin, TagV2Mixin, mlrun.utils.db.HasStruct):
        __tablename__ = "functions"
        __table_args__ = (
            UniqueConstraint("name", "project", "uid", name="_functions_uc"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        uid: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        kind: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        state: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        # TODO: change to JSON, see mlrun/common/schemas/function.py::FunctionState for reasoning
        body: Mapped[bytes] = mapped_column(
            mlrun.db.sql_types.Blob,
        )
        updated: Mapped[Optional[datetime]] = mapped_column(
            mlrun.db.sql_types.DateTime,
            nullable=True,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}/{self.uid}"

    class Run(Base, LabelMixin, TagMixin, NotificationMixin, mlrun.utils.db.HasStruct):
        __tablename__ = "runs"
        __table_args__ = (
            UniqueConstraint("uid", "project", "iteration", name="_runs_uc"),
            Index("idx_runs_project_id", "id", "project", unique=True),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        uid: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, default="no-name"
        )
        iteration: Mapped[int] = mapped_column(
            Integer,
        )
        state: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        # TODO: change to JSON, see mlrun/common/schemas/function.py::FunctionState for reasoning
        body: Mapped[bytes] = mapped_column(
            mlrun.db.sql_types.Blob,
        )
        start_time: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
        )
        end_time: Mapped[Optional[datetime]] = mapped_column(
            mlrun.db.sql_types.MicroSecondDateTime,
            nullable=True,
        )
        updated: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime, default=datetime.utcnow
        )
        # requested logs column indicates whether logs were requested for this run
        # None - old runs prior to the column addition, logs were already collected for them, so no need to collect them
        # False - logs were not requested for this run
        # True - logs were requested for this run
        requested_logs: Mapped[bool] = mapped_column(
            BOOLEAN,
            default=False,
            index=True,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.uid}/{self.iteration}"

    class BackgroundTask(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "background_tasks"
        __table_args__ = (
            UniqueConstraint("name", "project", name="_background_tasks_uc"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        created: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )
        updated: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )
        state: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        error: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        timeout: Mapped[Optional[int]] = mapped_column(
            Integer,
            nullable=True,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}"

    class Schedule(Base, LabelMixin, mlrun.utils.db.BaseModel):
        __tablename__ = "schedules_v2"
        __table_args__ = (UniqueConstraint("project", "name", name="_schedules_v2_uc"),)

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        kind: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        desired_state: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        state: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        creation_time: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
        )
        cron_trigger_str: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        last_run_uri: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        # TODO: change to JSON, see mlrun/common/schemas/function.py::FunctionState for reasoning
        struct: Mapped[bytes] = mapped_column(
            mlrun.db.sql_types.Blob,
        )

        concurrency_limit: Mapped[int] = mapped_column(
            Integer,
            nullable=False,
        )
        next_run_time: Mapped[Optional[datetime]] = mapped_column(
            mlrun.db.sql_types.DateTime,
            nullable=True,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}"

        @property
        def scheduled_object(self):
            return pickle.loads(self.struct)

        @scheduled_object.setter
        def scheduled_object(self, value):
            self.struct = pickle.dumps(value)

        @property
        def cron_trigger(self) -> mlrun.common.schemas.ScheduleCronTrigger:
            return orjson.loads(self.cron_trigger_str)

        @cron_trigger.setter
        def cron_trigger(self, trigger: mlrun.common.schemas.ScheduleCronTrigger):
            self.cron_trigger_str = orjson.dumps(trigger.dict(exclude_unset=True))

    # Define "many to many" users/projects
    project_users = Table(
        "project_users",
        Base.metadata,
        Column("project_id", Integer, ForeignKey("projects.id")),
        Column("user_id", Integer, ForeignKey("users.id")),
    )

    class User(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "users"
        __table_args__ = (UniqueConstraint("name", name="_users_uc"),)

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )

        def get_identifier_string(self) -> str:
            return f"{self.name}"

    class Project(Base, LabelMixin, mlrun.utils.db.BaseModel):
        __tablename__ = "projects"
        # For now since we use project name a lot
        __table_args__ = (UniqueConstraint("name", name="_projects_uc"),)

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        description: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        owner: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        source: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        # the attribute name used to be _spec which is just a wrong naming, the attribute was renamed to _full_object
        # leaving the column as is to prevent redundant migration
        # TODO: change to JSON, see mlrun/common/schemas/function.py::FunctionState for reasoning
        _full_object: Mapped[bytes] = mapped_column(
            "spec",
            mlrun.db.sql_types.Blob,
            nullable=True,
        )
        created: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime, default=datetime.now(tz=timezone.utc)
        )
        default_function_node_selector: Mapped[Optional[dict]] = mapped_column(
            "default_function_node_selector",
            JSON,
            nullable=True,
        )
        state: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        users = relationship(User, secondary=project_users)

        def get_identifier_string(self) -> str:
            return f"{self.name}"

        @property
        def full_object(self):
            if self._full_object:
                return pickle.loads(self._full_object)

        @full_object.setter
        def full_object(self, value):
            self._full_object = pickle.dumps(value)

    class Feature(Base, LabelMixin, mlrun.utils.db.BaseModel):
        __tablename__ = "features"
        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        feature_set_id: Mapped[int] = mapped_column(
            Integer, ForeignKey("feature_sets.id", ondelete="CASCADE")
        )

        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        value_type: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )

        feature_set = relationship(
            "FeatureSet",
            back_populates="features",
        )

        def get_identifier_string(self) -> str:
            return f"{self.feature_set_id}/{self.name}"

    class Entity(Base, LabelMixin, mlrun.utils.db.BaseModel):
        __tablename__ = "entities"
        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        feature_set_id: Mapped[int] = mapped_column(
            Integer, ForeignKey("feature_sets.id", ondelete="CASCADE")
        )

        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        value_type: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )

        feature_set = relationship(
            "FeatureSet",
            back_populates="entities",
        )

    class FeatureSet(Base, LabelMixin, TagV2Mixin, mlrun.utils.db.BaseModel):
        __tablename__ = "feature_sets"
        __table_args__ = (
            UniqueConstraint("name", "project", "uid", name="_feature_set_uc"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        created: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )
        updated: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )
        state: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        uid: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )

        _full_object: Mapped[dict] = mapped_column(
            "object",
            JSON,
        )

        features = relationship(
            Feature,
            cascade="all, delete-orphan",
            back_populates="feature_set",
            passive_deletes=True,
        )
        entities = relationship(
            Entity,
            cascade="all, delete-orphan",
            back_populates="feature_set",
            passive_deletes=True,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}/{self.uid}"

        @property
        def full_object(self):
            if self._full_object:
                return json.loads(self._full_object)

        @full_object.setter
        def full_object(self, value):
            # TODO - convert to pickle, to avoid issues with non-json serializable fields such as datetime
            self._full_object = json.dumps(value, default=str)

    class FeatureVector(Base, LabelMixin, TagV2Mixin, mlrun.utils.db.BaseModel):
        __tablename__ = "feature_vectors"
        __table_args__ = (
            UniqueConstraint("name", "project", "uid", name="_feature_vectors_uc"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        created: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )
        updated: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )
        state: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        uid: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )

        _full_object: Mapped[dict] = mapped_column(
            "object",
            JSON,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}/{self.uid}"

        @property
        def full_object(self):
            if self._full_object:
                return json.loads(self._full_object)

        @full_object.setter
        def full_object(self, value):
            # TODO - convert to pickle, to avoid issues with non-json serializable fields such as datetime
            self._full_object = json.dumps(value, default=str)

    class HubSource(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "hub_sources"
        __table_args__ = (UniqueConstraint("name", name="_hub_sources_uc"),)

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        index: Mapped[Optional[int]] = mapped_column(
            Integer,
            nullable=True,
        )
        created: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )
        updated: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )

        _full_object: Mapped[dict] = mapped_column(
            "object",
            JSON,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}"

        @property
        def full_object(self):
            if self._full_object:
                return json.loads(self._full_object)

        @full_object.setter
        def full_object(self, value):
            # TODO - convert to pickle, to avoid issues with non-json serializable fields such as datetime
            self._full_object = json.dumps(value, default=str)

    class DataVersion(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "data_versions"
        __table_args__ = (UniqueConstraint("version", name="_versions_uc"),)

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        version: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        created: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )

        def get_identifier_string(self) -> str:
            return f"{self.version}"

    class DatastoreProfile(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "datastore_profiles"
        __table_args__ = (
            UniqueConstraint("name", "project", name="_datastore_profiles_uc"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        type: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        _full_object: Mapped[dict] = mapped_column(
            "object",
            JSON,
        )

        @property
        def full_object(self):
            if self._full_object:
                return json.loads(self._full_object)

        @full_object.setter
        def full_object(self, value):
            self._full_object = json.dumps(value, default=str)

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}"

    class PaginationCache(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "pagination_cache"

        key: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, primary_key=True
        )
        user: Mapped[Optional[str]] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=True,
        )
        function: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        current_page: Mapped[int] = mapped_column(
            Integer,
        )
        page_size: Mapped[int] = mapped_column(
            Integer,
        )
        kwargs: Mapped[dict] = mapped_column(
            JSON,
        )
        last_accessed: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,  # TODO: change to `datetime`, see ML-6921
            default=lambda: datetime.now(timezone.utc),
        )

        def get_identifier_string(self) -> str:
            return f"{self.key}"

    class AlertState(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "alert_states"
        __table_args__ = (UniqueConstraint("parent_id", name="_alert_state_parent_uc"),)

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        count: Mapped[int] = mapped_column(
            Integer,
        )
        created: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,  # TODO: change to `datetime`, see ML-6921
            default=lambda: datetime.now(timezone.utc),
        )
        last_updated: Mapped[Optional[datetime]] = mapped_column(
            mlrun.db.sql_types.DateTime,  # TODO: change to `datetime`, see ML-6921
            default=None,
            nullable=True,
        )
        active: Mapped[bool] = mapped_column(
            BOOLEAN,
            default=False,
        )

        parent_id: Mapped[int] = mapped_column(
            Integer,
            ForeignKey("alert_configs.id"),
        )

        _full_object: Mapped[Optional[dict]] = mapped_column(
            "object",
            JSON,
            nullable=True,
        )

        @property
        def full_object(self):
            if self._full_object:
                return json.loads(self._full_object)

        @full_object.setter
        def full_object(self, value):
            self._full_object = json.dumps(value, default=str)

        def get_identifier_string(self) -> str:
            return f"{self.id}"

    class AlertConfig(Base, NotificationMixin, mlrun.utils.db.BaseModel):
        __tablename__ = "alert_configs"
        __table_args__ = (
            UniqueConstraint("project", "name", name="_alert_configs_uc"),
        )

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )

        alerts = relationship(AlertState, cascade="all, delete-orphan")

        _full_object: Mapped[dict] = mapped_column(
            "object",
            JSON,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}"

        @property
        def full_object(self):
            if self._full_object:
                return json.loads(self._full_object)

        @full_object.setter
        def full_object(self, value):
            self._full_object = json.dumps(value, default=str)

    class AlertTemplate(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "alert_templates"
        __table_args__ = (UniqueConstraint("name", name="_alert_templates_uc"),)

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )

        _full_object: Mapped[dict] = mapped_column(
            "object",
            JSON,
        )

        def get_identifier_string(self) -> str:
            return f"{self.name}"

        @property
        def full_object(self):
            if self._full_object:
                return json.loads(self._full_object)

        @full_object.setter
        def full_object(self, value):
            self._full_object = json.dumps(value, default=str)

    class AlertActivation(Base):
        __tablename__ = "alert_activations"

        # partition setup at import
        _interval_name = os.getenv("PARTITION_INTERVAL", "YEARWEEK").upper()
        if not mlrun.common.schemas.partition.PartitionInterval.is_valid(
            _interval_name
        ):
            raise ValueError(
                f"Partition interval must be one of: "
                f"{mlrun.common.schemas.partition.PartitionInterval.valid_intervals()}"
            )
        _interval = mlrun.common.schemas.partition.PartitionInterval(_interval_name)
        _expr = _interval.get_partition_expression(column_name="activation_time")
        _pname, _pval = _interval.get_partition_info(datetime.utcnow())[0]

        __table_args__ = (
            PrimaryKeyConstraint("id", "activation_time", name="_alert_activation_uc"),
            Index("ix_alert_activation_project_name", "project", "name"),
            Index(
                "ix_alert_activation_project_activation_time",
                "project",
                "activation_time",
            ),
            {
                "mysql_engine": "InnoDB",
                "mysql_charset": "utf8mb4",
                "mysql_partition_by": f"RANGE ({_expr})",
                "mysql_partition_options": f"(PARTITION p{_pname} VALUES LESS THAN ({_pval}))",
                "postgresql_partition_by": f"RANGE ({_expr})",
            },
        )

        id: Mapped[int] = mapped_column(
            Integer,
            autoincrement=True,
            primary_key=True,
        )
        # Keep fsp=3 for activation_time as it is part of the primary key and partitioning logic,
        # ensuring stable indexing and avoiding potential inconsistencies.
        # This must remain unchanged to maintain compatibility with existing logic
        # and prevent unintended precision changes.
        activation_time: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime(timezone=True), nullable=False
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText(), nullable=False
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText(), nullable=False
        )
        data: Mapped[dict] = mapped_column(
            JSON,
        )
        entity_id: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText(), nullable=False
        )
        entity_kind: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText(), nullable=False
        )
        event_kind: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText(), nullable=False
        )
        severity: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText(), nullable=False
        )
        number_of_events: Mapped[int] = mapped_column(
            Integer,
            nullable=False,
        )

        # Similarly, keep fsp=3 for reset_time to ensure consistency with activation_time
        # and maintain compatibility with the existing system behavior.
        reset_time: Mapped[Optional[datetime]] = mapped_column(
            mlrun.db.sql_types.DateTime(timezone=True),
            nullable=True,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}/{self.name}/{self.id}"

    class ProjectSummary(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "project_summaries"
        __table_args__ = (UniqueConstraint("project", name="_project_summaries_uc"),)

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )
        updated: Mapped[Optional[datetime]] = mapped_column(
            mlrun.db.sql_types.MicroSecondDateTime,
            nullable=True,
        )
        summary: Mapped[dict] = mapped_column(
            JSON,
        )

        def get_identifier_string(self) -> str:
            return f"{self.project}"

    class TimeWindowTracker(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "time_window_trackers"

        key: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, primary_key=True
        )
        timestamp: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.MicroSecondDateTime,
            nullable=False,
            default=lambda: datetime.now(timezone.utc),
        )
        max_window_size_seconds: Mapped[int] = mapped_column(
            Integer,
        )

        def get_identifier_string(self) -> str:
            return f"{self.key}"

    class ModelEndpoint(Base, LabelMixin, TagV2Mixin, mlrun.utils.db.HasStruct):
        __tablename__ = "model_endpoints"

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        uid: Mapped[str] = mapped_column(
            mlrun.db.sql_types.UuidType, default=lambda: uuid.uuid4().hex, unique=True
        )
        name: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        endpoint_type: Mapped[int] = mapped_column(
            Integer,
            nullable=False,
        )
        project: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
        )
        body: Mapped[bytes] = mapped_column(
            mlrun.db.sql_types.Blob,
        )
        created: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )
        updated: Mapped[datetime] = mapped_column(
            mlrun.db.sql_types.DateTime,
            default=lambda: datetime.now(timezone.utc),
        )
        function_id: Mapped[Optional[int]] = mapped_column(
            Integer,
            ForeignKey("functions.id", ondelete="SET NULL"),
            nullable=True,
        )
        function = relationship(Function)

        model_id: Mapped[Optional[int]] = mapped_column(
            Integer,
            ForeignKey("artifacts_v2.id"),
            nullable=True,
        )
        model = relationship(ArtifactV2)

        def get_identifier_string(self) -> str:
            return f"{self.project}_{self.name}_{self.created}"

    class SystemMetadata(Base, mlrun.utils.db.BaseModel):
        __tablename__ = "system_metadata"
        __table_args__ = (UniqueConstraint("key", name="_system_metadata_uc"),)

        id: Mapped[int] = mapped_column(
            Integer,
            primary_key=True,
        )
        key: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText,
            nullable=False,
        )
        # This column stores a string value, when extracting or manipulating it, ensure to handle it appropriately
        value: Mapped[str] = mapped_column(
            mlrun.db.sql_types.Utf8BinText, nullable=False
        )

        def get_identifier_string(self) -> str:
            return f"{self.key}"


@event.listens_for(AlertActivation.__table__, "before_create")
def _disable_autoinc_on_sqlite(table, connection, **kw):
    if connection.dialect.name == "sqlite":
        # disable SQLAlchemy's AUTOINCREMENT flag
        table.c.id.autoincrement = False


@event.listens_for(AlertActivation, "before_insert")
def _sqlite_autoincrement(
    mapper: Mapper, connection: Connection, target: AlertActivation
) -> None:
    if connection.dialect.name == "sqlite" and target.id is None:
        next_id: int = connection.execute(
            text("SELECT COALESCE(MAX(id),0) + 1 FROM alert_activations")
        ).scalar_one()
        target.id = next_id


def get_partitioned_table_names():
    return [
        AlertActivation.__tablename__,
    ]


# Must be after all table definitions
post_table_definitions(base_cls=Base)
