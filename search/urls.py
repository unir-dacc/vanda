
from django.urls import path

from . import views

urlpatterns = [
    path("search", views.search_view, name="search"),
    path("api/search", views.search_api, name="search_api"),
]
