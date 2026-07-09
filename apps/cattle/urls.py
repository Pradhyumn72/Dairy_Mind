from django.urls import path
from .views import AnimalListCreateView, AnimalDetailView, AnimalHistoryView

urlpatterns = [
    path("",              AnimalListCreateView.as_view(), name="animal-list-create"),
    path("<int:pk>/",     AnimalDetailView.as_view(),     name="animal-detail"),
    path("<int:pk>/history/", AnimalHistoryView.as_view(), name="animal-history"),
]
