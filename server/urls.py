from django.urls import include, path

from backdate.observability import health
from backdate.observability.exposition import metrics_view

urlpatterns = [
    path("healthz", health.live, name="healthz"),
    path("readyz", health.ready, name="readyz"),
    path("metrics", metrics_view, name="metrics"),
    path("v1/", include("backdate.api.urls")),
]
