from datetime import date

import pytest
from django.db import IntegrityError, transaction

from backdate import reads, writes
from backdate.intervals import Span
from backdate.models import ChangeRange, Changeset, Fact
from backdate.writes import Assert, Retract

D = date
pytestmark = pytest.mark.django_db


def salary(tenant, start, end, cents, **kw):
    span = Span(start, end)
    return writes.apply(tenant.id, [Assert("employee:1", "salary", span, cents)], **kw)


def test_first_write_gets_version_one(tenant):
    result = salary(tenant, D(2024, 1, 1), None, 100)
    assert result.version == 1
    assert not result.noop
    assert reads.value_at(tenant.id, "employee:1", "salary", D(2030, 1, 1)) == 100


def test_noop_write_spends_no_version(tenant):
    salary(tenant, D(2024, 1, 1), None, 100)
    again = salary(tenant, D(2024, 3, 1), D(2024, 4, 1), 100)
    assert again.noop
    assert again.version == 1
    assert Changeset.objects.filter(tenant=tenant).count() == 1


def test_backdated_raise_keeps_old_knowledge(tenant):
    salary(tenant, D(2024, 1, 1), None, 100)
    salary(tenant, D(2024, 3, 1), None, 120)
    feb = D(2024, 2, 15)
    apr = D(2024, 4, 15)
    assert reads.value_at(tenant.id, "employee:1", "salary", apr) == 120
    assert reads.value_at(tenant.id, "employee:1", "salary", apr, version=1) == 100
    assert reads.value_at(tenant.id, "employee:1", "salary", feb) == 100


def test_only_changed_rows_are_closed(tenant):
    salary(tenant, D(2024, 1, 1), D(2024, 6, 1), 100)
    salary(tenant, D(2024, 6, 1), None, 200)
    salary(tenant, D(2024, 8, 1), None, 250)
    first = Fact.objects.get(tenant=tenant, tx_from=1)
    assert first.tx_to is None, "the January row did not change and should stay open"


def test_change_ranges_cover_only_differences(tenant):
    salary(tenant, D(2024, 1, 1), None, 100)
    salary(tenant, D(2024, 1, 1), D(2024, 6, 1), 100)  # no-op
    salary(tenant, D(2024, 1, 1), D(2024, 6, 1), 110)
    ranges = list(ChangeRange.objects.filter(tenant=tenant, version=2))
    assert [Span.from_range(r.valid) for r in ranges] == [Span(D(2024, 1, 1), D(2024, 6, 1))]


def test_retract_leaves_a_gap(tenant):
    salary(tenant, D(2024, 1, 1), None, 100)
    writes.apply(tenant.id, [Retract("employee:1", "salary", Span(D(2024, 2, 1), D(2024, 3, 1)))])
    pieces = reads.timeline(tenant.id, "employee:1", "salary")
    assert [(str(p.span), p.value) for p in pieces] == [
        ("[2024-01-01, 2024-02-01)", 100),
        ("[2024-03-01, ∞)", 100),
    ]


def test_several_ops_on_one_attribute_apply_in_order(tenant):
    span = Span(D(2024, 1, 1))
    result = writes.apply(
        tenant.id,
        [Assert("e", "a", span, 1), Assert("e", "a", Span(D(2024, 5, 1)), 2)],
    )
    assert result.version == 1
    assert reads.value_at(tenant.id, "e", "a", D(2024, 6, 1)) == 2


def test_json_values_compare_structurally(tenant):
    span = Span(D(2024, 1, 1))
    writes.apply(tenant.id, [Assert("e", "addr", span, {"city": "Pune", "zip": "411001"})])
    again = writes.apply(tenant.id, [Assert("e", "addr", span, {"zip": "411001", "city": "Pune"})])
    assert again.noop


def test_exclusion_constraint_blocks_overlapping_current_rows(tenant):
    salary(tenant, D(2024, 1, 1), None, 100)
    cs = Changeset.objects.get(tenant=tenant)
    with pytest.raises(IntegrityError), transaction.atomic():
        Fact.objects.create(
            tenant=tenant,
            entity="employee:1",
            attribute="salary",
            value=1,
            valid=Span(D(2024, 5, 1), D(2024, 6, 1)).to_range(),
            tx_from=9,
            changeset=cs,
        )


def test_tenants_do_not_see_each_other(tenant, other_tenant):
    salary(tenant, D(2024, 1, 1), None, 100)
    assert reads.value_at(other_tenant.id, "employee:1", "salary", D(2024, 2, 1)) is None
    assert (
        writes.apply(
            other_tenant.id, [Assert("employee:1", "salary", Span(D(2024, 1, 1)), 5)]
        ).version
        == 1
    )


def test_rejects_empty_write(tenant):
    with pytest.raises(writes.WriteError):
        writes.apply(tenant.id, [])


def test_rejects_too_many_ops(tenant, settings):
    settings.BACKDATE = {**settings.BACKDATE, "MAX_OPS_PER_CHANGESET": 2}
    ops = [Assert("e", f"a{i}", Span(D(2024, 1, 1)), i) for i in range(3)]
    with pytest.raises(writes.WriteError):
        writes.apply(tenant.id, ops)


def test_history_keeps_superseded_rows(tenant):
    salary(tenant, D(2024, 1, 1), None, 100)
    salary(tenant, D(2024, 1, 1), None, 105)
    rows = reads.history(tenant.id, "employee:1", "salary")
    assert [(r.value, r.tx_from, r.tx_to) for r in rows] == [(100, 1, 2), (105, 2, None)]
