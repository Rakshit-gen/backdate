from django.urls import path

from backdate.api import views

urlpatterns = [
    path("writes", views.write, name="write"),
    path("facts/<str:entity>/<str:attribute>", views.timeline, name="timeline"),
    path("facts/<str:entity>/<str:attribute>/history", views.history, name="history"),
    path("entities/<str:entity>", views.entity, name="entity"),
    path("changesets", views.changesets, name="changesets"),
    path("clock", views.clock, name="clock"),
    path("derivations", views.derivations, name="derivations"),
    path("computations", views.computations, name="computations"),
    path("computations/<int:computation_id>", views.computation, name="computation"),
    path("restatements", views.feed, name="feed"),
    path("graph", views.graph, name="graph"),
]
