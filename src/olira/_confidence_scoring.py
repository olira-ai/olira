"""Helpers for per-scorer confidence scoring config patches (client-side)."""

from __future__ import annotations

from typing import Any

SCORER_COVERAGE = "builtin.coverage"
SCORER_FRESHNESS = "builtin.freshness"
SCORER_CERTAINTY = "builtin.certainty"
SCORER_CONSISTENCY = "builtin.consistency"
SCORER_EVIDENCE_DENSITY = "builtin.evidence_density"

BUILTIN_SCORER_IDS = (
    SCORER_COVERAGE,
    SCORER_FRESHNESS,
    SCORER_CERTAINTY,
    SCORER_CONSISTENCY,
    SCORER_EVIDENCE_DENSITY,
)


def _legacy_params_to_scorers(params: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not params:
        return []
    out: list[dict[str, Any]] = []
    fresh: dict[str, Any] = {}
    if "freshness_zero_days" in params and params["freshness_zero_days"] is not None:
        fresh["freshness_zero_days"] = params["freshness_zero_days"]
    if fresh:
        out.append({"scorer_id": SCORER_FRESHNESS, "params": fresh})
    dens: dict[str, Any] = {}
    if "evidence_density_divisor" in params and params["evidence_density_divisor"] is not None:
        dens["evidence_density_divisor"] = params["evidence_density_divisor"]
    if dens:
        out.append({"scorer_id": SCORER_EVIDENCE_DENSITY, "params": dens})
    cert: dict[str, Any] = {}
    if params.get("certainty_rubric"):
        cert["certainty_rubric"] = params["certainty_rubric"]
    if "agentic_trajectory_alpha" in params and params["agentic_trajectory_alpha"] is not None:
        cert["agentic_trajectory_alpha"] = params["agentic_trajectory_alpha"]
    if cert:
        out.append({"scorer_id": SCORER_CERTAINTY, "params": cert})
    cons: dict[str, Any] = {}
    if params.get("consistency_rubric"):
        cons["consistency_rubric"] = params["consistency_rubric"]
    if "agentic_trajectory_alpha" in params and params["agentic_trajectory_alpha"] is not None:
        cons["agentic_trajectory_alpha"] = params["agentic_trajectory_alpha"]
    if cons:
        out.append({"scorer_id": SCORER_CONSISTENCY, "params": cons})
    return out


def normalize_scoring_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return a scorers-primary config dict (drops deprecated flat params)."""
    if not raw:
        return {"scorers": None, "weights": None, "params": None}
    scorers = raw.get("scorers")
    weights = raw.get("weights")
    params = raw.get("params")
    if scorers is None and isinstance(params, dict):
        scorers = _legacy_params_to_scorers(params) or None
        if weights is None and "weights" in params:
            weights = params.get("weights")
    return {"scorers": scorers, "weights": weights, "params": None}


def get_scorer_params_from_config(
    raw: dict[str, Any] | None, scorer_id: str
) -> dict[str, Any] | None:
    cfg = normalize_scoring_config(raw)
    for entry in cfg.get("scorers") or []:
        if isinstance(entry, dict) and str(entry.get("scorer_id")) == scorer_id:
            params = entry.get("params")
            return dict(params) if isinstance(params, dict) else {}
    return None


def patch_scorer_in_config(
    raw: dict[str, Any] | None,
    scorer_id: str,
    params: dict[str, Any] | None,
) -> dict[str, Any]:
    """Replace one scorer's params (or remove when params is None). Returns write payload."""
    cfg = normalize_scoring_config(raw)
    existing = [e for e in (cfg.get("scorers") or []) if isinstance(e, dict)]
    kept = [e for e in existing if str(e.get("scorer_id")) != scorer_id]
    if params is not None:
        kept.append({"scorer_id": scorer_id, "params": dict(params)})
    out: dict[str, Any] = {"scorers": kept or None}
    if cfg.get("weights") is not None:
        out["weights"] = cfg["weights"]
    return out


def set_weights_in_config(
    raw: dict[str, Any] | None,
    weights: dict[str, float] | None,
) -> dict[str, Any]:
    cfg = normalize_scoring_config(raw)
    out: dict[str, Any] = {"scorers": cfg.get("scorers")}
    if weights is not None:
        out["weights"] = weights
    return out
