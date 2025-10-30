from pydantic import BaseModel
from typing import Optional

class StatusResponse(BaseModel):
    status: str
    source: Optional[str] = None
    path: Optional[str] = None
    message: Optional[str] = None
