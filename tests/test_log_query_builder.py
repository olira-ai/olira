"""Unit tests for LogQuery / AsyncLogQuery builder (mocked transport, no network)."""

import pytest

from olira import AsyncLogQuery, F, LogQuery, LogQueryResult, ValidationError
from olira.log_query import _OPS

# ---------------------------------------------------------------------------
# Mock transports
# ---------------------------------------------------------------------------


class MockTransport:
    def __init__(self, rows=None, count=0, total_count=None):
        self._rows = rows or []
        self._count = count
        self._total_count = total_count
        self.last_patient_id: str | None = None
        self.last_body: dict = {}
        self.last_endpoint: str | None = None

    def _make_result(self, body: dict) -> LogQueryResult:
        if body.get("include_total") and self._total_count is not None:
            offset = body.get("offset", 0)
            has_more = (offset + len(self._rows)) < self._total_count
            return LogQueryResult(
                count=self._count, rows=self._rows,
                total_count=self._total_count, has_more=has_more,
            )
        return LogQueryResult(count=self._count, rows=self._rows)

    def query_logs(self, patient_id: str, body: dict) -> LogQueryResult:
        self.last_patient_id = patient_id
        self.last_body = body
        self.last_endpoint = f"/v1/state/{patient_id}/logs/query"
        return self._make_result(body)

    def query_population_logs(self, body: dict) -> LogQueryResult:
        self.last_body = body
        self.last_endpoint = "/v1/state/logs/query"
        return self._make_result(body)


class MockAsyncTransport:
    def __init__(self, rows=None, count=0, total_count=None):
        self._rows = rows or []
        self._count = count
        self._total_count = total_count
        self.last_patient_id: str | None = None
        self.last_body: dict = {}
        self.last_endpoint: str | None = None

    def _make_result(self, body: dict) -> LogQueryResult:
        if body.get("include_total") and self._total_count is not None:
            offset = body.get("offset", 0)
            has_more = (offset + len(self._rows)) < self._total_count
            return LogQueryResult(
                count=self._count, rows=self._rows,
                total_count=self._total_count, has_more=has_more,
            )
        return LogQueryResult(count=self._count, rows=self._rows)

    async def query_logs(self, patient_id: str, body: dict) -> LogQueryResult:
        self.last_patient_id = patient_id
        self.last_body = body
        self.last_endpoint = f"/v1/state/{patient_id}/logs/query"
        return self._make_result(body)

    async def query_population_logs(self, body: dict) -> LogQueryResult:
        self.last_body = body
        self.last_endpoint = "/v1/state/logs/query"
        return self._make_result(body)


# ---------------------------------------------------------------------------
# Spec compilation — filters
# ---------------------------------------------------------------------------


def test_eq_appends_filter_node():
    t = MockTransport()
    LogQuery(t, patient_id="p1").eq("type", "health_metric_reported").execute()
    assert t.last_body["filter"] == [{"field": "type", "op": "eq", "value": "health_metric_reported"}]


def test_multiple_filters_chain():
    t = MockTransport()
    LogQuery(t, patient_id="p1").gt("payload.score", 5).lt("payload.score", 10).execute()
    assert len(t.last_body["filter"]) == 2
    assert t.last_body["filter"][0] == {"field": "payload.score", "op": "gt", "value": 5}
    assert t.last_body["filter"][1] == {"field": "payload.score", "op": "lt", "value": 10}


def test_in_coerces_to_list():
    t = MockTransport()
    LogQuery(t, patient_id="p1").in_("type", ("a", "b", "c")).execute()
    assert t.last_body["filter"][0]["value"] == ["a", "b", "c"]


def test_nin():
    t = MockTransport()
    LogQuery(t, patient_id="p1").nin("type", ["x"]).execute()
    assert t.last_body["filter"][0] == {"field": "type", "op": "nin", "value": ["x"]}


def test_all_scalar_operators():
    ops_methods = {
        "neq": lambda q: q.neq("f", 1),
        "gte": lambda q: q.gte("f", 1),
        "lte": lambda q: q.lte("f", 1),
        "like": lambda q: q.like("f", "%x%"),
        "ilike": lambda q: q.ilike("f", "%x%"),
        "is": lambda q: q.is_("f", None),
        "exists": lambda q: q.exists("f", True),
        "contains": lambda q: q.contains("f", "val"),
    }
    for op, method in ops_methods.items():
        t = MockTransport()
        method(LogQuery(t, patient_id="p")).execute()
        assert t.last_body["filter"][0]["op"] == op


def test_unknown_operator_raises_validation_error():
    t = MockTransport()
    with pytest.raises(ValidationError, match="unknown operator"):
        LogQuery(t, patient_id="p1").filter("type", "regex", ".*").execute()


# ---------------------------------------------------------------------------
# Spec compilation — boolean groups
# ---------------------------------------------------------------------------


def test_or_with_F_expressions():
    t = MockTransport()
    LogQuery(t, patient_id="p1").or_(F("payload.score").gt(6), F("type").eq("mood")).execute()
    assert t.last_body["filter"] == [
        {
            "or": [
                {"field": "payload.score", "op": "gt", "value": 6},
                {"field": "type", "op": "eq", "value": "mood"},
            ]
        }
    ]


def test_and_group():
    t = MockTransport()
    LogQuery(t, patient_id="p1").and_(F("type").eq("a"), F("type").eq("b")).execute()
    node = t.last_body["filter"][0]
    assert "and" in node
    assert len(node["and"]) == 2


def test_F_all_operators():
    f = F("payload.x")
    assert f.neq(1)["op"] == "neq"
    assert f.gte(1)["op"] == "gte"
    assert f.lte(1)["op"] == "lte"
    assert f.in_(["a"])["op"] == "in"
    assert f.nin(["a"])["op"] == "nin"
    assert f.like("%x")["op"] == "like"
    assert f.ilike("%x")["op"] == "ilike"
    assert f.is_(None)["op"] == "is"
    assert f.exists()["op"] == "exists"
    assert f.contains("v")["op"] == "contains"


# ---------------------------------------------------------------------------
# Spec compilation — projection
# ---------------------------------------------------------------------------


def test_select_positional():
    t = MockTransport()
    LogQuery(t, patient_id="p1").select("timestamp", "type").execute()
    assert t.last_body["select"] == [{"path": "timestamp"}, {"path": "type"}]


def test_select_aliases():
    t = MockTransport()
    LogQuery(t, patient_id="p1").select(severity="payload.score").execute()
    assert t.last_body["select"] == [{"path": "payload.score", "alias": "severity"}]


def test_select_mixed():
    t = MockTransport()
    LogQuery(t, patient_id="p1").select("timestamp", score="payload.score").execute()
    sel = t.last_body["select"]
    assert {"path": "timestamp"} in sel
    assert {"path": "payload.score", "alias": "score"} in sel


def test_select_array_shape():
    t = MockTransport()
    LogQuery(t, patient_id="p1").select_array(
        "payload.items", where=F("payload.items").gt(0), element="name", first=True, alias="first_item"
    ).execute()
    node = t.last_body["select"][0]
    assert node["path"] == "payload.items"
    assert node["first"] is True
    assert node["alias"] == "first_item"
    assert node["element"] == "name"
    assert "where" in node


# ---------------------------------------------------------------------------
# Spec compilation — modifiers
# ---------------------------------------------------------------------------


def test_order():
    t = MockTransport()
    LogQuery(t, patient_id="p1").order("timestamp", desc=True).execute()
    assert t.last_body["order"] == [{"field": "timestamp", "desc": True}]


def test_limit_and_offset():
    t = MockTransport()
    LogQuery(t, patient_id="p1").limit(10).offset(20).execute()
    assert t.last_body["limit"] == 10
    assert t.last_body["offset"] == 20


def test_range_sets_offset_and_limit():
    t = MockTransport()
    LogQuery(t, patient_id="p1").range(10, 19).execute()
    assert t.last_body["offset"] == 10
    assert t.last_body["limit"] == 10  # 19 - 10 + 1 = 10


# ---------------------------------------------------------------------------
# Spec compilation — aggregations
# ---------------------------------------------------------------------------


def test_group_by_and_avg():
    t = MockTransport()
    LogQuery(t, patient_id="p1").group_by("type").avg("payload.score", "avg_score").execute()
    assert t.last_body["group_by"] == ["type"]
    assert t.last_body["aggregations"] == [{"op": "avg", "field": "payload.score", "alias": "avg_score"}]


def test_count_agg():
    t = MockTransport()
    LogQuery(t, patient_id="p1").group_by("type").count_agg("n").execute()
    assert t.last_body["aggregations"] == [{"op": "count", "alias": "n"}]


def test_sum_min_max():
    for op_method, op_name in [("sum", "sum"), ("min", "min"), ("max", "max")]:
        t = MockTransport()
        getattr(LogQuery(t, patient_id="p"), op_method)("payload.x", "result").execute()
        assert t.last_body["aggregations"][0]["op"] == op_name


# ---------------------------------------------------------------------------
# Endpoint routing
# ---------------------------------------------------------------------------


def test_single_patient_posts_to_correct_endpoint():
    t = MockTransport()
    LogQuery(t, patient_id="abc").execute()
    assert t.last_endpoint == "/v1/state/abc/logs/query"
    assert t.last_patient_id == "abc"


def test_population_posts_to_org_endpoint():
    t = MockTransport()
    LogQuery(t, patient_ids=["p1", "p2"], population=True).execute()
    assert t.last_endpoint == "/v1/state/logs/query"
    assert t.last_body.get("patient_ids") == ["p1", "p2"]


def test_population_without_ids_omits_patient_ids():
    t = MockTransport()
    LogQuery(t, population=True).execute()
    assert "patient_ids" not in t.last_body


# ---------------------------------------------------------------------------
# Terminals
# ---------------------------------------------------------------------------


def test_execute_returns_log_query_result():
    t = MockTransport(rows=[{"id": "1", "type": "t"}], count=1)
    result = LogQuery(t, patient_id="p1").execute()
    assert isinstance(result, LogQueryResult)
    assert result.count == 1
    assert result[0]["id"] == "1"


def test_count_terminal_sets_count_true_and_returns_int():
    t = MockTransport(count=42)
    n = LogQuery(t, patient_id="p1").count()
    assert n == 42
    assert t.last_body.get("count") is True


def test_single_raises_when_zero_rows():
    t = MockTransport(rows=[], count=0)
    with pytest.raises(ValidationError, match="expected exactly one row"):
        LogQuery(t, patient_id="p1").single()


def test_single_raises_when_two_rows():
    t = MockTransport(rows=[{"id": "1"}, {"id": "2"}], count=2)
    with pytest.raises(ValidationError, match="expected exactly one row"):
        LogQuery(t, patient_id="p1").single()


def test_single_returns_dict_for_one_row():
    t = MockTransport(rows=[{"id": "42"}], count=1)
    row = LogQuery(t, patient_id="p1").single()
    assert row["id"] == "42"
    assert t.last_body["limit"] == 2


def test_single_respects_caller_limit():
    # .limit(1) set before .single() — must not be overridden to 2
    t = MockTransport(rows=[{"id": "1"}], count=1)
    LogQuery(t, patient_id="p1").limit(1).single()
    assert t.last_body["limit"] == 1


def test_maybe_single_returns_none_for_empty():
    t = MockTransport(rows=[], count=0)
    assert LogQuery(t, patient_id="p1").maybe_single() is None


def test_maybe_single_raises_for_two_rows():
    t = MockTransport(rows=[{"id": "1"}, {"id": "2"}], count=2)
    with pytest.raises(ValidationError, match="expected at most one row"):
        LogQuery(t, patient_id="p1").maybe_single()


def test_maybe_single_respects_caller_limit():
    # .limit(1) set before .maybe_single() — only 1 row returned, no raise
    t = MockTransport(rows=[{"id": "1"}], count=1)
    row = LogQuery(t, patient_id="p1").limit(1).maybe_single()
    assert row == {"id": "1"}
    assert t.last_body["limit"] == 1


# ---------------------------------------------------------------------------
# LogQueryResult protocol
# ---------------------------------------------------------------------------


def test_result_is_iterable_and_indexable():
    result = LogQueryResult(count=2, rows=[{"a": 1}, {"a": 2}])
    assert list(result) == [{"a": 1}, {"a": 2}]
    assert len(result) == 2
    assert result[0] == {"a": 1}


def test_as_logs_parses_into_log_entries():
    from olira import LogEntry

    result = LogQueryResult(
        count=1, rows=[{"id": "x", "type": "health_metric_reported", "timestamp": "2026-01-01T00:00:00Z", "payload": {}}]
    )
    entries = result.as_logs()
    assert len(entries) == 1
    assert isinstance(entries[0], LogEntry)
    assert entries[0].id == "x"


# ---------------------------------------------------------------------------
# Async parity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_execute_returns_result():
    t = MockAsyncTransport(rows=[{"id": "1"}], count=1)
    result = await AsyncLogQuery(t, patient_id="p1").eq("type", "test").execute()
    assert isinstance(result, LogQueryResult)
    assert t.last_body["filter"][0]["op"] == "eq"


@pytest.mark.asyncio
async def test_async_count_sets_count_true():
    t = MockAsyncTransport(count=7)
    n = await AsyncLogQuery(t, patient_id="p1").count()
    assert n == 7
    assert t.last_body.get("count") is True


@pytest.mark.asyncio
async def test_async_single_asserts_cardinality():
    t = MockAsyncTransport(rows=[], count=0)
    with pytest.raises(ValidationError):
        await AsyncLogQuery(t, patient_id="p1").single()


@pytest.mark.asyncio
async def test_async_maybe_single_returns_none():
    t = MockAsyncTransport(rows=[], count=0)
    assert await AsyncLogQuery(t, patient_id="p1").maybe_single() is None


@pytest.mark.asyncio
async def test_async_population_routing():
    t = MockAsyncTransport()
    await AsyncLogQuery(t, patient_ids=["x", "y"], population=True).execute()
    assert t.last_endpoint == "/v1/state/logs/query"
    assert t.last_body["patient_ids"] == ["x", "y"]


@pytest.mark.asyncio
async def test_async_as_logs():
    from olira import LogEntry

    t = MockAsyncTransport(rows=[{"id": "z", "payload": {}}], count=1)
    entries = await AsyncLogQuery(t, patient_id="p1").as_logs()
    assert isinstance(entries[0], LogEntry)


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


def test_transport_422_propagates_as_validation_error():
    class RaisingTransport:
        def query_logs(self, patient_id, body):
            raise ValidationError("invalid field path: user_id")

    with pytest.raises(ValidationError, match="invalid field path"):
        LogQuery(RaisingTransport(), patient_id="p1").eq("user_id", "x").execute()


# ---------------------------------------------------------------------------
# with_count / total_count / has_more
# ---------------------------------------------------------------------------


def test_with_count_sets_include_total_in_body():
    t = MockTransport(rows=[{"id": "1"}], count=1, total_count=100)
    LogQuery(t, patient_id="p1").eq("type", "t").with_count().execute()
    assert t.last_body.get("include_total") is True


def test_with_count_returns_total_count_and_has_more():
    rows = [{"id": str(i)} for i in range(50)]
    t = MockTransport(rows=rows, count=50, total_count=5000)
    result = LogQuery(t, patient_id="p1").limit(50).with_count().execute()
    assert result.total_count == 5000
    assert result.has_more is True


def test_has_more_false_on_last_page():
    rows = [{"id": "1"}, {"id": "2"}]
    t = MockTransport(rows=rows, count=2, total_count=52)
    result = LogQuery(t, patient_id="p1").limit(50).offset(50).with_count().execute()
    assert result.total_count == 52
    assert result.has_more is False


def test_has_more_false_when_all_rows_fit_in_one_page():
    rows = [{"id": "1"}, {"id": "2"}]
    t = MockTransport(rows=rows, count=2, total_count=2)
    result = LogQuery(t, patient_id="p1").with_count().execute()
    assert result.has_more is False


def test_without_with_count_total_count_is_none():
    t = MockTransport(rows=[{"id": "1"}], count=1)
    result = LogQuery(t, patient_id="p1").execute()
    assert result.total_count is None
    assert result.has_more is None


def test_with_count_chaining():
    t = MockTransport(rows=[], count=0, total_count=0)
    q = LogQuery(t, patient_id="p1").eq("type", "t").with_count().limit(100).offset(0)
    q.execute()
    assert t.last_body["include_total"] is True
    assert t.last_body["limit"] == 100


@pytest.mark.asyncio
async def test_async_with_count():
    rows = [{"id": str(i)} for i in range(50)]
    t = MockAsyncTransport(rows=rows, count=50, total_count=5000)
    result = await AsyncLogQuery(t, patient_id="p1").limit(50).with_count().execute()
    assert result.total_count == 5000
    assert result.has_more is True


@pytest.mark.asyncio
async def test_async_has_more_false_on_last_page():
    t = MockAsyncTransport(rows=[{"id": "x"}], count=1, total_count=51)
    result = await AsyncLogQuery(t, patient_id="p1").limit(50).offset(50).with_count().execute()
    assert result.has_more is False


# ---------------------------------------------------------------------------
# OPS set completeness
# ---------------------------------------------------------------------------


def test_ops_set_matches_plan():
    expected = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "nin", "like", "ilike", "is", "exists", "contains"}
    assert _OPS == expected
