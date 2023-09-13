import requests
import logging
from django.core.cache import cache


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

        url = f"https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/{snpid[2:]}"

        snp_data = cache.get(snpid, None)

        if snp_data == None:
            response = requests.get(url)

            if response.status_code == 200:
                snp_data = response.json()
                cache.set(snpid, snp_data)
            else:
                logging.error(
                    f"Resonse code on get_snp_data: {response.status_code}")

        self.data = snp_data

    def get_snp_hgvs(self):
        snp_data = self.data["primary_snapshot_data"]["placements_with_allele"]

        hgvs = []

        for item in snp_data:
            for allele in item["alleles"]:
                hgvs.append(allele["hgvs"])

        return hgvs
