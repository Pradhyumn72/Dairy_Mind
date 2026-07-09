from django.urls import path
from .views import FeedLogListCreateView, ROIView, LowPerformersView, FarmConfigView

urlpatterns = [
    path("feed-entries/",    FeedLogListCreateView.as_view(), name="feed-log-list-create"),
    path("roi/",             ROIView.as_view(),               name="costs-roi"),
    path("low-performers/",  LowPerformersView.as_view(),     name="costs-low-performers"),
    path("config/",          FarmConfigView.as_view(),        name="costs-config"),
]
