"use client";

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { DashboardRiskRow } from "../lib/types";
import { CLIENT_API_PROXY_BASE } from "../lib/api-base";

const COORDS: Record<string, [number, number]> = {
  // Bangladesh
  "BD-4047": [89.4933, 22.3531], // Khulna
  "BD-1006": [90.3534, 22.7626], // Barisal
  "BD-3026": [90.2587, 23.7832], // Dhaka
  "BD-10":   [89.4933, 22.3531],
  "BD-20":   [90.3534, 22.7626],
  "BD-30":   [90.2587, 23.7832],
  // Kenya
  "KE-001":  [36.82, -1.29],    // Nairobi
  "KE-002":  [39.67, -4.05],    // Mombasa
  "KE-003":  [34.76, -0.09],    // Kisumu
  // Nigeria
  "NG-001":  [3.39,   6.52],    // Lagos
  "NG-002":  [8.53,  12.00],    // Kano
  "NG-003":  [7.03,   4.83],    // Rivers
  // Ethiopia
  "ET-001":  [38.74,  8.99],    // Addis Ababa
  "ET-002":  [39.55,  7.65],    // Oromia
  "ET-003":  [37.85, 11.35],    // Amhara
  // Pakistan
  "PK-001":  [67.01, 24.87],    // Karachi
  "PK-002":  [74.35, 31.52],    // Lahore
  "PK-003":  [71.56, 34.01],    // Peshawar
  // India
  "IN-001":  [72.87, 19.07],    // Mumbai
  "IN-002":  [88.36, 22.57],    // Kolkata
  "IN-003":  [80.27, 13.08],    // Chennai
  // Mozambique
  "MZ-001":  [32.59, -25.97],   // Maputo
  "MZ-002":  [34.83, -19.84],   // Beira
  "MZ-003":  [39.26, -15.12],   // Nampula
  // Haiti
  "HT-001":  [-72.34, 18.54],   // Port-au-Prince
  "HT-002":  [-72.20, 19.76],   // Cap-Haitien
  "HT-003":  [-72.69, 19.44],   // Gonaïves
  // Sudan
  "SD-001":  [32.53, 15.55],    // Khartoum
  "SD-002":  [32.48, 15.65],    // Omdurman
  "SD-003":  [37.22, 19.62],    // Port Sudan
  // Yemen
  "YE-001":  [44.21, 15.35],    // Sanaa
  "YE-002":  [45.03, 12.78],    // Aden
  "YE-003":  [42.95, 14.80],    // Hodeidah
};

const COLORS = { high: "#ff3d3d", medium: "#ffab00", low: "#00e676" } as const;
const FILL_COLORS = { high: "rgba(255,61,61,0.18)", medium: "rgba(255,171,0,0.15)", low: "rgba(0,230,118,0.12)" } as const;
const BORDER_COLORS = { high: "rgba(255,61,61,0.6)", medium: "rgba(255,171,0,0.55)", low: "rgba(0,230,118,0.5)" } as const;

const SATELLITE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    satellite: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 19,
      attribution: "© Esri, Maxar, Earthstar Geographics",
    },
    reference: {
      type: "raster",
      tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"],
      tileSize: 256,
      maxzoom: 19,
    },
  },
  layers: [
    { id: "satellite-layer", type: "raster", source: "satellite" },
    { id: "reference-layer", type: "raster", source: "reference", paint: { "raster-opacity": 0.85 } },
  ],
};

interface TacticalMapProps {
  risks: DashboardRiskRow[];
  selectedRegionId: string | null;
  onSelectRegion: (regionId: string) => void;
  apiBaseUrl?: string;
  mapCenter?: [number, number] | null;
  mapZoom?: number | null;
}

export default function TacticalMap({
  risks,
  selectedRegionId,
  onSelectRegion,
  apiBaseUrl = CLIENT_API_PROXY_BASE,
  mapCenter,
  mapZoom,
}: TacticalMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: SATELLITE_STYLE,
      center: [50.0, 15.0],  // global centre — pilot selector flyTo overrides this
      zoom: 2.5,
      attributionControl: false,
    });
    mapRef.current = map;

    map.on("load", async () => {
      // --- Load district boundary polygons from API ---
      try {
        const res = await fetch(`${apiBaseUrl}/regions/geojson`);
        if (res.ok) {
          const geojson = await res.json();

          map.addSource("districts", { type: "geojson", data: geojson });

          // Fill layer - colour by risk level
          map.addLayer({
            id: "district-fill",
            type: "fill",
            source: "districts",
            paint: {
              "fill-color": [
                "match",
                ["get", "risk_level"],
                "high",   FILL_COLORS.high,
                "medium", FILL_COLORS.medium,
                "low",    FILL_COLORS.low,
                "rgba(0,170,255,0.08)",
              ],
              "fill-opacity": 1,
            },
          });

          // Border layer
          map.addLayer({
            id: "district-border",
            type: "line",
            source: "districts",
            paint: {
              "line-color": [
                "match",
                ["get", "risk_level"],
                "high",   BORDER_COLORS.high,
                "medium", BORDER_COLORS.medium,
                "low",    BORDER_COLORS.low,
                "rgba(0,170,255,0.4)",
              ],
              "line-width": 1.5,
            },
          });

          // Selected district highlight border
          map.addLayer({
            id: "district-selected",
            type: "line",
            source: "districts",
            paint: {
              "line-color": "#00aaff",
              "line-width": 3,
              "line-opacity": [
                "case",
                ["==", ["get", "region_id"], selectedRegionId ?? ""],
                1,
                0,
              ],
            },
          });

          // Click on polygon to select district
          map.on("click", "district-fill", (e) => {
            const feature = e.features?.[0];
            if (feature?.properties?.["region_id"]) {
              onSelectRegion(feature.properties["region_id"] as string);
            }
          });

          map.on("mouseenter", "district-fill", () => {
            map.getCanvas().style.cursor = "pointer";
          });
          map.on("mouseleave", "district-fill", () => {
            map.getCanvas().style.cursor = "";
          });
        }
      } catch {
        // Polygon layer is optional - markers still show
      }

      // --- Point markers ---
      risks.forEach((risk) => {
        const coords = COORDS[risk.region_id];
        if (!coords) return;

        const color = COLORS[risk.risk_level];
        const el = document.createElement("div");
        el.className = "gotham-marker";
        el.style.cursor = "pointer";
        el.innerHTML = `
          <div class="gm-anchor">
            <div class="gm-ring" style="border-color:${color};box-shadow:0 0 12px ${color}80;"></div>
            <div class="gm-diamond" style="border-color:${color};"></div>
          </div>
          <div class="gm-label" style="color:${color};border-color:${color}50;">${risk.region_name.toUpperCase()}</div>
          <div class="gm-score" style="color:${color};">${risk.score.toFixed(2)}</div>
        `;
        el.addEventListener("click", () => onSelectRegion(risk.region_id));

        const marker = new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat(coords)
          .addTo(map);
        markersRef.current.push(marker);
      });
    });

    return () => {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Fly to selected country when mapCenter changes (null = stay put / global view)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || mapCenter == null) return;
    map.flyTo({ center: mapCenter, zoom: mapZoom ?? 5, duration: 1400 });
  }, [mapCenter, mapZoom]);

  // Update selected highlight when selectedRegionId changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    if (!map.getLayer("district-selected")) return;
    map.setPaintProperty("district-selected", "line-opacity", [
      "case",
      ["==", ["get", "region_id"], selectedRegionId ?? ""],
      1,
      0,
    ]);
  }, [selectedRegionId]);

  return <div ref={containerRef} className="map-gl-container" />;
}
