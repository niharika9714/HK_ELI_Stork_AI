from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Condition(BaseModel):
    model_config = ConfigDict(extra='forbid')
    column: str
    operator: Literal['eq', 'ne', 'gt', 'gte', 'lt', 'lte']
    value: str


class Plan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['native', 'analyze', 'clarify']
    include_summary: bool = False
    view_id: str | None = None
    filters: list[Condition] = Field(default_factory=list, max_length=8)
    dimensions: list[str] = Field(default_factory=list, max_length=3)
    measure: str | None = None
    aggregation: Literal['none', 'sum', 'mean', 'count'] = 'none'
    period: Literal['month', 'year'] | None = None
    date_column: str | None = None
    chart: Literal['table', 'bar', 'pie', 'heatmap', 'line'] = 'table'
    explanation: str = Field(default='', max_length=500)


class RequestUnderstanding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    measures: list[str] = Field(max_length=12)
    dimensions: list[str] = Field(max_length=12)
    conditions: list[str] = Field(max_length=12)


class Requirement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    quote: str = Field(min_length=1, max_length=2000)


class SelectionAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    view_id: str
    dashboard: str
    relevance_reason: str = Field(max_length=500)
    full_match: bool
    missing_requirements: list[str] = Field(max_length=12)


class SourcePlan(Plan):
    dashboard: str | None = None
    request_understanding: RequestUnderstanding
    requirements: list[Requirement] = Field(max_length=12)
    selection_assessment: SelectionAssessment | None
