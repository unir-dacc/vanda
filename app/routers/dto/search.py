from typing import Literal, Optional
from pydantic import Field

from app.models import QueryFilter


class QuerySearch(QueryFilter):
	query: str
	publications: Optional[bool] = Field(False)
	abstract: bool = Field(False)
	multiple_genes: Optional[bool] = Field(None)
	single_genes: Optional[bool] = Field(None)
