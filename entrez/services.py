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
            return Entrez.read(handle)

    def get_snp_hgvs(self):
        """
        Returns the SNP HGVS identifiers.
        """
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

def get_abstracts_by_gene(gene_id, page=1, max_results=20):
    term = f"{gene_id.upper()} AND (snp_pubmed_cited[Filter] OR snp_pubmed[Filter])"
    offset = (page - 1) * max_results

    with Entrez.esearch(db="snp", term=term, retmode="xml", retstart=offset, retmax=max_results) as handle:
        snp_ids = Entrez.read(handle).get("IdList", [])

    if not snp_ids:
        return [], {}

    return fetch_pubmed_articles(snp_ids, page, max_results)

def get_abstracts_by_snp(snp_id, page=1, max_results=20):
    with Entrez.elink(dbfrom="snp", db="pubmed", id=snp_id, retmode="xml") as handle:
        pubmed_data = Entrez.read(handle)

    snp_to_pubmed = {}
    ids = []
    for pubmed_item in pubmed_data:
        for linkset_db in pubmed_item.get("LinkSetDb", []):
            for link in linkset_db.get("Link", []):
                ids.append(link["Id"])
                snp_to_pubmed.setdefault(pubmed_item["IdList"][0], []).append(link["Id"])

    if not ids:
        return []

    return fetch_pubmed_articles(ids, page, max_results)

def fetch_pubmed_articles(snp_ids, page=1, max_results=20):
    filter_search = f'(" OR ".join(snp_ids))' + get_filter_term()
    offset = (page - 1) * max_results

    with Entrez.esearch(db="pubmed", term=filter_search, retmode="xml", retstart=offset, retmax=max_results) as handle:
        pubmed_ids_filtered = Entrez.read(handle).get("IdList", [])

    if not pubmed_ids_filtered:
        return []

    with Entrez.efetch(db="pubmed", id=pubmed_ids_filtered, rettype="medline", retmode="xml") as handle:
        articles = Entrez.read(handle)

    abstracts = []
    for article in articles["PubmedArticle"]:
        if "Abstract" in article["MedlineCitation"]["Article"]:
            abstracts.append(
                {
                    "pmid": str(article["MedlineCitation"]["PMID"]),
                    "title": article["MedlineCitation"]["Article"]["ArticleTitle"],
                    "abstract": str(article["MedlineCitation"]["Article"]["Abstract"]["AbstractText"][0]),
                }
            )

    return abstracts

def fetch_pubmed_articles_by_snp(snp_ids):
    filter_search = f'({" OR ".join(snp_ids)})' + get_filter_term()

    with Entrez.esearch(db="pubmed", term=filter_search, retmode="xml") as handle:
        pubmed_ids_filtered = Entrez.read(handle).get("IdList", [])

    if not pubmed_ids_filtered:
        return []

    with Entrez.efetch(db="pubmed", id=pubmed_ids_filtered, rettype="medline", retmode="xml") as handle:
        articles = Entrez.read(handle)

    abstracts = []
    for article in articles["PubmedArticle"]:
        if "Abstract" in article["MedlineCitation"]["Article"]:
            abstracts.append(
                {
                    "pmid": str(article["MedlineCitation"]["PMID"]),
                    "title": article["MedlineCitation"]["Article"]["ArticleTitle"],
                    "abstract": str(article["MedlineCitation"]["Article"]["Abstract"]["AbstractText"][0]),
                }
            )

    return abstracts

def get_summary_of_gene(gene_id):
    with Entrez.esearch(db="gene", term=gene_id, retmode="xml", sort="relevance") as handle:
        gene_ids = Entrez.read(handle).get("IdList", [])

    if not gene_ids:
        return ""

    with Entrez.esummary(db="gene", id=gene_ids[0]) as handle:
        result = Entrez.read(handle)

    return result["DocumentSummarySet"]["DocumentSummary"][0]["Summary"]
