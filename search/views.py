import os
import re
from django.core.paginator import Paginator
from django.shortcuts import render, redirect
from django.http import JsonResponse
from Bio import Entrez
from dotenv import load_dotenv
import entrez.services as ncbi

load_dotenv()
Entrez.email = os.getenv("EMAIL")

def search(request):
    query = request.GET.get("q", None)
    page = int(request.GET.get("page", 1))
    per_page = int(request.GET.get("per_page", 10))

    if not query:
        return JsonResponse({})

    response = ncbi.search_snp(query, page=page, max_results=per_page)
    num_items = response.get("num_items", 0)
    data = response.get("data", [])

    paginator = Paginator(data, per_page)
    current_page = paginator.get_page(page)

    snps = [snp[0][2:] for snp in current_page]
    hgvs = []

    if snps:
        hgvs_data = ncbi.SnpData(snps).get_snp_hgvs()
        for snp in hgvs_data:
            p = [x for x in snp if x[1:2] == "P"]
            c = [x for x in snp if x[1:2] == "C"]
            m = [x for x in snp if x[1:2] == "M"]
            hgvs.append([p, c, m])

    for i, snp_data in enumerate(current_page):
        snp_data[4] = snp_data[4].split()
        snp_data.append(hgvs[i])

        protein_matches = re.findall(r"(?P<id>\w+_\d+\.\d+):p\.(?P<mut>\w+\d+\w+)", " ".join(hgvs[i][0]) if hgvs[i][0] else "")
        genomic_matches = re.findall(r"(?P<id>\w+_\d+\.\d+):g\.(?P<mut>\d+\w+>\w+)", " ".join(hgvs[i][1]) if hgvs[i][1] else "")
        mrna_matches = re.findall(r"(?P<id>\w+_\d+\.\d+):c\.(?P<mut>\d+\w+>\w+)", " ".join(hgvs[i][2]) if hgvs[i][2] else "")

        snp_data.append({
            "proteins": [{"id": p[0], "mutation": p[1]} for p in protein_matches],
            "genomics": [{"id": g[0], "mutation": g[1]} for g in genomic_matches],
            "mrnas": [{"id": m[0], "mutation": m[1]} for m in mrna_matches],
        })

    for snp in current_page:
        snp.append(ncbi.fetch_pubmed_articles_by_snp(snp[0]))

    single_gene = request.GET.get("single_gene")
    multiple_genes = request.GET.get("multiple_genes")

    if single_gene:
        data = [x for x in current_page if len(x[4]) == 1]
        num_items = len(data)
    if multiple_genes:
        data = [x for x in current_page if len(x[4]) > 1]
        num_items = len(data)

    return {"search_response": data, "num_items": num_items, "page": page, "total_pages": paginator.num_pages}

def search_view(request):
    query = request.GET.get("q", None)
    data = search(request)
    snps_related = data.get("search_response", [])

    if snps_related and query.upper() in snps_related[0][4]:
        return redirect(f"gene/{query.upper()}")

    return render(request, "web/search.html", data)

def search_api(request):
    data = search(request)
    return JsonResponse(data)

