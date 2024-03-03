from django.urls import path

from . import views

urlpatterns = [
    path("<str:snpid>", views.snp_page, name="snp")
]
