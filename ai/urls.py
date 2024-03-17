from django.urls import path

from . import views

urlpatterns = [
    path("snp/<str:snpid>", views.snp_page, name="snp"),
]
