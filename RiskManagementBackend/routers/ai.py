import json
import logging
import os
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from ai_prompts import SYSTEM_PROMPT
from risk_scoring import calculate_risk_assessment
from schemas.ai import AIAnalysis, RiskAnalysisRequest, RiskAnalysisResponse
from security import require_api_user

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/v1/ai", tags=["AI Risk Analysis"], dependencies=[Depends(require_api_user)])
OLLAMA_TIMEOUT_SECONDS = 120


def _request_ollama(user_message: str) -> AIAnalysis:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "gpt-oss:20b-cloud")
    request_body = {
        "model": model,
        "stream": False,
        # JSON mode is supported by Ollama Cloud; include the exact schema in
        # the system message and still validate every returned field locally.
        "format": "json",
        "messages": [
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + "\n\nRequired JSON schema:\n"
                    + json.dumps(AIAnalysis.model_json_schema())
                ),
            },
            {"role": "user", "content": user_message},
        ],
    }
    request = Request(
        f"{base_url}/api/chat",
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
            ollama_response = json.loads(response.read().decode("utf-8"))
    except socket.timeout:
        raise HTTPException(
            status_code=504,
            detail="The AI analysis timed out. Please try again.",
        ) from None
    except HTTPError as error:
        # Do not return the Ollama response body; it may contain private details.
        logger.warning("Ollama request returned HTTP %s", error.code)
        raise HTTPException(
            status_code=503,
            detail="The AI service could not complete the request. Check that the configured model is available.",
        ) from None
    except (URLError, OSError):
        logger.warning("Ollama service is unavailable")
        raise HTTPException(
            status_code=503,
            detail="The AI service is unavailable. Check that Ollama is running and try again.",
        ) from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Ollama returned an unreadable response")
        raise HTTPException(
            status_code=502,
            detail="The AI service returned an unreadable response. Please try again.",
        ) from None

    try:
        content = ollama_response["message"]["content"]
        parsed_content = json.loads(content)
        return AIAnalysis.model_validate(parsed_content)
    except (KeyError, TypeError, json.JSONDecodeError, ValidationError):
        logger.warning("Ollama response did not match the expected analysis schema")
        raise HTTPException(
            status_code=502,
            detail="The AI service returned an invalid analysis format. Please try again.",
        ) from None


@router.post("/analyze-risk", response_model=RiskAnalysisResponse)
def analyze_risk(payload: RiskAnalysisRequest) -> RiskAnalysisResponse:
    """Analyze a risk using Ollama and return it beside the official app score."""
    if (payload.likelihood is None) != (payload.impact is None):
        raise HTTPException(
            status_code=422,
            detail="Provide both likelihood and impact to calculate the application risk score.",
        )

    assessment = None
    if payload.likelihood is not None and payload.impact is not None:
        try:
            assessment = calculate_risk_assessment(payload.likelihood, payload.impact)
        except RuntimeError:
            logger.error("Risk score thresholds are invalid")
            raise HTTPException(
                status_code=500,
                detail="Risk scoring is not configured correctly.",
            ) from None

    user_message = json.dumps(
        {
            "description": payload.description,
            "category": payload.category,
            "likelihood": payload.likelihood,
            "impact": payload.impact,
            "context": payload.context,
        },
        ensure_ascii=False,
    )

    return RiskAnalysisResponse(
        application_assessment=assessment,
        ai_analysis=_request_ollama(user_message),
    )
