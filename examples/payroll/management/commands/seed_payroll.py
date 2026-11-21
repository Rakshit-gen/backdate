from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from backdate.models import Tenant
from examples.payroll.seed import Plan, seed


class Command(BaseCommand):
    help = "Load a deterministic payroll dataset into a tenant and queue every month."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("tenant")
        parser.add_argument("--employees", type=int, default=50)
        parser.add_argument("--year", type=int, default=2024)
        parser.add_argument("--seed", type=int, default=7)

    def handle(self, *args: Any, **opts: Any) -> None:
        tenant = Tenant.objects.filter(slug=opts["tenant"]).first()
        if tenant is None:
            raise CommandError(f"no tenant {opts['tenant']!r}; run create_tenant first")
        keys = seed(tenant.id, Plan(opts["employees"], opts["year"], seed=opts["seed"]))
        self.stdout.write(f"seeded {opts['employees']} employees, queued {len(keys) * 2} results")
