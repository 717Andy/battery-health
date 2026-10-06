"""Helpers for the BatteryHealth canonical JSON record."""

from __future__ import annotations

from typing import Any


def battery_to_dict(record: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-serializable copy (already dict-shaped)."""
    return record


def discharge_cycles(record: dict[str, Any]) -> list[dict[str, Any]]:
    return [c for c in record.get("cycles", []) if str(c.get("type", "")).lower() == "discharge"]


def dict_to_summary(record: dict[str, Any]) -> dict[str, Any]:
    discharges = discharge_cycles(record)
    capacities = [c.get("capacityAh") for c in discharges if c.get("capacityAh")]
    return {
        "batteryId": record.get("batteryId"),
        "source": record.get("source"),
        "nCycles": len(discharges),
        "firstCapacityAh": capacities[0] if capacities else None,
        "lastCapacityAh": capacities[-1] if capacities else None,
        "ratedCapacityAh": record.get("ratedCapacityAh"),
        "eolCapacityFraction": record.get("eolCapacityFraction"),
    }
