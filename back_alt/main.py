"""FastAPI service for extracting findings from medical report text."""

from dataclasses import asdict

from fastapi import FastAPI
from pydantic import BaseModel

from .extractors import extract_findings


class ExtractRequest(BaseModel):
    text: str


class FindingResponse(BaseModel):
    text: str
    sentence: str
    category: str
    certainty: str
    start: int
    end: int


class ExtractResponse(BaseModel):
    count: int
    findings: list[FindingResponse]


app = FastAPI(
    title="Medical Report Text Parser",
    description="Extracts abnormal findings from Russian medical report text.",
    version="1.0.0",
)


@app.post("/api/v1/extract", response_model=ExtractResponse)
def extract_report(request: ExtractRequest) -> ExtractResponse:
    findings = extract_findings(request.text)
    return ExtractResponse(
        count=len(findings),
        findings=[FindingResponse(**asdict(finding)) for finding in findings],
    )
