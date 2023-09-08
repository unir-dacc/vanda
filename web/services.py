import requests
import logging


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


def get_snp_hgvs(snpid):
    url = f"https://api.ncbi.nlm.nih.gov/variation/v0/refsnp/{snpid[2:]}"

    response = requests.get(url)

    r = []

    if response.status_code == 200:
        r = response.json()
    else:
        logging.error(f"Resonse code on get_snp_data: {response.status_code}")

    return r["primary_snapshot_data"]["placements_with_allele"]
