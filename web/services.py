import requests
import logging
import os
from Bio import Entrez
from dotenv import load_dotenv

load_dotenv()

Entrez.email = os.getenv("EMAIL")


def search_snp(query):
    url = f"https://clinicaltables.nlm.nih.gov/api/snps/v3/search?terms={query}&maxList=500"
    response = requests.get(url)

    r = []
    if response.status_code == 200:
        r = response.json()
    else:
        logging.error(
            f"Resonse code on services.search_snp: {response.status_code}")

    return {"num_items": r[0], "data": r[3]}


class SnpData:
    def __init__(self, snpid):
        self.snpid = snpid

        result = ''

        with Entrez.esummary(db="snp", id=snpid) as handle:
            result = Entrez.read(handle)

        self.data = result

    def get_snp_hgvs(self):
        hgvs = self.data["DocumentSummarySet"]['DocumentSummary'][0]['DOCSUM'][5:].split("|")[
            0].split(',')

        return hgvs


keywords = ["Metabolism", "Nutrients", "Micronutrients",
            "Obesity", "Hypertriglyceridaemia"]


def get_abstracts_by_gene(geneid):
    term = f"{geneid.upper()} AND (snp_pubmed_cited[Filter] OR snp_pubmed[Filter])"
    abstracts = []

    with Entrez.esearch(db="snp", term=term, retmode="xml") as handle:
        snp_ids = Entrez.read(handle)["IdList"]

    pubmed_ids = []
    with Entrez.elink(dbfrom="snp", db="pubmed", id=snp_ids, retmode="xml") as handle:
        pubmed_ids = Entrez.read(handle)

    ids = []
    snp_to_pubmed = {}

    for i in pubmed_ids:
        for j in i["LinkSetDb"]:
            for id in j["Link"]:
                ids.append(id["Id"])
                if i["IdList"][0] in snp_to_pubmed:
                    snp_to_pubmed[i["IdList"][0]].append(id["Id"])
                else:
                    snp_to_pubmed[i["IdList"][0]] = []
                    snp_to_pubmed[i["IdList"][0]].append(id["Id"])

    filter_term = f'({" OR ".join(ids)}) AND ({" OR ".join(keywords)})'

    with Entrez.esearch(db="pubmed", term=filter_term, retmode="xml") as handle:
        pubmed_ids = Entrez.read(handle)["IdList"]

    articles = []
    with Entrez.efetch(db="pubmed", id=ids, rettype="medline", retmode="xml") as handle:
        articles = Entrez.read(handle)

    abstracts = []

    for article in articles['PubmedArticle']:
        if "Abstract" in article["MedlineCitation"]["Article"]:
            abstracts.append({
                "pmid": str(article["MedlineCitation"]["PMID"]),
                "title": article["MedlineCitation"]["Article"]["ArticleTitle"],
                "abstract": str(article["MedlineCitation"]["Article"]
                                ["Abstract"]["AbstractText"][0])

            })

    return abstracts, snp_to_pubmed


def get_summary_of_gene(geneid):
    gene_ids = []

    with Entrez.esearch(db="gene", term=geneid, retmode="xml", sort="relevance") as handle:
        gene_ids = Entrez.read(handle)["IdList"]

    result = ''

    with Entrez.esummary(db="gene", id=gene_ids[0]) as handle:
        result = Entrez.read(handle)

    result = result["DocumentSummarySet"]["DocumentSummary"][0]["Summary"]

    return result


def get_abstracts_by_snp(snpid):
    article_ids = []

    with Entrez.elink(dbfrom="snp", db="pubmed", id=snpid, retmode="xml") as handle:
        pubmed_ids = Entrez.read(handle)

    ids = []

    for i in pubmed_ids:
        for j in i["LinkSetDb"]:
            for id in j["Link"]:
                ids.append(id["Id"])

    filter_term = f'({" OR ".join(ids)}) AND ({" OR ".join(keywords)})'

    with Entrez.esearch(db="pubmed", term=filter_term, retmode="xml") as handle:
        pubmed_ids = Entrez.read(handle)["IdList"]

    articles = []
    with Entrez.efetch(db="pubmed", id=pubmed_ids, retmode="xml") as handle:
        articles = Entrez.read(handle)

    abstracts = []

    for article in articles['PubmedArticle']:
        if "Abstract" in article["MedlineCitation"]["Article"]:
            abstracts.append({
                "pmid": str(article["MedlineCitation"]["PMID"]),
                "title": article["MedlineCitation"]["Article"]["ArticleTitle"],
                "abstract": str(article["MedlineCitation"]["Article"]
                                ["Abstract"]["AbstractText"][0])

            })

    return abstracts
