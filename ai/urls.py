from django.urls import path

from . import views

urlpatterns = [
    path("api/snp/<str:snpid>/abstracts",
         views.snp_summary_abstracts, name="snp_abstracts"),
    path("api/gene/<str:geneid>/abstracts",
         views.gene_summary_abstracts, name="gene_abstracts"),
]
