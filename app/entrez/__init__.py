import requests
import logging
import os
from Bio import Entrez
from dotenv import load_dotenv

load_dotenv()
Entrez.email = os.getenv("EMAIL")


def search_snp(query, page=1, max_results=500):
	offset = (page - 1) * max_results
	url = f"https://clinicaltables.nlm.nih.gov/api/snps/v3/search?terms={query}&maxList={max_results}&offset={offset}"
	response = requests.get(url)

	if response.status_code == 200:
		result = response.json()
		return {"num_items": result[0], "data": result[3]}
	else:
		logging.error(f"Error in search_snp request: {response.status_code}")
		return {"num_items": 0, "data": []}


class SnpData:
	def __init__(self, snp_id):
		self.snp_id = snp_id
		self.is_list = isinstance(snp_id, list)
		self.data = self._fetch_snp_data()

	def _fetch_snp_data(self):
		"""
		Fetches detailed SNP information.
		"""
		with Entrez.esummary(db="snp", id=self.snp_id) as handle:
			return Entrez.read(handle, validate=False)


def get_snp_hgvs(self):
	hgvs = []
	if self.is_list:
		for item in self.data["DocumentSummarySet"]["DocumentSummary"]:
			hgvs.append(item["DOCSUM"][5:].split("|")[0].split(","))
	else:
		hgvs = (
			self.data["DocumentSummarySet"]["DocumentSummary"][0]["DOCSUM"][5:]
			.split("|")[0]
			.split(",")
		)
	return hgvs


def get_filter_term():
	base_keywords = ["Nutrients", "Nutrigenomics", "Nutrigenetics", "Diet", "Diets"]
	return " AND (" + " OR ".join([f"{kw}[MeSH Terms]" for kw in base_keywords]) + ")"


def get_abstracts_by_gene(gene_id):
	term = f"{gene_id.upper()} AND (snp_pubmed_cited[Filter] OR snp_pubmed[Filter])"

	with Entrez.esearch(db="snp", term=term, retmode="xml") as handle:
		snp_ids = Entrez.read(handle).get("IdList", [])

	if not snp_ids:
		return [], {}

	with Entrez.elink(dbfrom="snp", db="pubmed", id=",".join(snp_ids)) as handle:
		pubmed_data = Entrez.read(handle)

	snp_to_pubmed = {}
	ids = []
	for pubmed_item in pubmed_data:
		for linkset_db in pubmed_item.get("LinkSetDb", []):
			for link in linkset_db.get("Link", []):
				ids.append(link["Id"])
				snp_to_pubmed.setdefault(pubmed_item["IdList"][0], []).append(
					link["Id"]
				)

	if not ids:
		return [], {}

	filter_search = f"({' OR '.join(ids)})" + get_filter_term()
	print(filter_search)

	pubmed_ids = []
	with Entrez.esearch(db="pubmed", term=filter_search, retmode="xml") as handle:
		pubmed_ids = Entrez.read(handle).get("IdList", [])

	if not pubmed_ids:
		return [], {}

	with Entrez.efetch(
		db="pubmed", id=pubmed_ids, rettype="medline", retmode="xml"
	) as handle:
		articles = Entrez.read(handle)

	abstracts = []
	for article in articles["PubmedArticle"]:
		if "Abstract" in article["MedlineCitation"]["Article"]:
			abstracts.append(
				{
					"pmid": str(article["MedlineCitation"]["PMID"]),
					"title": article["MedlineCitation"]["Article"]["ArticleTitle"],
					"abstract": str(
						article["MedlineCitation"]["Article"]["Abstract"][
							"AbstractText"
						][0]
					),
				}
			)

	return abstracts, snp_to_pubmed


def get_abstracts_by_snp(snp_id):
	with Entrez.elink(dbfrom="snp", db="pubmed", id=snp_id, retmode="xml") as handle:
		pubmed_data = Entrez.read(handle)

	snp_to_pubmed = {}
	ids = []
	for pubmed_item in pubmed_data:
		for linkset_db in pubmed_item.get("LinkSetDb", []):
			for link in linkset_db.get("Link", []):
				ids.append(link["Id"])
				snp_to_pubmed.setdefault(pubmed_item["IdList"][0], []).append(
					link["Id"]
				)

	if not ids:
		return []

	return fetch_pubmed_articles(ids)


def fetch_pubmed_articles(snp_ids):
	filter_search = f'(" OR ".join({snp_ids}))' + get_filter_term()

	with Entrez.esearch(db="pubmed", term=filter_search, retmode="xml") as handle:
		pubmed_ids_filtered = Entrez.read(handle).get("IdList", [])

	if not pubmed_ids_filtered:
		return []

	with Entrez.efetch(
		db="pubmed", id=pubmed_ids_filtered, rettype="medline", retmode="xml"
	) as handle:
		articles = Entrez.read(handle)

	abstracts = []
	for article in articles["PubmedArticle"]:
		if "Abstract" in article["MedlineCitation"]["Article"]:
			abstracts.append(
				{
					"pmid": str(article["MedlineCitation"]["PMID"]),
					"title": article["MedlineCitation"]["Article"]["ArticleTitle"],
					"abstract": str(
						article["MedlineCitation"]["Article"]["Abstract"][
							"AbstractText"
						][0]
					),
				}
			)

	return abstracts


def fetch_pubmed_articles_by_snp(snp_ids, include_abstract=False):
	if not snp_ids:
		return []

	filter_search = f"({' OR '.join(snp_ids)})" + get_filter_term()

	with Entrez.esearch(db="pubmed", term=filter_search, retmode="xml") as handle:
		search_results = Entrez.read(handle)
		pubmed_ids_filtered = search_results.get("IdList", [])

	if not pubmed_ids_filtered:
		return []

	try:
		with Entrez.efetch(
			db="pubmed", id=pubmed_ids_filtered, rettype="medline", retmode="xml"
		) as handle:
			articles = Entrez.read(handle)
	except Exception as e:
		print(f"Erro ao buscar detalhes dos artigos: {e}")
		return []

	abstracts = []
	for article in articles.get("PubmedArticle", []):
		citation = article.get("MedlineCitation", {}).get("Article", {})
		pmid = article.get("MedlineCitation", {}).get("PMID", "")
		title = citation.get("ArticleTitle", "")
		abstract_texts = citation.get("Abstract", {}).get("AbstractText", [])
		abstract = " ".join(abstract_texts) if abstract_texts else ""

		if pmid and title:
			abstracts.append(
				{
					"pmid": str(pmid),
					"title": title,
					"abstract": abstract if include_abstract else "",
				}
			)

	return abstracts


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
