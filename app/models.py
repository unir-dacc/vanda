from typing import Literal, Optional

from pydantic import BaseModel, Field


class QueryFilter(BaseModel):
    order: Optional[Literal["asc", "desc"]] = Field(
        default=None, description="Ordem de classificação (ascendente ou descendente)."
    )


from pydantic import BaseModel
from typing import List, Optional


class MutationDetail(BaseModel):
    id: str
    mutation: str


class HGVSData(BaseModel):
    proteins: List[MutationDetail]
    genomics: List[MutationDetail]
    mrnas: List[MutationDetail]


class PubMedArticle(BaseModel):
    pmid: str
    title: str
    abstract: str


class SNPData(BaseModel):
    snp: str
    chromosome: str
    position: str
    allele: str
    extra_info: List[str]
    hgvs: HGVSData
    pubmed_articles: List[PubMedArticle]


class SNPResponse(BaseModel):
    items: List[SNPData]
