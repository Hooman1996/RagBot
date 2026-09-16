from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_evaluation_session


DatabaseDep = Annotated[AsyncSession, Depends(get_evaluation_session)]
