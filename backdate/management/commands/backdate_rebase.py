from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand
from django.db.models import Q

from backdate.derive import registry
from backdate.models import Computation


class Command(BaseCommand):
    help = (
        "Mark results computed by an older version of a derivation stale, "
        "so the new code restates them."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("derivation")

    def handle(self, *args: Any, **opts: Any) -> None:
        d = registry.get(opts["derivation"])
        n = (
            Computation.objects.filter(derivation=d.name, status=Computation.Status.FRESH)
            .filter(~Q(code_version=d.version))
            .update(status=Computation.Status.STALE)
        )
        self.stdout.write(f"{n} results of {d.name} marked stale for version {d.version}")
