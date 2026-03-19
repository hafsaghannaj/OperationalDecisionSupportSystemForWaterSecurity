from dataclasses import dataclass


@dataclass(slots=True)
class AdminBoundaryRef:
    region_id: str
    name: str
    admin_level: int
    country_code: str

