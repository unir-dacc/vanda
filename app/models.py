from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# Base
class QueryFilter(BaseModel):
	order: Optional[Literal["asc", "desc"]] = Field(
		default=None, description="Ordem de classificação (ascendente ou descendente)."
	)


# HGVS / Mutations
class MutationDetail(BaseModel):
	id: str
	mutation: str


class HGVSData(BaseModel):
	proteins: list[MutationDetail]
	genomics: list[MutationDetail]
	mrnas: list[MutationDetail]


# PubMed
class PubMedArticle(BaseModel):
	pmid: str
	title: str
	abstract: str = ""


# Search endpoint
class SearchResultItem(BaseModel):
	snp_id: str
	chromossome_number: str
	genomic_position: str
	alleles: str
	genes: list[str]
	mutations: HGVSData
	publications: list[PubMedArticle] = []


# SNP page endpoint
class SNPTopicArticle(BaseModel):
	pmid: str
	title: str
	abstract: str = ""


class SNPPageResponse(BaseModel):
	topics: dict[str, list[SNPTopicArticle]]
	genes: list[str]


# Gene page endpoint
class GenePageResponse(BaseModel):
	gene_name: str
	description: str
	snp_topics: dict[str, list[SNPTopicArticle]]
	data: dict[str, list[SNPTopicArticle]]


# Food analysis endpoint
class PredictionDetail(BaseModel):
	food: str
	disease: str
	direction: str
	snp_id: str
	gene_info: str
	confidence: float = 0.0
	rn: int = 0


class DirectionCounts(BaseModel):
	snps: int
	genes: int


class SNPByGene(BaseModel):
	gene_info: str
	snp_count: int


class DiseaseInfo(BaseModel):
	disease: str
	gene_info: str


class FoodAnalysisResponse(BaseModel):
	totalDetails: dict[str, int]
	counts: dict[str, DirectionCounts]
	details: dict[str, list[PredictionDetail]]
	disease: list[DiseaseInfo]
	snpByGene: list[SNPByGene]
