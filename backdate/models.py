"""Schema for bitemporal facts, changesets and derived results.

Two clocks matter here:

* valid time, a date range saying when a fact is true in the world, and
* knowledge time, a per-tenant version number saying when backdate learned it.

Versions come from ``TenantClock``. A writer holds the clock row lock until
it commits, so versions commit in order. That is what lets a reader treat
"every version up to N" as a stable snapshot.
"""

from __future__ import annotations

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import ArrayField, DateRangeField, RangeOperators
from django.contrib.postgres.indexes import GistIndex
from django.db import models
from django.db.models import BigIntegerField, F, Func, Q, TextField
from django.db.models.functions import Cast


class Tenant(models.Model):
    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.slug


class ApiKey(models.Model):
    """A bearer key of the form ``bk_<prefix>_<secret>``.

    Only a SHA-256 of the secret is stored. The prefix is unique and is used
    to find the row, then the hash is compared in constant time.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="api_keys")
    prefix = models.CharField(max_length=16, unique=True)
    secret_hash = models.CharField(max_length=64)
    scopes = ArrayField(models.CharField(max_length=32), default=list)
    label = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.tenant_id}:{self.prefix}"


class TenantClock(models.Model):
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, primary_key=True)
    version = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class Changeset(models.Model):
    """One committed write. Every fact row it touched carries its version."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    version = models.BigIntegerField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    actor = models.CharField(max_length=200, blank=True)
    reason = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "version"], name="changeset_version_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.tenant_id}@{self.version}"


class ChangeRange(models.Model):
    """The valid-time slice of one (entity, attribute) a changeset rewrote.

    Saves check these to find out whether something they read moved after
    the version they read at.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    changeset = models.ForeignKey(Changeset, on_delete=models.CASCADE, related_name="ranges")
    version = models.BigIntegerField()
    entity = models.CharField(max_length=200)
    attribute = models.CharField(max_length=100)
    valid = DateRangeField()

    class Meta:
        indexes = [
            GistIndex(
                fields=["tenant", "entity", "attribute", "valid"], name="changerange_lookup_gist"
            ),
            models.Index(fields=["tenant", "version"], name="changerange_version_idx"),
        ]


class Fact(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    entity = models.CharField(max_length=200)
    attribute = models.CharField(max_length=100)
    value = models.JSONField()
    valid = DateRangeField()
    tx_from = models.BigIntegerField()
    tx_to = models.BigIntegerField(null=True, blank=True)
    changeset = models.ForeignKey(Changeset, on_delete=models.PROTECT, related_name="facts")

    class Meta:
        constraints = [
            # The core invariant: among rows the system currently believes,
            # one (entity, attribute) never has two values on the same day.
            ExclusionConstraint(
                name="fact_current_no_overlap",
                index_type="gist",
                expressions=[
                    (F("tenant"), RangeOperators.EQUAL),
                    (F("entity"), RangeOperators.EQUAL),
                    (F("attribute"), RangeOperators.EQUAL),
                    (F("valid"), RangeOperators.OVERLAPS),
                ],
                condition=Q(tx_to__isnull=True),
            ),
            models.CheckConstraint(
                condition=Q(tx_to__isnull=True) | Q(tx_to__gt=F("tx_from")),
                name="fact_tx_order",
            ),
            models.CheckConstraint(
                condition=Q(valid__isempty=False) & Q(valid__lower_inf=False),
                name="fact_valid_bounded_below",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "entity", "attribute", "tx_from"], name="fact_history_idx"
            ),
        ]


class Computation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        FRESH = "fresh"
        STALE = "stale"
        FAILED = "failed"

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    derivation = models.CharField(max_length=100)
    key = models.CharField(max_length=300)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # Version string of the derivation code that produced the stored result.
    code_version = models.CharField(max_length=40, blank=True)

    result = models.JSONField(null=True, blank=True)
    # Fact version the stored result was computed at.
    result_version = models.BigIntegerField(null=True, blank=True)
    # Bumped every time the stored result changes. Dependents remember the
    # seq they read and their save fails if it moved.
    result_seq = models.IntegerField(default=0)
    stale_since_version = models.BigIntegerField(null=True, blank=True)

    attempts = models.IntegerField(default=0)
    not_before = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)

    lease_owner = models.CharField(max_length=100, blank=True)
    # Fencing token. Each claim increments it, and a save only lands if the
    # token it was claimed with is still current.
    lease_token = models.BigIntegerField(default=0)
    lease_expires_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "derivation", "key"], name="computation_identity"
            ),
            models.CheckConstraint(
                condition=~Q(status="fresh") | Q(result_version__isnull=False),
                name="computation_fresh_has_version",
            ),
        ]
        indexes = [
            models.Index(
                fields=["not_before", "id"],
                condition=Q(status__in=["pending", "stale"]),
                name="computation_runnable_idx",
            ),
            models.Index(
                fields=["tenant"],
                condition=Q(status__in=["pending", "stale"]),
                name="computation_backlog_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.derivation}({self.key})"


class ReadRange(models.Model):
    """A slice of fact history a computation looked at when it last ran."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    computation = models.ForeignKey(Computation, on_delete=models.CASCADE, related_name="reads")
    entity = models.CharField(max_length=200)
    attribute = models.CharField(max_length=100)
    valid = DateRangeField()

    class Meta:
        indexes = [
            GistIndex(fields=["tenant", "entity", "attribute", "valid"], name="readrange_gist"),
        ]


class DerivedRead(models.Model):
    """A computation that used another computation's result."""

    reader = models.ForeignKey(Computation, on_delete=models.CASCADE, related_name="derived_reads")
    source = models.ForeignKey(Computation, on_delete=models.CASCADE, related_name="dependents")
    observed_seq = models.IntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["reader", "source"], name="derivedread_unique"),
        ]


def current_txid() -> Cast:
    # xid8 has no direct cast to bigint, so go through text.
    return Cast(
        Cast(Func(function="pg_current_xact_id", output_field=TextField()), TextField()),
        BigIntegerField(),
    )


class Restatement(models.Model):
    """Append-only record of a derived result changing.

    seq 1 is the first statement of a result. Later rows are corrections,
    with ``delta`` holding new minus old for numeric fields. Summing deltas
    over all rows of a computation gives its current result.
    """

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    computation = models.ForeignKey(
        Computation, on_delete=models.CASCADE, related_name="restatements"
    )
    seq = models.IntegerField()
    from_version = models.BigIntegerField(null=True, blank=True)
    to_version = models.BigIntegerField()
    previous = models.JSONField(null=True, blank=True)
    current = models.JSONField()
    delta = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    # Transaction id of the writer, used to page the feed in commit-safe order.
    txid = models.BigIntegerField(db_default=current_txid())

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["computation", "seq"], name="restatement_seq_unique"),
        ]
        indexes = [
            models.Index(fields=["tenant", "txid", "id"], name="restatement_feed_idx"),
        ]


class IdempotencyRecord(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    key = models.CharField(max_length=200)
    request_hash = models.CharField(max_length=64)
    status_code = models.IntegerField()
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"], name="idempotency_unique"),
        ]
        indexes = [models.Index(fields=["created_at"], name="idempotency_created_idx")]
