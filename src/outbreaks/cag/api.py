from __future__ import annotations

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from outbreaks.cag.engine import CAGEngine


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)
    region_key: str | None = None


class AskResponse(BaseModel):
    answer: str
    used_region: str | None = None
    cache_type: str


engine = CAGEngine()
router = APIRouter(tags=["cag"])


@router.get("/cag/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/cag/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    try:
        answer = engine.ask(request.question, request.region_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return AskResponse(
        answer=answer.answer,
        used_region=answer.used_region,
        cache_type=answer.cache_type,
    )


app = FastAPI(
    title="OperationalDecisionSupportSystemForWaterSecurity CAG API",
    version="0.1.0",
)
app.include_router(router)
