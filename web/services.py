import requests
import logging
from Bio import Entrez

Entrez.email = "example@example.org"


def search_snp(query):
    url = f"https://clinicaltables.nlm.nih.gov/api/snps/v3/search?terms={query}&maxList=500"
    response = requests.get(url)

    r = []
    if response.status_code == 200:
        r = response.json()
    else:
        logging.error(
            f"Resonse code on services.search_snp: {response.status_code}")

    return r[3]


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
