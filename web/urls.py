from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/snp/<str:snpid>/hgvs", views.snp_hgvs, name="snp_hgvs"),
]
