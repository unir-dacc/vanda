from django.shortcuts import render
from . import services

def index(request):
	query = request.GET.get('q', None)

	r = services.get_by_name(query)

	return render(request, 'web/index.html', {"list_response": r})
