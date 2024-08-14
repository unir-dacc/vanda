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

    if query is None:
        return JsonResponse({})

    response = []
    num_items = 0

    response = services.search_snp(query)
    num_items = response["num_items"]

    single_gene = request.GET.get("single_gene")
    multiple_genes = request.GET.get("multiple_genes")

    data = response["data"]

    snps = []
    for snp in data:
        snps.append(snp[0][2:])

    hgvs = []

    if snps:
        hgvs_data = services.SnpData(snps).get_snp_hgvs()

        for snp in hgvs_data:
            p = list(filter(lambda x: x[1:2] == "P", snp))
            c = list(filter(lambda x: x[1:2] == "C", snp))
            m = list(filter(lambda x: x[1:2] == "M", snp))

            hgvs.append([p, c, m])

    for i in range(len(data)):
        data[i][4] = data[i][4].split()
        data[i].append(hgvs[i])

    if single_gene:
        data = list(filter(lambda x: len(x[4]) == 1, data))
        num_items = len(data)

    if multiple_genes:
        data = list(filter(lambda x: len(x[4]) > 1, data))
        num_items = len(data)

    return {"search_response": data, "num_items": num_items}


def search_view(request):
    data = search(request)

    print(data)

    return render(request, 'web/search.html', data)


def search_api(request):
    data = search(request)

    return JsonResponse(data)


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
