/** Pilot registry — add an entry here for each country you want selectable in the UI.
 *  The selector controls map navigation only; all countries' data is always visible.
 *  Use the special "ALL" key to show a global overview (no flyTo).
 */
export interface PilotConfig {
  key: string;               // ISO-2 country code (or "ALL" for global view)
  label: string;             // Human-readable name shown in the selector
  region_id_prefix: string;  // unused when key === "ALL"
  map_center: [number, number] | null; // null = no flyTo (global view)
  map_zoom: number | null;
}

export const PILOT_REGISTRY: Record<string, PilotConfig> = {
  ALL: { key: "ALL", label: "All Countries", region_id_prefix: "", map_center: null, map_zoom: null },
  BD: { key: "BD", label: "Bangladesh",  region_id_prefix: "BD-", map_center: [90.2,  23.1],  map_zoom: 6.8 },
  KE: { key: "KE", label: "Kenya",       region_id_prefix: "KE-", map_center: [37.9,  0.02],  map_zoom: 5.5 },
  NG: { key: "NG", label: "Nigeria",     region_id_prefix: "NG-", map_center: [8.7,   9.0],   map_zoom: 5.2 },
  ET: { key: "ET", label: "Ethiopia",    region_id_prefix: "ET-", map_center: [40.0,  9.0],   map_zoom: 5.0 },
  PK: { key: "PK", label: "Pakistan",    region_id_prefix: "PK-", map_center: [69.3,  30.4],  map_zoom: 5.2 },
  IN: { key: "IN", label: "India",       region_id_prefix: "IN-", map_center: [78.9,  20.6],  map_zoom: 4.5 },
  MZ: { key: "MZ", label: "Mozambique",  region_id_prefix: "MZ-", map_center: [35.0, -18.7],  map_zoom: 5.0 },
  HT: { key: "HT", label: "Haiti",       region_id_prefix: "HT-", map_center: [-72.3, 19.0],  map_zoom: 7.0 },
  SD: { key: "SD", label: "Sudan",       region_id_prefix: "SD-", map_center: [30.2,  15.5],  map_zoom: 4.8 },
  YE: { key: "YE", label: "Yemen",       region_id_prefix: "YE-", map_center: [48.5,  15.9],  map_zoom: 5.5 },
};

export const DEFAULT_PILOT_KEY = "ALL";

export function countryCodeFromRegionId(regionId: string): string {
  return regionId.split("-")[0];
}

export function pilotForRegionId(regionId: string): PilotConfig | undefined {
  return PILOT_REGISTRY[countryCodeFromRegionId(regionId)];
}
