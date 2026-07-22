import logging
import os

import requests
from Bio import Entrez
from dotenv import load_dotenv

load_dotenv()
Entrez.email = os.getenv("EMAIL")

logger = logging.getLogger(__name__)


def batch_iterator(iterable, batch_size):
	for i in range(0, len(iterable), batch_size):
		yield iterable[i : i + batch_size]


def search_snp(query, page=1, max_results=500):
	offset = (page - 1) * max_results
	url = (
		f"https://clinicaltables.nlm.nih.gov/api/snps/v3/search?terms={query}"
		f"&maxList={max_results}&offset={offset}"
	)
	response = requests.get(url)
	if response.status_code == 200:
		result = response.json()
		return {"num_items": result[0], "data": result[3]}
	else:
		logger.error(f"Error in search_snp request: {response.status_code}")
		return {"num_items": 0, "data": []}


class SnpData:
	def __init__(self, snp_id):
		self.snp_id = snp_id if isinstance(snp_id, list) else [snp_id]
		self.data = self._fetch_snp_data()

	def _fetch_snp_data(self):
		batch_size = 500
		all_summaries = {"DocumentSummarySet": {"DocumentSummary": []}}
		for batch in batch_iterator(self.snp_id, batch_size):
			with Entrez.esummary(db="snp", id=",".join(batch)) as handle:
				batch_data = Entrez.read(handle, validate=False)
			all_summaries["DocumentSummarySet"]["DocumentSummary"].extend(
				batch_data["DocumentSummarySet"]["DocumentSummary"]
			)
		return all_summaries

	def get_snp_hgvs(self):
		hgvs = []
		for item in self.data["DocumentSummarySet"]["DocumentSummary"]:
			hgvs.append(item["DOCSUM"][5:].split("|")[0].split(","))
		return hgvs


NUTRITION_MESH = [
	"Nutrigenomics", "Nutrigenetics", "Diet",
	"Nutrients", "Nutritional Genomics",
	"Vitamins", "Fatty Acids", "Minerals",
	"Folic Acid", "Vitamin D", "Omega-3 Fatty Acids",
	"Caffeine", "Alcohol Drinking",
	"Food", "Feeding Behavior",
	"Micronutrients", "Dietary Supplements",
	"Nutritional Status",
]

SNP_MESH = "Polymorphism, Single Nucleotide"


def get_filter_term():
	nutrition_part = " OR ".join(f'"{t}"[MeSH Terms]' for t in NUTRITION_MESH)
	return f' AND ({nutrition_part}) AND "{SNP_MESH}"[MeSH Terms]'


def _parse_article(article):
	citation = article.get("MedlineCitation", {})
	article_data = citation.get("Article", {})
	pmid = str(citation.get("PMID", ""))
	title = article_data.get("ArticleTitle", "")
	abstract_texts = article_data.get("Abstract", {}).get("AbstractText", [])
	abstract = " ".join(abstract_texts) if abstract_texts else ""
	return {"pmid": pmid, "title": title, "abstract": abstract}


def get_abstracts_by_gene(gene_id):
	term = f"{gene_id.upper()} AND (snp_pubmed_cited[Filter] OR snp_pubmed[Filter])"
	with Entrez.esearch(db="snp", term=term, retmode="xml", retmax=1000) as handle:
		snp_ids = Entrez.read(handle).get("IdList", [])
	if not snp_ids:
		return [], {}

	pubmed_data_all = []
	for batch in batch_iterator(snp_ids, 100):
		with Entrez.elink(
			dbfrom="snp", db="pubmed", id=",".join(batch), retmode="xml"
		) as handle:
			pubmed_data_all.extend(Entrez.read(handle))

	snp_to_pubmed = {}
	pubmed_ids = []
	for pubmed_item in pubmed_data_all:
		snp = pubmed_item.get("IdList", [""])[0]
		for linkset_db in pubmed_item.get("LinkSetDb", []):
			for link in linkset_db.get("Link", []):
				pubmed_id = link["Id"]
				pubmed_ids.append(pubmed_id)
				snp_to_pubmed.setdefault(snp, []).append(pubmed_id)

	if not pubmed_ids:
		return [], {}

	filter_search = "(" + " OR ".join(pubmed_ids) + ")" + get_filter_term()
	logger.debug(filter_search)

	with Entrez.esearch(
		db="pubmed", term=filter_search, retmode="xml", retmax=1000
	) as handle:
		pubmed_ids_filtered = Entrez.read(handle).get("IdList", [])

	if not pubmed_ids_filtered:
		return [], {}

	abstracts = []
	for batch in batch_iterator(pubmed_ids_filtered, 100):
		with Entrez.efetch(
			db="pubmed", id=batch, rettype="medline", retmode="xml"
		) as handle:
			articles = Entrez.read(handle)
		for article in articles.get("PubmedArticle", []):
			parsed = _parse_article(article)
			if parsed["abstract"]:
				abstracts.append(parsed)

	return abstracts, snp_to_pubmed


def get_abstracts_by_snp(snp_id):
	if isinstance(snp_id, list):
		pubmed_data_all = []
		for batch in batch_iterator(snp_id, 100):
			with Entrez.elink(
				dbfrom="snp", db="pubmed", id=",".join(batch), retmode="xml"
			) as handle:
				pubmed_data_all.extend(Entrez.read(handle))
	else:
		with Entrez.elink(
			dbfrom="snp", db="pubmed", id=snp_id, retmode="xml"
		) as handle:
			pubmed_data_all = Entrez.read(handle)

	ids = []
	for pubmed_item in pubmed_data_all:
		for linkset_db in pubmed_item.get("LinkSetDb", []):
			for link in linkset_db.get("Link", []):
				ids.append(link["Id"])

	if not ids:
		return []

	return fetch_pubmed_articles(ids)


def fetch_pubmed_articles(ids):
	filter_search = "(" + " OR ".join(ids) + ")" + get_filter_term()
	with Entrez.esearch(
		db="pubmed", term=filter_search, retmode="xml", retmax=1000
	) as handle:
		pubmed_ids_filtered = Entrez.read(handle).get("IdList", [])

	if not pubmed_ids_filtered:
		return []

	abstracts = []
	for batch in batch_iterator(pubmed_ids_filtered, 100):
		with Entrez.efetch(
			db="pubmed", id=batch, rettype="medline", retmode="xml"
		) as handle:
			articles = Entrez.read(handle)
		for article in articles.get("PubmedArticle", []):
			parsed = _parse_article(article)
			if parsed["abstract"]:
				abstracts.append(parsed)

	return abstracts


def fetch_pubmed_articles_by_snp(snp_ids, include_abstract=False):
	if not snp_ids:
		return []

	filter_search = "(" + " OR ".join(snp_ids) + ")" + get_filter_term()
	with Entrez.esearch(
		db="pubmed", term=filter_search, retmode="xml", retmax=1000
	) as handle:
		pubmed_ids_filtered = Entrez.read(handle).get("IdList", [])

	if not pubmed_ids_filtered:
		return []

	abstracts = []
	for batch in batch_iterator(pubmed_ids_filtered, 100):
		try:
			with Entrez.efetch(
				db="pubmed", id=batch, rettype="medline", retmode="xml"
			) as handle:
				articles = Entrez.read(handle)
		except Exception as e:
			logger.error(f"Erro ao buscar detalhes dos artigos: {e}")
			continue
		for article in articles.get("PubmedArticle", []):
			parsed = _parse_article(article)
			if parsed["pmid"] and parsed["title"]:
				if not include_abstract:
					parsed["abstract"] = ""
				abstracts.append(parsed)

	return abstracts


def get_articles_for_snps(snp_ids, batch_size=100):
	results = {}
	for snp_batch in batch_iterator(snp_ids, batch_size):
		try:
			with Entrez.elink(
				dbfrom="snp", db="pubmed", id=",".join(snp_batch), retmode="xml"
			) as handle:
				pubmed_data_batch = Entrez.read(handle)
		except Exception as e:
			logger.error(f"Erro no Entrez.elink para lote de SNPs: {e}")
			continue

		snp_to_pubmed = {}
		all_pubmed_ids = set()
		for item in pubmed_data_batch:
			snp = item.get("IdList", [""])[0]
			for linkset in item.get("LinkSetDb", []):
				for link in linkset.get("Link", []):
					pmid = link["Id"]
					all_pubmed_ids.add(pmid)
					snp_to_pubmed.setdefault(snp, []).append(pmid)

		# Filtrar por nutrigenética antes de baixar
		filtered_pubmed_ids = set()
		if all_pubmed_ids:
			for pmid_batch in batch_iterator(list(all_pubmed_ids), 500):
				filter_search = (
					"(" + " OR ".join(pmid_batch) + ")" + get_filter_term()
				)
				try:
					with Entrez.esearch(
						db="pubmed", term=filter_search, retmode="xml", retmax=1000
					) as handle:
						filtered = Entrez.read(handle).get("IdList", [])
					filtered_pubmed_ids.update(filtered)
				except Exception as e:
					logger.error(f"Erro no filtro de nutrigenética: {e}")
					filtered_pubmed_ids.update(pmid_batch)

		articles_by_pmid = {}
		if filtered_pubmed_ids:
			for pmid_batch in batch_iterator(list(filtered_pubmed_ids), batch_size):
				try:
					with Entrez.efetch(
						db="pubmed", id=pmid_batch, rettype="medline", retmode="xml"
					) as handle:
						articles = Entrez.read(handle)
				except Exception as e:
					logger.error(f"Erro no Entrez.efetch para PubMed IDs: {e}")
					continue
				for article in articles.get("PubmedArticle", []):
					parsed = _parse_article(article)
					articles_by_pmid[parsed["pmid"]] = parsed

		for snp, pmid_list in snp_to_pubmed.items():
			results[snp] = [
				articles_by_pmid[pmid]
				for pmid in pmid_list
				if pmid in articles_by_pmid
			]

	return results


def get_summary_of_gene(gene_id):
	with Entrez.esearch(
		db="gene", term=gene_id, retmode="xml", sort="relevance"
	) as handle:
		gene_ids = Entrez.read(handle).get("IdList", [])

	if not gene_ids:
		return ""

	with Entrez.esummary(db="gene", id=gene_ids[0]) as handle:
		result = Entrez.read(handle)

	return result["DocumentSummarySet"]["DocumentSummary"][0]["Summary"]
