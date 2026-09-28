import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, UniqueConstraint
from sqlmodel import Column, Field, SQLModel


class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    slug: str = Field(max_length=100, unique=True)
    settings: Any = Field(default_factory=dict, sa_column=Column("settings", JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ApiKey(SQLModel, table=True):
    __tablename__ = "api_keys"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")
    key_hash: str = Field(max_length=64)
    key_prefix: str = Field(max_length=8)
    name: str = Field(max_length=255)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Connection(SQLModel, table=True):
    __tablename__ = "connections"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")
    integration: str = Field(max_length=50)
    status: str = Field(default="active", max_length=20)
    mango_connection_id: str | None = Field(default=None, max_length=100)
    access_token: str | None = Field(default=None)
    refresh_token: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Resource(SQLModel, table=True):
    __tablename__ = "resources"
    __table_args__ = (UniqueConstraint("workspace_id", "integration", "external_id"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")
    integration: str = Field(max_length=50)
    external_id: str = Field(max_length=255)
    title: str = Field(max_length=500)
    content: str = Field(default="")
    doc_metadata: Any = Field(default_factory=dict, sa_column=Column("metadata", JSON))
    status: str = Field(default="pending", max_length=20)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Chunk(SQLModel, table=True):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("resource_id", "chunk_index"),)

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    resource_id: uuid.UUID = Field(foreign_key="resources.id")
    workspace_id: uuid.UUID = Field(foreign_key="workspaces.id")
    content: str
    embedding: list[float] = Field(sa_column=Column(Vector(384)))
    chunk_index: int
    doc_metadata: Any = Field(default_factory=dict, sa_column=Column("metadata", JSON))
    source: str = Field(max_length=50)
    created_at: datetime = Field(default_factory=datetime.utcnow)
