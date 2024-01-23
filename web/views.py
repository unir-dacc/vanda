from django.core.handlers.asgi import HttpRequest
from django.shortcuts import render
from django.http import JsonResponse
from django.core.paginator import Paginator
import logging

from . import services

PAGE_SIZE = 20


def index(request):
    query = request.GET.get('q', None)

    response = []

    if query is not None:
        response = services.search_snp(query)

    paginator = Paginator(response, PAGE_SIZE)

    page_number = request.GET.get("page")
    logging.info(page_number)
    page_obj = paginator.get_page(page_number)

    return render(request, 'web/index.html', {"list_response": page_obj})


def snp_hgvs(request, snpid=None):
    snp = services.SnpData(snpid)

    data = {'hgvs': snp.get_snp_hgvs()}

    return JsonResponse(data)
