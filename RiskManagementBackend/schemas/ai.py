from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


AnalysisPoint = Annotated[str, Field(min_length=1, max_length=1000)]


class RiskAnalysisRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    description: Annotated[str, Field(min_length=10, max_length=4000)]
    category: Annotated[str, Field(max_length=120)] | None = None
    likelihood: int | None = Field(default=None, ge=1, le=5)
    impact: int | None = Field(default=None, ge=1, le=5)
    context: Annotated[str, Field(max_length=2000)] | None = None


class RiskAssessmentDetails(BaseModel):
    likelihood: int
    impact: int
    risk_score: int
    severity: str


class AIAnalysis(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    qualitative_assessment: AnalysisPoint
    risk_summary: AnalysisPoint
    potential_causes: list[AnalysisPoint] = Field(min_length=1, max_length=10)
    potential_consequences: list[AnalysisPoint] = Field(min_length=1, max_length=10)
    recommended_mitigations: list[AnalysisPoint] = Field(min_length=1, max_length=12)
    preventive_controls: list[AnalysisPoint] = Field(min_length=1, max_length=10)
    detection_methods: list[AnalysisPoint] = Field(min_length=1, max_length=10)
    residual_risk_considerations: list[AnalysisPoint] = Field(min_length=1, max_length=8)
    assumptions_and_uncertainty: list[AnalysisPoint] = Field(min_length=1, max_length=8)


class RiskAnalysisResponse(BaseModel):
    application_assessment: RiskAssessmentDetails | None
    ai_analysis: AIAnalysis
    simulated: bool = False
