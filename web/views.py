from django.core.handlers.asgi import HttpRequest
from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.core.paginator import Paginator

from . import services

PAGE_SIZE = 20


def index(request):
    return render(request, 'web/index.html')


def search(request):
    query = request.GET.get('q', None)

    response = []
    num_items = 0

    if query is not None:
        response = services.search_snp(query)
        num_items = response["num_items"]

    if len(response["data"]) > 0:
        if query.upper() == response["data"][0][4].upper():
            return redirect(f'gene/{query.upper()}')

    single_gene = request.GET.get("single_gene")
    multiple_genes = request.GET.get("multiple_genes")

    data = response["data"]

    snps = []
    for snp in data:
        snps.append(snp[0][2:])

    hgvs = []

    if snps:
        hgvs = services.SnpData(snps).get_snp_hgvs()

    for i in range(len(data)):
        data[i][4] = data[i][4].split()
        data[i].append(hgvs[i])

    if single_gene:
        data = list(filter(lambda x: len(x[4]) == 1, data))
        num_items = len(data)

    if multiple_genes:
        data = list(filter(lambda x: len(x[4]) > 1, data))
        num_items = len(data)

    paginator = Paginator(data, PAGE_SIZE)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, 'web/search.html', {"list_response": page_obj, "num_items": num_items})


def gene_abstracts(request, geneid=None):

    abstracts = services.get_abstracts_by_gene(geneid)

    return JsonResponse({"articles": abstracts})


def snp_abstracts(request, snpid=None):
    abstracts = services.get_abstracts_by_snp(snpid)

    return JsonResponse({"articles": abstracts})


def snp_hgvs(request, snpid=None):
    snp = services.SnpData(snpid)

    data = {'hgvs': snp.get_snp_hgvs()}

    return JsonResponse(data)
