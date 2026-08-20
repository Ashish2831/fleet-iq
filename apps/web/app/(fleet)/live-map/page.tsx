"use client";

import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { getToken, rest, WS_URL } from "@/lib/api";

type LiveVehicle = {
  id: string;
  lat?: number | null;
  lng?: number | null;
  status?: string;
  speed?: number;
  plate?: string | null;
  recorded_at?: string | null;
  heading?: number | null;
  driver_id?: string | null;
  route_id?: string | null;
};

type Counts = { active: number; delivering: number; delayed: number; offline: number };

const COLORS: Record<string, string> = {
  delivering: "#c8f54a",
  delayed: "#ffb84d",
  offline: "#6b736c",
  stopped: "#8ec8ff",
  active: "#8ec8ff",
};

export default function LiveMapPage() {
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markers = useRef(new Map<string, maplibregl.Marker>());
  const [counts, setCounts] = useState<Counts>({ active: 0, delivering: 0, delayed: 0, offline: 0 });
  const [selected, setSelected] = useState<LiveVehicle | null>(null);
  const [status, setStatus] = useState("Connecting…");

  useEffect(() => {
    if (!mapEl.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: mapEl.current,
      style: "https://tiles.openfreemap.org/styles/dark",
      center: [77.61, 12.97],
      zoom: 11,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    rest<{ vehicles: LiveVehicle[]; counts: Counts }>("/api/v1/tracking/vehicles")
      .then((snap) => {
        setCounts(snap.counts);
        snap.vehicles.forEach((v) => upsert(v, setSelected));
      })
      .catch(() => undefined);

    const ws = new WebSocket(`${WS_URL}/ws/fleet?token=${encodeURIComponent(token)}`);
    ws.onopen = () => setStatus("Live");
    ws.onclose = () => setStatus("Disconnected");
    ws.onerror = () => setStatus("Socket error");
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.counts) setCounts(msg.counts);
      if (msg.type === "snapshot") {
        (msg.vehicles || []).forEach((v: LiveVehicle) => upsert(v, setSelected));
      }
      if (msg.type === "vehicle.updated" && msg.vehicle) {
        upsert(msg.vehicle, setSelected);
      }
    };
    const ping = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
    }, 20000);
    return () => {
      window.clearInterval(ping);
      ws.close();
    };
  }, []);

  function upsert(v: LiveVehicle, select: typeof setSelected) {
    const map = mapRef.current;
    if (!map || v.lat == null || v.lng == null) {
      const existing = markers.current.get(v.id);
      if (existing && v.status === "offline") existing.getElement().style.background = COLORS.offline;
      return;
    }
    let marker = markers.current.get(v.id);
    if (!marker) {
      const el = document.createElement("div");
      el.className = "live-pin";
      el.title = v.plate || v.id;
      marker = new maplibregl.Marker({ element: el }).setLngLat([v.lng, v.lat]).addTo(map);
      el.addEventListener("click", () => {
        select(v);
        void loadTrail(v.id);
      });
      markers.current.set(v.id, marker);
    } else {
      marker.setLngLat([v.lng, v.lat]);
    }
    const el = marker.getElement();
    el.style.background = COLORS[v.status || "active"] || COLORS.active;
    el.onclick = () => {
      select(v);
      void loadTrail(v.id);
    };
  }

  async function loadTrail(vehicleId: string) {
    const map = mapRef.current;
    if (!map) return;
    const from = new Date(Date.now() - 15 * 60 * 1000).toISOString();
    const to = new Date().toISOString();
    try {
      const data = await rest<{ points: { lat: number; lng: number }[] }>(
        `/api/v1/vehicles/${vehicleId}/track/?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`
      );
      const coords = (data.points || [])
        .filter((p) => p.lat != null && p.lng != null)
        .map((p) => [p.lng, p.lat] as [number, number]);
      const geo = {
        type: "Feature" as const,
        geometry: { type: "LineString" as const, coordinates: coords },
        properties: {},
      };
      const apply = () => {
        if (map.getSource("trail")) {
          (map.getSource("trail") as maplibregl.GeoJSONSource).setData(geo as any);
        } else {
          map.addSource("trail", { type: "geojson", data: geo as any });
          map.addLayer({
            id: "trail-line",
            type: "line",
            source: "trail",
            paint: { "line-color": "#c8f54a", "line-width": 3, "line-opacity": 0.85 },
          });
        }
      };
      if (map.isStyleLoaded()) apply();
      else map.once("load", apply);
    } catch {
      /* history is optional; live pin still works */
    }
  }

  async function pingGps() {
    const token = getToken();
    if (!token) return;
    const first = [...markers.current.entries()][0];
    const id = selected?.id || first?.[0];
    if (!id) return;
    const marker = markers.current.get(id);
    const lngLat = marker?.getLngLat();
    await rest("/api/v1/tracking/locations", {
      method: "POST",
      body: JSON.stringify({
        vehicle_id: id,
        event_id: crypto.randomUUID(),
        recorded_at: new Date().toISOString(),
        lat: (lngLat?.lat ?? 12.97) + 0.002,
        lng: (lngLat?.lng ?? 77.61) + 0.002,
        speed_kmh: 24,
        heading: 80,
      }),
    });
  }

  return (
    <div className="live-map">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>Live fleet map</h2>
        <span className="muted">{status}</span>
      </div>
      <div className="cards">
        <div className="card"><b>{counts.active}</b><span>Active</span></div>
        <div className="card"><b>{counts.delivering}</b><span>Delivering</span></div>
        <div className="card"><b>{counts.delayed}</b><span>Delayed</span></div>
        <div className="card"><b>{counts.offline}</b><span>Offline</span></div>
      </div>
      <div className="map-wrap">
        <div ref={mapEl} style={{ width: "100%", height: "100%" }} />
        {selected ? (
          <aside className="live-drawer">
            <h3>{selected.plate || selected.id.slice(0, 8)}</h3>
            <p>Status {selected.status}</p>
            <p>Speed {selected.speed ?? 0} km/h</p>
            <p>{selected.recorded_at ? new Date(selected.recorded_at).toLocaleTimeString() : "No ping"}</p>
            <button className="ghost" onClick={() => setSelected(null)}>Close</button>
          </aside>
        ) : null}
      </div>
      <button className="ghost" onClick={pingGps} style={{ width: "fit-content" }}>
        Simulate one GPS ping
      </button>
    </div>
  );
}
