from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_evaluation_session
from ..ragbot_auth import require_ragbot_user


AuthenticatedUserDep = Annotated[dict, Depends(require_ragbot_user)]
DatabaseDep = Annotated[AsyncSession, Depends(get_evaluation_session)]
