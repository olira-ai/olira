"""Fluent log query builder — compiles to POST /v1/state/.../logs/query DSL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .exceptions import ValidationError
from .models import LogEntry, LogQueryResult

if TYPE_CHECKING:
    from .http import AsyncHttpTransport, HttpTransport

_OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "in", "nin", "like", "ilike", "is", "exists", "contains"}


class F:
    """Field expression helper for .or_() / .and_() sub-conditions."""

    def __init__(self, field: str) -> None:
        self._field = field

    def eq(self, v: Any) -> dict[str, Any]:
        return {"field": self._field, "op": "eq", "value": v}

    def neq(self, v: Any) -> dict[str, Any]:
        return {"field": self._field, "op": "neq", "value": v}

    def gt(self, v: Any) -> dict[str, Any]:
        return {"field": self._field, "op": "gt", "value": v}

    def gte(self, v: Any) -> dict[str, Any]:
        return {"field": self._field, "op": "gte", "value": v}

    def lt(self, v: Any) -> dict[str, Any]:
        return {"field": self._field, "op": "lt", "value": v}

    def lte(self, v: Any) -> dict[str, Any]:
        return {"field": self._field, "op": "lte", "value": v}

    def in_(self, values: Any) -> dict[str, Any]:
        return {"field": self._field, "op": "in", "value": list(values)}

    def nin(self, values: Any) -> dict[str, Any]:
        return {"field": self._field, "op": "nin", "value": list(values)}

    def like(self, pattern: str) -> dict[str, Any]:
        return {"field": self._field, "op": "like", "value": pattern}

    def ilike(self, pattern: str) -> dict[str, Any]:
        return {"field": self._field, "op": "ilike", "value": pattern}

    def is_(self, v: Any) -> dict[str, Any]:
        return {"field": self._field, "op": "is", "value": v}

    def exists(self, present: bool = True) -> dict[str, Any]:
        return {"field": self._field, "op": "exists", "value": present}

    def contains(self, v: Any) -> dict[str, Any]:
        return {"field": self._field, "op": "contains", "value": v}


def _as_node(c: Any) -> Any:
    return c


class _BaseLogQuery:
    def __init__(
        self,
        transport: Any,
        *,
        patient_id: str | None = None,
        patient_ids: list[str] | None = None,
        population: bool = False,
    ) -> None:
        self._t = transport
        self._patient_id = patient_id
        self._population = population
        self._spec: dict[str, Any] = {}
        if population and patient_ids is not None:
            self._spec["patient_ids"] = list(patient_ids)

    # --- filters ---

    def filter(self, field: str, op: str, value: Any = None) -> _BaseLogQuery:
        if op not in _OPS:
            raise ValidationError(f"unknown operator {op!r}; expected one of {sorted(_OPS)}")
        self._spec.setdefault("filter", []).append({"field": field, "op": op, "value": value})
        return self

    def eq(self, field: str, value: Any) -> _BaseLogQuery:
        return self.filter(field, "eq", value)

    def neq(self, field: str, value: Any) -> _BaseLogQuery:
        return self.filter(field, "neq", value)

    def gt(self, field: str, value: Any) -> _BaseLogQuery:
        return self.filter(field, "gt", value)

    def gte(self, field: str, value: Any) -> _BaseLogQuery:
        return self.filter(field, "gte", value)

    def lt(self, field: str, value: Any) -> _BaseLogQuery:
        return self.filter(field, "lt", value)

    def lte(self, field: str, value: Any) -> _BaseLogQuery:
        return self.filter(field, "lte", value)

    def in_(self, field: str, values: Any) -> _BaseLogQuery:
        return self.filter(field, "in", list(values))

    def nin(self, field: str, values: Any) -> _BaseLogQuery:
        return self.filter(field, "nin", list(values))

    def like(self, field: str, pattern: str) -> _BaseLogQuery:
        return self.filter(field, "like", pattern)

    def ilike(self, field: str, pattern: str) -> _BaseLogQuery:
        return self.filter(field, "ilike", pattern)

    def is_(self, field: str, value: Any) -> _BaseLogQuery:
        return self.filter(field, "is", value)

    def exists(self, field: str, present: bool = True) -> _BaseLogQuery:
        return self.filter(field, "exists", present)

    def contains(self, field: str, value: Any) -> _BaseLogQuery:
        return self.filter(field, "contains", value)

    # --- boolean groups ---

    def or_(self, *conditions: Any) -> _BaseLogQuery:
        self._spec.setdefault("filter", []).append({"or": [_as_node(c) for c in conditions]})
        return self

    def and_(self, *conditions: Any) -> _BaseLogQuery:
        self._spec.setdefault("filter", []).append({"and": [_as_node(c) for c in conditions]})
        return self

    # --- projection ---

    def select(self, *paths: str, **aliases: str) -> _BaseLogQuery:
        sel = self._spec.setdefault("select", [])
        sel += [{"path": p} for p in paths]
        sel += [{"path": path, "alias": alias} for alias, path in aliases.items()]
        return self

    def select_array(
        self,
        path: str,
        *,
        where: Any = None,
        element: str | None = None,
        first: bool = False,
        alias: str | None = None,
    ) -> _BaseLogQuery:
        node: dict[str, Any] = {"path": path, "first": first}
        if alias:
            node["alias"] = alias
        if where is not None:
            node["where"] = _as_node(where)
        if element:
            node["element"] = element
        self._spec.setdefault("select", []).append(node)
        return self

    # --- modifiers ---

    def order(self, field: str, desc: bool = False) -> _BaseLogQuery:
        self._spec.setdefault("order", []).append({"field": field, "desc": desc})
        return self

    def limit(self, n: int) -> _BaseLogQuery:
        self._spec["limit"] = n
        return self

    def offset(self, n: int) -> _BaseLogQuery:
        self._spec["offset"] = n
        return self

    def range(self, start: int, end: int) -> _BaseLogQuery:
        self._spec["offset"] = start
        self._spec["limit"] = end - start + 1
        return self

    # --- aggregations ---

    def group_by(self, *fields: str) -> _BaseLogQuery:
        self._spec.setdefault("group_by", []).extend(fields)
        return self

    def agg(self, op: str, field: str | None = None, *, alias: str) -> _BaseLogQuery:
        a: dict[str, Any] = {"op": op, "alias": alias}
        if field is not None:
            a["field"] = field
        self._spec.setdefault("aggregations", []).append(a)
        return self

    def count_agg(self, alias: str = "count") -> _BaseLogQuery:
        return self.agg("count", alias=alias)

    def sum(self, field: str, alias: str) -> _BaseLogQuery:
        return self.agg("sum", field, alias=alias)

    def avg(self, field: str, alias: str) -> _BaseLogQuery:
        return self.agg("avg", field, alias=alias)

    def min(self, field: str, alias: str) -> _BaseLogQuery:
        return self.agg("min", field, alias=alias)

    def max(self, field: str, alias: str) -> _BaseLogQuery:
        return self.agg("max", field, alias=alias)

    # --- spec finalization ---

    def _build(self, *, count: bool = False) -> dict[str, Any]:
        spec = dict(self._spec)
        if count:
            spec["count"] = True
        return spec


class LogQuery(_BaseLogQuery):
    """Sync fluent query builder over patient event logs."""

    _t: HttpTransport

    def _run(self, *, count: bool = False) -> LogQueryResult:
        body = self._build(count=count)
        if not self._population:
            return self._t.query_logs(self._patient_id or "", body)
        return self._t.query_population_logs(body)

    def execute(self) -> LogQueryResult:
        """Execute the query and return all matching rows."""
        return self._run()

    def count(self) -> int:
        """Return only the total count (sets count:true in the request body)."""
        return self._run(count=True).count

    def single(self) -> dict[str, Any]:
        """Execute and assert exactly one row is returned."""
        if "limit" not in self._spec:
            self.limit(2)
        res = self._run()
        if len(res) != 1:
            raise ValidationError(f"expected exactly one row, got {len(res)}")
        return res[0]

    def maybe_single(self) -> dict[str, Any] | None:
        """Execute and return one row or None; raises if more than one row is returned."""
        if "limit" not in self._spec:
            self.limit(2)
        res = self._run()
        if len(res) > 1:
            raise ValidationError(f"expected at most one row, got {len(res)}")
        return res[0] if res else None

    def as_logs(self) -> list[LogEntry]:
        """Execute and parse rows into typed LogEntry. Only valid when no .select() was used."""
        return self._run().as_logs()


class AsyncLogQuery(_BaseLogQuery):
    """Async fluent query builder over patient event logs."""

    _t: AsyncHttpTransport

    async def _run(self, *, count: bool = False) -> LogQueryResult:  # type: ignore[override]
        body = self._build(count=count)
        if not self._population:
            return await self._t.query_logs(self._patient_id or "", body)
        return await self._t.query_population_logs(body)

    async def execute(self) -> LogQueryResult:  # type: ignore[override]
        """Execute the query and return all matching rows."""
        return await self._run()

    async def count(self) -> int:  # type: ignore[override]
        """Return only the total count."""
        return (await self._run(count=True)).count

    async def single(self) -> dict[str, Any]:  # type: ignore[override]
        """Execute and assert exactly one row is returned."""
        if "limit" not in self._spec:
            self.limit(2)
        res = await self._run()
        if len(res) != 1:
            raise ValidationError(f"expected exactly one row, got {len(res)}")
        return res[0]

    async def maybe_single(self) -> dict[str, Any] | None:  # type: ignore[override]
        """Execute and return one row or None; raises if more than one row is returned."""
        if "limit" not in self._spec:
            self.limit(2)
        res = await self._run()
        if len(res) > 1:
            raise ValidationError(f"expected at most one row, got {len(res)}")
        return res[0] if res else None

    async def as_logs(self) -> list[LogEntry]:  # type: ignore[override]
        """Execute and parse rows into typed LogEntry."""
        return (await self._run()).as_logs()
