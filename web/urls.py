from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("search", views.search_view, name="search"),
    path("api/search", views.search_api, name="search_api"),
    path("api/snp/<str:snpid>/hgvs", views.snp_hgvs, name="snp_hgvs"),
    path("api/snp/<str:snpid>/abstracts",
         views.snp_abstracts, name="snp_abstracts"),
    path("api/gene/<str:geneid>/abstracts",
         views.gene_abstracts, name="gene_abstracts"),
     path("about", views.about, name="about"),
]
