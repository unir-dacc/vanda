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

    if query is not None:
        response = services.search_snp(query)

    if len(response["data"]) > 0:
        if query.upper() == response["data"][0][4].upper():
            return redirect(f'gene/{query.upper()}')

    paginator = Paginator(response["data"], PAGE_SIZE)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    for snp in page_obj:
        snp[4] = snp[4].split()
        snp_data = services.SnpData(snp[0][2:])
        snp.append(snp_data.get_snp_hgvs())

    return render(request,
                  'web/search.html',
                  {"list_response": page_obj,
                   "num_items": response["num_items"]})


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
