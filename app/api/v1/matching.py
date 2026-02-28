from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.match import MatchRequest, MatchResponse
from app.services.match_service import (
    CandidateProfileValidationError,
    LLMRerankConfigurationError,
    MatchExperimentService,
    MatchQueryError,
)

router = APIRouter(prefix="/matching", tags=["matching"])


def get_match_service() -> MatchExperimentService:
    return MatchExperimentService()


@router.post(
    "/recommendations",
    response_model=MatchResponse,
    responses={
        422: {"description": "Invalid candidate profile"},
        503: {"description": "Matching dependencies unavailable"},
    },
)
async def get_match_recommendations(
    request: MatchRequest,
    service: MatchExperimentService = Depends(get_match_service),
) -> MatchResponse:
    try:
        return await service.run(request)
    except CandidateProfileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except (MatchQueryError, LLMRerankConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
