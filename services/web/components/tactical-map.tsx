"use client";

import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { DashboardRiskRow } from "../lib/types";

const COORDS: Record<string, [number, number]> = {
  // OCHA pcode centroids (lon, lat) — derived from GeoBoundaries ADM2 GeoJSON
  "BD-4047": [89.4933, 22.3531], // Khulna
  "BD-1006": [90.3534, 22.7626], // Barisal
  "BD-3026": [90.2587, 23.7832], // Dhaka
  // Legacy IDs kept for backward compatibility
  "BD-10": [89.4933, 22.3531],
  "BD-20": [90.3534, 22.7626],
  "BD-30": [90.2587, 23.7832],
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

export default function TacticalMap({ risks, selectedRegionId, onSelectRegion, apiBaseUrl = "http://localhost:8000", mapCenter, mapZoom }: TacticalMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: SATELLITE_STYLE,
      center: [90.2, 23.1],
      zoom: 6.8,
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
