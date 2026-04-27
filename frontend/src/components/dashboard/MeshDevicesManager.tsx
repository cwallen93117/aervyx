"use client";

import { useCallback, useEffect, useState } from "react";
import type { MeshDevicePurpose, MeshDeviceRecord } from "./types";

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
        }
      } catch { return configured; }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

const PURPOSE_OPTIONS: { value: MeshDevicePurpose; label: string }[] = [
  { value: "tracking", label: "Pilot" },
  { value: "driver_mesh", label: "Driver" },
  { value: "driver_wifi", label: "Driver Wi-Fi" },
  { value: "base_station", label: "Base Station" },
];

const normalizeUserPurpose = (purpose: MeshDevicePurpose): MeshDevicePurpose =>
  PURPOSE_OPTIONS.some((option) => option.value === purpose) ? purpose : "base_station";

const purposeLabel = (purpose: string) =>
  PURPOSE_OPTIONS.find((option) => option.value === purpose)?.label ?? (purpose === "relay" ? "Base Station" : purpose);

export default function MeshDevicesManager({ token }: { token: string }) {
  const [devices, setDevices] = useState<MeshDeviceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newDevice, setNewDevice] = useState<{ device_id: string; label: string; purpose: MeshDevicePurpose }>({
    device_id: "",
    label: "",
    purpose: "tracking",
  });
  const [drafts, setDrafts] = useState<Record<string, { label: string; purpose: MeshDevicePurpose; is_active: boolean }>>({});
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const showFeedback = useCallback((type: "success" | "error", text: string) => {
    setFeedback({ type, text });
    setTimeout(() => setFeedback(null), 3500);
  }, []);

  const loadDevices = useCallback(async () => {
    try {
      const data = await apiFetch<MeshDeviceRecord[]>("/api/auth/mesh-devices", token);
      setDevices(data);
      setDrafts(Object.fromEntries(data.map((device) => [
        device.device_id,
        { label: device.label, purpose: normalizeUserPurpose(device.purpose), is_active: device.is_active },
      ])));
    } catch (error) {
      showFeedback("error", error instanceof Error ? error.message : "Failed to load Meshtastic devices");
    } finally {
      setLoading(false);
    }
  }, [token, showFeedback]);

  useEffect(() => { void loadDevices(); }, [loadDevices]);

  async function addDevice() {
    const deviceId = newDevice.device_id.trim().toLowerCase();
    if (!deviceId) return;
    setSaving(true);
    try {
      await apiFetch<MeshDeviceRecord>("/api/auth/mesh-devices", token, {
        method: "POST",
        body: JSON.stringify({
          device_id: deviceId,
          label: newDevice.label.trim() || null,
          purpose: newDevice.purpose,
          is_active: true,
        }),
      });
      setNewDevice({ device_id: "", label: "", purpose: "tracking" });
      showFeedback("success", "Meshtastic device saved.");
      await loadDevices();
    } catch (error) {
      showFeedback("error", error instanceof Error ? error.message : "Could not save device.");
    } finally {
      setSaving(false);
    }
  }

  async function saveDevice(device: MeshDeviceRecord) {
    const draft = drafts[device.device_id];
    if (!draft) return;
    setSaving(true);
    try {
      await apiFetch<MeshDeviceRecord>(`/api/auth/mesh-devices/${encodeURIComponent(device.device_id)}`, token, {
        method: "PATCH",
        body: JSON.stringify(draft),
      });
      showFeedback("success", "Device updated.");
      await loadDevices();
    } catch (error) {
      showFeedback("error", error instanceof Error ? error.message : "Could not update device.");
    } finally {
      setSaving(false);
    }
  }

  async function deleteDevice(device: MeshDeviceRecord) {
    setSaving(true);
    try {
      await apiFetch<void>(`/api/auth/mesh-devices/${encodeURIComponent(device.device_id)}`, token, { method: "DELETE" });
      showFeedback("success", "Device removed.");
      await loadDevices();
    } catch (error) {
      showFeedback("error", error instanceof Error ? error.message : "Could not remove device.");
    } finally {
      setSaving(false);
    }
  }

  async function setTrackingDevice(device: MeshDeviceRecord) {
    setSaving(true);
    try {
      await apiFetch("/api/auth/mesh-devices/tracking", token, {
        method: "PUT",
        body: JSON.stringify({ mesh_device_id: device.device_id }),
      });
      showFeedback("success", "Tracking device updated.");
      await loadDevices();
    } catch (error) {
      showFeedback("error", error instanceof Error ? error.message : "Could not update tracking device.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="stack form-block">
      <div className="inline-grid">
        <label className="stack compact">
          <span>Device ID</span>
          <input
            value={newDevice.device_id}
            onChange={(event) => setNewDevice((current) => ({ ...current, device_id: event.target.value }))}
            placeholder="!abcdef12"
            style={{ fontFamily: "monospace" }}
          />
        </label>
        <label className="stack compact">
          <span>Label</span>
          <input
            value={newDevice.label}
            onChange={(event) => setNewDevice((current) => ({ ...current, label: event.target.value }))}
            placeholder="LZ Gateway"
          />
        </label>
      </div>
      <div className="inline-grid">
        <label className="stack compact">
          <span>Purpose</span>
          <select
            value={newDevice.purpose}
            onChange={(event) => setNewDevice((current) => ({ ...current, purpose: event.target.value as MeshDevicePurpose }))}
          >
            {PURPOSE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <div className="button-row" style={{ alignItems: "flex-end" }}>
          <button type="button" disabled={saving || !newDevice.device_id.trim()} onClick={() => void addDevice()}>
            Add device
          </button>
        </div>
      </div>

      {feedback ? <div className={`status-chip ${feedback.type}`}>{feedback.text}</div> : null}

      <div className="participant-table-wrap">
        <table className="participant-table">
          <thead>
            <tr>
              <th>Label</th>
              <th>Device ID</th>
              <th>Purpose</th>
              <th>Pilot Tracker</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="participant-table-empty">Loading devices...</td></tr>
            ) : devices.length ? (
              devices.map((device) => {
                const draft = drafts[device.device_id] ?? { label: device.label, purpose: normalizeUserPurpose(device.purpose), is_active: device.is_active };
                const isPilotTracker = device.purpose === "tracking" && device.is_active;
                return (
                  <tr key={device.device_id}>
                    <td>
                      <input
                        value={draft.label}
                        onChange={(event) => setDrafts((current) => ({
                          ...current,
                          [device.device_id]: { ...draft, label: event.target.value },
                        }))}
                      />
                    </td>
                    <td style={{ fontFamily: "monospace", fontSize: "0.78rem" }}>{device.device_id}</td>
                    <td>
                      <select
                        value={draft.purpose}
                        onChange={(event) => setDrafts((current) => ({
                          ...current,
                          [device.device_id]: { ...draft, purpose: event.target.value as MeshDevicePurpose },
                        }))}
                      >
                        {PURPOSE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                      </select>
                    </td>
                    <td>
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={isPilotTracker}
                          disabled={saving}
                          aria-label={`Use ${device.label || device.device_id} as pilot tracker`}
                          onChange={() => {
                            if (!isPilotTracker) void setTrackingDevice(device);
                          }}
                        />
                      </label>
                    </td>
                    <td>
                      <label className="checkbox-label">
                        <input
                          type="checkbox"
                          checked={draft.is_active}
                          onChange={(event) => setDrafts((current) => ({
                            ...current,
                            [device.device_id]: { ...draft, is_active: event.target.checked },
                          }))}
                        />
                        Active
                      </label>
                    </td>
                    <td>
                      <div className="button-row">
                        <button type="button" className="ghost-button" disabled={saving} onClick={() => void saveDevice(device)}>Save</button>
                        <button type="button" className="ghost-button danger-button" disabled={saving} onClick={() => void deleteDevice(device)}>Remove</button>
                      </div>
                      <div className="hint">{purposeLabel(device.purpose)} device</div>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr><td colSpan={6} className="participant-table-empty">No Meshtastic devices registered.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
