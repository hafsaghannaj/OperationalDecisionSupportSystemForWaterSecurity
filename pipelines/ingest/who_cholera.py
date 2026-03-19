from __future__ import annotations

"""Framework for fetching WHO GHO cholera case data.

NOTE: Bangladesh does not currently report cholera case counts to WHO GHO.
Connect to DGHS surveillance API when available.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

NOTE_BGD = (
    "Bangladesh does not currently report cholera case counts to WHO GHO. "
    "Connect to DGHS surveillance API when available."
)

WHO_GHO_INDICATOR = "CHOLERA_0000000001"
_WHO_GHO_BASE_URL = "https://ghoapi.azureedge.net/api"


def fetch_who_gho_cases(
    iso3: str = "BGD",
    years: int = 5,
) -> list[dict]:
    """Fetch annual cholera case counts from the WHO GHO OData API.

    Calls::

        GET /api/CHOLERA_0000000001?$filter=SpatialDim eq '{iso3}'
            &$orderby=TimeDim desc&$top={years}

    Parameters
    ----------
    iso3:
        ISO 3166-1 alpha-3 country code.  Defaults to ``"BGD"`` (Bangladesh).
    years:
        Maximum number of most-recent years to return.

    Returns
    -------
    list[dict]
        List of ``{"year": int, "cases": float | None}`` dicts ordered from
        most recent to oldest.  Returns an empty list if the request fails or
        no data is available for the specified country.

    Notes
    -----
    Bangladesh currently reports zero records to WHO GHO for this indicator.
    See :data:`NOTE_BGD`.
    """
    url = (
        f"{_WHO_GHO_BASE_URL}/{WHO_GHO_INDICATOR}"
        f"?$filter=SpatialDim eq '{iso3}'"
        f"&$orderby=TimeDim desc"
        f"&$top={years}"
    )
    logger.info("Fetching WHO GHO cholera data for %s from %s", iso3, url)

    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning(
            "WHO GHO request failed for iso3=%s: %s", iso3, exc
        )
        return []

    raw_values = payload.get("value", [])
    if not raw_values:
        logger.info(
            "No WHO GHO cholera records returned for %s. %s", iso3, NOTE_BGD
        )
        return []

    results: list[dict] = []
    for item in raw_values:
        year_raw = item.get("TimeDim")
        numeric_value = item.get("NumericValue")
        try:
            year = int(year_raw)
        except (TypeError, ValueError):
            logger.warning("Could not parse year from WHO GHO item: %r", item)
            continue
        cases: float | None = (
            float(numeric_value) if numeric_value is not None else None
        )
        results.append({"year": year, "cases": cases})

    logger.info(
        "Fetched %d WHO GHO cholera records for %s.", len(results), iso3
    )
    return results


def distribute_cases_to_districts(
    annual_cases: list[dict],
    district_weights: dict[str, float],
) -> list[dict]:
    """Distribute national annual cholera cases to districts by weight.

    Parameters
    ----------
    annual_cases:
        List of ``{"year": int, "cases": float | None}`` dicts as returned by
        :func:`fetch_who_gho_cases`.
    district_weights:
        Mapping of ``region_id`` → weight (e.g. population fraction).  Weights
        do not need to sum to 1; they are normalised internally.

    Returns
    -------
    list[dict]
        List of ``{"year": int, "region_id": str, "estimated_cases": int}``
        records.  Years with ``cases=None`` are skipped.

    Notes
    -----
    If ``district_weights`` is empty or all weights are zero, an empty list is
    returned.
    """
    if not district_weights:
        logger.warning(
            "distribute_cases_to_districts called with empty district_weights."
        )
        return []

    total_weight = sum(district_weights.values())
    if total_weight == 0.0:
        logger.warning(
            "All district weights are zero; cannot distribute cases."
        )
        return []

    results: list[dict] = []
    for entry in annual_cases:
        year = entry.get("year")
        cases = entry.get("cases")
        if cases is None:
            continue
        national_cases = float(cases)
        for region_id, weight in district_weights.items():
            fraction = weight / total_weight
            estimated_cases = int(round(national_cases * fraction))
            results.append(
                {
                    "year": year,
                    "region_id": region_id,
                    "estimated_cases": estimated_cases,
                }
            )

    logger.info(
        "Distributed cases for %d year(s) across %d district(s).",
        len(annual_cases),
        len(district_weights),
    )
    return results
