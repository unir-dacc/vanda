from django.shortcuts import render

import requests


def index(request):
    query = request.GET.get('q', None)

    url = f"https://clinicaltables.nlm.nih.gov/api/snps/v3/search?terms={query}"
    response = requests.get(url)

    r = []
    if response.status_code == 200:
        r = response.json()
    else:
        print(f"Resonse code: {response.status_code}")

    context = {"search_list": r[3]}

    return render(request, 'web/index.html', context)
