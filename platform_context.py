"""Immutable request platform context, independent of document category."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from utils.service_errors import InvalidRequestError

PLATFORMS = frozenset({"hibank", "negahboom"})
SOURCE_PLATFORMS = {"General_FAQ": "hibank", "NegahBoom_FAQ": "negahboom"}
# These are the existing explicit Hibank document families in document_category.py.
HIBANK_TITLE_MARKERS = ("قرارداد", "ابلاغیه")
PLATFORM_METADATA_KEY = "chatbot_platform"


@dataclass(frozen=True)
class PlatformContext:
    platform: str

    def __post_init__(self):
        if self.platform not in PLATFORMS:
            raise InvalidRequestError("Invalid chatbot platform")


def instance_platform() -> str:
    mode = os.getenv("CHATBOT_PLATFORM", "hibank")
    if mode not in PLATFORMS | {"auto"}:
        raise ValueError("CHATBOT_PLATFORM must be auto, hibank, or negahboom")
    return mode


def source_platform(title: str) -> str:
    if title in SOURCE_PLATFORMS:
        return SOURCE_PLATFORMS[title]
    if any(marker in title for marker in HIBANK_TITLE_MARKERS):
        return "hibank"
    raise InvalidRequestError("Knowledge source has no configured platform owner")


def session_platform(row: dict) -> str:
    metadata = row.get("meta_data") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    value = metadata.get(PLATFORM_METADATA_KEY, "hibank")
    return PlatformContext(value).platform


def resolve_platform(
    *, documents=(), header=None, session=None, mode=None
) -> PlatformContext:
    mode = instance_platform() if mode is None else mode
    if mode not in PLATFORMS | {"auto"}:
        raise ValueError("Invalid CHATBOT_PLATFORM")
    signals = {
        source_platform(str(title).strip()) for title in documents if str(title).strip()
    }
    if header is not None:
        signals.add(PlatformContext(header).platform)
    if mode != "auto":
        signals.add(mode)
    if session is not None:
        signals.add(session_platform(session))
    if len(signals) > 1:
        raise InvalidRequestError("Conflicting chatbot platforms")
    return PlatformContext(next(iter(signals), "hibank"))


def snapshot_session(snapshot, namespace):
    """Production legacy rows are Hibank; isolated first evaluation turns are new."""
    metadata = dict(snapshot.metadata)
    if namespace == "production":
        return {"meta_data": metadata}
    state_platform = (snapshot.agent_state or {}).get("platform")
    if state_platform is not None:
        return {"meta_data": {"chatbot_platform": state_platform}}
    # Historical evaluation state predating binding also belongs to Hibank.
    if (snapshot.agent_state or {}).get("messages"):
        return {"meta_data": {}}
    return None


def request_header(request):
    return request.headers.get("X-Chatbot-Platform")


async def check_session(request, db, runner, session_id, *, documents=()):
    row = await runner.run(db.get_session_by_id, int(session_id))
    if row is None:
        raise InvalidRequestError("Session unavailable")
    return resolve_platform(
        documents=documents, header=request_header(request), session=row
    )


async def check_query(request, db, runner, query_id):
    row = await runner.run(db.get_query_session, query_id)
    if row is None:
        raise InvalidRequestError("Query unavailable")
    return resolve_platform(header=request_header(request), session=row)
