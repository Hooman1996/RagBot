"""Dedicated SQLAlchemy metadata for evaluation-owned objects only."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


EVALUATION_SCHEMA = "evaluation"
evaluation_metadata = MetaData(schema=EVALUATION_SCHEMA)


class EvaluationBase(DeclarativeBase):
    metadata = evaluation_metadata

