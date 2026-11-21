from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from backdate.api import keys
from backdate.models import Tenant, TenantClock


class Command(BaseCommand):
    help = "Create a tenant (if missing) and print a new API key for it."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("slug")
        parser.add_argument("--name", default="")
        parser.add_argument("--scopes", default="read,write,compute")
        parser.add_argument("--label", default="")

    def handle(self, *args: Any, **opts: Any) -> None:
        scopes = [s for s in opts["scopes"].split(",") if s]
        with transaction.atomic():
            tenant, _ = Tenant.objects.get_or_create(
                slug=opts["slug"], defaults={"name": opts["name"] or opts["slug"]}
            )
            TenantClock.objects.get_or_create(tenant=tenant)
            try:
                _, token = keys.issue(tenant, scopes, opts["label"])
            except ValueError as exc:
                raise CommandError(str(exc)) from None
        # The only time the key is ever shown.
        self.stdout.write(token)
