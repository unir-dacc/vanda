from django.core.handlers.asgi import HttpRequest
from django.shortcuts import render
from django.http import JsonResponse

from . import services


def index(request):
    query = request.GET.get('q', None)

    response = []

    if query is not None:
        response = services.search_snp(query)

    return render(request, 'web/index.html', {"list_response": response})


def snp_popover(request, snpid=None):
    data = {'content': services.get_snp_hgvs(snpid)}

    return JsonResponse(data)
