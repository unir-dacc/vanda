from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("snp/<str:snpid>", views.snp_popover, name="snp_popover"),
]
