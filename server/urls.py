from django.urls import path

from backdate.observability import health

urlpatterns = [
    path("healthz", health.live),
    path("readyz", health.ready),
]
