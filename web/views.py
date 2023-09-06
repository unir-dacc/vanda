from django.shortcuts import render
from . import services


def index(request):
    query = request.GET.get('q', None)

    response = []

    if query is not None:
        response = services.get_by_name(query)

    return render(request, 'web/index.html', {"list_response": response})
