from django.urls import path

from . import views

urlpatterns = [
    path("snp/<str:snpid>", views.snp_page, name="snp"),
    path("api/snp/<str:snpid>", views.snp_page, name="snp"),
    path("gene/<str:geneid>", views.gene_page, name="snp"),
    path("api/gene/<str:geneid>", views.gene_page, name="snp"),
]
