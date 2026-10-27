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
