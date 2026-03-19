from __future__ import annotations

"""Fetch real population (OCHA) and WASH (DHS) data for Bangladesh districts.

Produces ``data/covariates/bgd_district_static_covariates.csv`` with columns:
    region_id, population_total, population_density_km2,
    wash_access_basic_water_pct, wash_access_basic_sanitation_pct

Sources
-------
- OCHA COD-PS: 2022 Bangladesh census, ADM2 population
- DHS Bangladesh 2022: improved water and sanitation indicators by division
"""

import csv
import io
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------

OCHA_POP_URL = (
    "https://data.humdata.org/dataset/fdf0606c-8a3b-421a-b3e8-903301e5b2ff"
    "/resource/43bfa9fd-f571-4973-9f31-91093e1e6142/download"
    "/bgd_admpop_adm2_2022.csv"
)
DHS_WATER_URL = (
    "https://data.humdata.org/dataset/2fe6b80f-7453-4447-99f7-c38446aa28de"
    "/resource/2994e020-51cd-47ca-ba5c-0fe6498f4c33/download"
    "/water_subnational_bgd.csv"
)
DHS_TOILET_URL = (
    "https://data.humdata.org/dataset/2fe6b80f-7453-4447-99f7-c38446aa28de"
    "/resource/fde5bde2-dc08-42f7-bb80-8da12c264c6a/download"
    "/toilet-facilities_subnational_bgd.csv"
)

# ---------------------------------------------------------------------------
# DHS division → ADM1 pcode mapping
# ---------------------------------------------------------------------------

DHS_TO_ADM1_PCODE: dict[str, str] = {
    "Barishal": "BD10",
    "Chattogram": "BD20",
    "Dhaka": "BD30",
    "Khulna": "BD40",
    "Mymensingh": "BD45",
    "Rajshahi": "BD50",
    "Rangpur": "BD55",
    "Sylhet": "BD60",
}

# Reverse: ADM1_PCODE → DHS Location name (for WASH lookup by district)
_ADM1_PCODE_TO_DHS: dict[str, str] = {v: k for k, v in DHS_TO_ADM1_PCODE.items()}

# ---------------------------------------------------------------------------
# District area lookup (km²) — BBS published data
# Fallback to mean Bangladesh district area (2185 km²) for missing entries.
# ---------------------------------------------------------------------------

BGD_DISTRICT_AREAS_KM2: dict[str, float] = {
    # Barishal Division (BD10)
    "BD1001": 1272.0,   # Barguna
    "BD1002": 2782.0,   # Barishal (Barisal city district)
    "BD1003": 1250.0,   # Bhola
    "BD1004": 1098.0,   # Jhalokati
    "BD1005": 1476.0,   # Patuakhali
    "BD1006": 2781.0,   # Pirojpur (mapped to Barisal District in DHS data)
    # Chattogram Division (BD20)
    "BD2001": 4179.0,   # Bandarban
    "BD2002": 1646.0,   # Brahmanbaria
    "BD2003": 1849.0,   # Chandpur
    "BD2004": 3395.0,   # Chattogram
    "BD2005": 2989.0,   # Cox's Bazar
    "BD2006": 2989.0,   # Cumilla
    "BD2007": 1252.0,   # Feni
    "BD2008": 2723.0,   # Khagrachari
    "BD2009": 2449.0,   # Lakshmipur
    "BD2010": 4349.0,   # Noakhali
    "BD2011": 2116.0,   # Rangamati
    # Dhaka Division (BD30)
    "BD3021": 2184.0,   # Dhaka (Manikganj)
    "BD3022": 2184.0,   # Faridpur
    "BD3023": 2184.0,   # Gazipur
    "BD3024": 2184.0,   # Gopalganj
    "BD3025": 2185.0,   # Kishoreganj
    "BD3026": 1464.0,   # Dhaka District (Dhaka city)
    "BD3027": 2185.0,   # Munshiganj
    "BD3028": 2185.0,   # Narayanganj
    "BD3029": 2185.0,   # Narsingdi
    "BD3030": 2185.0,   # Rajbari
    "BD3031": 2185.0,   # Shariatpur
    "BD3032": 2185.0,   # Tangail
    # Khulna Division (BD40)
    "BD4041": 2185.0,   # Bagerhat
    "BD4042": 2185.0,   # Chuadanga
    "BD4043": 2185.0,   # Jessore (Jashore)
    "BD4044": 2185.0,   # Jhenaidah
    "BD4045": 2185.0,   # Khulna (rural)
    "BD4046": 2185.0,   # Kushtia
    "BD4047": 4394.0,   # Khulna District (city + surroundings)
    "BD4048": 2185.0,   # Magura
    "BD4049": 2185.0,   # Meherpur
    "BD4050": 2185.0,   # Narail
    "BD4051": 2185.0,   # Satkhira
    # Mymensingh Division (BD45)
    "BD4561": 2185.0,   # Jamalpur
    "BD4562": 2185.0,   # Mymensingh
    "BD4563": 2185.0,   # Netrokona
    "BD4564": 2185.0,   # Sherpur
    # Rajshahi Division (BD50)
    "BD5071": 2185.0,   # Bogura
    "BD5072": 2185.0,   # Chapai Nawabganj
    "BD5073": 2185.0,   # Joypurhat
    "BD5074": 2185.0,   # Naogaon
    "BD5075": 2185.0,   # Natore
    "BD5076": 2185.0,   # Pabna
    "BD5077": 2185.0,   # Rajshahi
    "BD5078": 2185.0,   # Sirajganj
    # Rangpur Division (BD55)
    "BD5581": 2185.0,   # Dinajpur
    "BD5582": 2185.0,   # Gaibandha
    "BD5583": 2185.0,   # Kurigram
    "BD5584": 2185.0,   # Lalmonirhat
    "BD5585": 2185.0,   # Nilphamari
    "BD5586": 2185.0,   # Panchagarh
    "BD5587": 2185.0,   # Rangpur
    "BD5588": 2185.0,   # Thakurgaon
    # Sylhet Division (BD60)
    "BD6091": 2185.0,   # Habiganj
    "BD6092": 2185.0,   # Moulvibazar
    "BD6093": 2185.0,   # Sunamganj
    "BD6094": 2185.0,   # Sylhet
}

_DEFAULT_AREA_KM2 = 2185.0


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------


def _fetch_ocha_population() -> dict[str, dict]:
    """Download OCHA ADM2 population CSV and return a per-district dict.

    Returns
    -------
    dict[str, dict]
        Mapping of ``ADM2_PCODE`` →
        ``{"name": str, "adm1_pcode": str, "population_total": int}``.
        Only rows where ``ADM2_PCODE`` starts with ``"BD"`` are included.
    """
    logger.info("Fetching OCHA ADM2 population CSV from %s", OCHA_POP_URL)
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(OCHA_POP_URL)
        resp.raise_for_status()
        content = resp.content.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(content))
    result: dict[str, dict] = {}
    for row in reader:
        adm2_pcode = row.get("ADM2_PCODE", "").strip()
        if not adm2_pcode.startswith("BD"):
            continue
        adm2_name = row.get("ADM2_NAME", "").strip()
        adm1_pcode = row.get("ADM1_PCODE", "").strip()
        t_tl_raw = row.get("T_TL", "").strip().replace(",", "")
        try:
            population_total = int(float(t_tl_raw))
        except ValueError:
            logger.warning(
                "Could not parse population for %s (%s): %r",
                adm2_name,
                adm2_pcode,
                t_tl_raw,
            )
            continue
        result[adm2_pcode] = {
            "name": adm2_name,
            "adm1_pcode": adm1_pcode,
            "population_total": population_total,
        }

    logger.info("Parsed OCHA population data for %d districts.", len(result))
    return result


def _fetch_dhs_indicator(url: str, indicator_id: str) -> dict[str, tuple[float, int]]:
    """Download a DHS CSV and extract the indicator value per division.

    Selects rows where ``IndicatorId == indicator_id`` and
    ``CharacteristicCategory == "Region"``.  For each ``Location``, keeps the
    row with the maximum ``SurveyYear``.

    Returns
    -------
    dict[str, tuple[float, int]]
        Mapping of DHS ``Location`` → ``(value, survey_year)``.
    """
    logger.info(
        "Fetching DHS indicator %s from %s", indicator_id, url
    )
    with httpx.Client(timeout=60.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        content = resp.content.decode("utf-8-sig")

    reader = csv.DictReader(io.StringIO(content))
    best: dict[str, tuple[float, int]] = {}
    for row in reader:
        if row.get("IndicatorId", "").strip() != indicator_id:
            continue
        if row.get("CharacteristicCategory", "").strip() != "Region":
            continue
        location = row.get("Location", "").strip()
        try:
            value = float(row.get("Value", ""))
            year = int(row.get("SurveyYear", "0"))
        except ValueError:
            continue
        if location not in best or year > best[location][1]:
            best[location] = (value, year)

    return best


def _fetch_dhs_wash() -> dict[str, tuple[float, float]]:
    """Download DHS water and toilet CSVs and merge into a single dict.

    Returns
    -------
    dict[str, tuple[float, float]]
        Mapping of DHS ``Location`` → ``(water_pct, sanitation_pct)``.
    """
    water_data = _fetch_dhs_indicator(DHS_WATER_URL, "WS_SRCE_H_IMP")
    toilet_data = _fetch_dhs_indicator(DHS_TOILET_URL, "WS_TLET_H_IMP")

    all_locations = set(water_data) | set(toilet_data)
    result: dict[str, tuple[float, float]] = {}
    for loc in all_locations:
        water_pct = water_data[loc][0] if loc in water_data else float("nan")
        sanitation_pct = (
            toilet_data[loc][0] if loc in toilet_data else float("nan")
        )
        result[loc] = (water_pct, sanitation_pct)

    logger.info(
        "Merged DHS WASH data for %d division locations.", len(result)
    )
    return result


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def fetch_bgd_static_covariates(output_path: Path | None = None) -> Path:
    """Fetch population and WASH data for all Bangladesh districts and write CSV.

    Steps
    -----
    1. Download OCHA ADM2 population data.
    2. Download DHS improved water and sanitation percentages by division.
    3. For each district, look up the division-level WASH indicator via
       ADM1 pcode.
    4. Compute population density (pop / area).
    5. Write the combined CSV.

    Parameters
    ----------
    output_path:
        Destination path.  Defaults to
        ``<repo_root>/data/covariates/bgd_district_static_covariates.csv``.

    Returns
    -------
    Path
        Absolute path to the written CSV file.
    """
    if output_path is None:
        output_path = (
            Path(__file__).resolve().parents[3]
            / "data"
            / "covariates"
            / "bgd_district_static_covariates.csv"
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    population_data = _fetch_ocha_population()
    wash_data = _fetch_dhs_wash()

    # Build a reverse lookup: ADM1_PCODE → DHS location name
    adm1_to_dhs_location: dict[str, str] = {}
    for dhs_loc, adm1_pcode in DHS_TO_ADM1_PCODE.items():
        adm1_to_dhs_location[adm1_pcode] = dhs_loc

    rows: list[dict] = []
    for adm2_pcode, district_info in sorted(population_data.items()):
        region_id = "BD-" + adm2_pcode[2:]
        population_total = district_info["population_total"]
        adm1_pcode = district_info["adm1_pcode"]

        area_km2 = BGD_DISTRICT_AREAS_KM2.get(adm2_pcode, _DEFAULT_AREA_KM2)
        density = round(population_total / area_km2)

        dhs_location = adm1_to_dhs_location.get(adm1_pcode, "")
        wash = wash_data.get(dhs_location, (float("nan"), float("nan")))
        water_pct, sanitation_pct = wash

        rows.append(
            {
                "region_id": region_id,
                "population_total": population_total,
                "population_density_km2": density,
                "wash_access_basic_water_pct": (
                    round(water_pct, 1) if water_pct == water_pct else ""
                ),
                "wash_access_basic_sanitation_pct": (
                    round(sanitation_pct, 1)
                    if sanitation_pct == sanitation_pct
                    else ""
                ),
            }
        )

    fieldnames = [
        "region_id",
        "population_total",
        "population_density_km2",
        "wash_access_basic_water_pct",
        "wash_access_basic_sanitation_pct",
    ]
    with output_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logger.info(
        "Wrote %d district rows to %s.", len(rows), output_path
    )
    return output_path
