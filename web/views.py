from django.shortcuts import render

PAGE_SIZE = 20


def index(request):
    return render(request, "web/index.html")

def about(request):
    return render(request, "web/about.html")
