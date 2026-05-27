"use client";

import React, { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { type MapLivePosition, type MapTaskPoint, type MapTurnpoint, TaskMap } from "../TaskMap";
import { SectionCard } from "../SectionCard";
import type { AdminSiteRecord, AdminUserRecord, DebugStatusResponse, MapOverlayConfigRecord, MeshDevicePurpose, MeshDeviceRecord, MqttBrokerMode, SiteSettingsRecord, User } from "./types";

type AdminTab = "platform_users" | "site_settings" | "sites_database" | "live_tracking" | "map_config" | "meshtastic" | "faa_credentials";
type MeshConnectionStatus = "live" | "stale" | "offline" | "never_seen";

function normalizeMqttBrokerMode(value: string | null | undefined): MqttBrokerMode {
  return value === "cloud_vm" || value === "private" ? "cloud_vm" : "local_mosquitto";
}

type MeshNode = {
  device_id: string;
  pilot_id: number | null;
  pilot_name: string | null;
  profile_type: string | null;
  device_label: string | null;
  device_purpose: string | null;
  registered_owner_user_id: number | null;
  registered_owner_name: string | null;
  lat: number | null;
  lon: number | null;
  alt: number | null;
  speed: number | null;
  heading: number | null;
  battery_level: number | null;
  timestamp: string;
  source: string | null;
  position_source: string;
  mesh_status: MeshConnectionStatus;
  last_packet_type: string | null;
  last_gateway_id: string | null;
  last_gateway_display_name: string | null;
  last_topic: string | null;
  packet_count: number;
};

type MeshDeviceDebug = NonNullable<DebugStatusResponse["registered_mesh_devices"]>[number];

type MeshDeviceStatus = {
  key: string;
  deviceId: string;
  label: string | null;
  purpose: string | null;
  isConnected: boolean;
  meshStatus: MeshConnectionStatus;
  registeredOwnerUserId: number | null;
  registeredOwnerName: string | null;
  ownerPilotId: number | null;
  source: string | null;
  positionSource: string;
  batteryLevel: number | null;
  lastSeenAt: string | null;
  lastPacketType: string | null;
  lastGatewayId: string | null;
  lastGatewayDisplayName: string | null;
  lastTopic: string | null;
  packetCount: number;
  lastPosition: { lat: number; lon: number; alt: number | null; speed: number | null; heading: number | null } | null;
};

type UnifiedDevice = {
  key: string;
  pilot_id: number | null;
  user_id: number | null;
  pilot_name: string;
  profile_type: string | null;
  session: import("./types").DebugActiveSession | null;
  meshDevices: MeshDeviceStatus[];
  hasPhone: boolean;
  hasMesh: boolean;
  isOnline: boolean;
  lastSeenAt: string | null;
};

type FaaCredentialsRecord = {
  provider: string;
  enabled: boolean;
  base_url: string;
  client_id_header: string;
  client_secret_header: string;
  client_id_configured: boolean;
  client_secret_configured: boolean;
  admin_client_id_configured: boolean;
  admin_client_secret_configured: boolean;
  credential_source: string;
  env_override: boolean;
  last_tested_at: string | null;
  last_test_status: string | null;
  last_test_message: string | null;
  updated_by_user_id: number | null;
  updated_at: string | null;
};

const DEFAULT_FAA_CREDENTIALS: FaaCredentialsRecord = {
  provider: "faa_notams",
  enabled: false,
  base_url: "https://api.faa.gov",
  client_id_header: "client_id",
  client_secret_header: "client_secret",
  client_id_configured: false,
  client_secret_configured: false,
  admin_client_id_configured: false,
  admin_client_secret_configured: false,
  credential_source: "none",
  env_override: false,
  last_tested_at: null,
  last_test_status: null,
  last_test_message: null,
  updated_by_user_id: null,
  updated_at: null,
};

function meshPurposeLabel(purpose: string | null | undefined) {
  switch (purpose) {
    case "tracking": return "Pilot tracker";
    case "base_station": return "Fixed MQTT gateway";
    case "driver_wifi": return "Driver Wi-Fi gateway";
    case "driver_mesh": return "Driver mesh relay";
    case "relay": return "Relay-only";
    default: return purpose ?? "Unregistered";
  }
}

const MESH_DEVICE_PURPOSE_OPTIONS: { value: MeshDevicePurpose; label: string }[] = [
  { value: "tracking", label: "Pilot tracker" },
  { value: "driver_mesh", label: "Driver mesh relay" },
  { value: "driver_wifi", label: "Driver Wi-Fi gateway" },
  { value: "base_station", label: "Fixed MQTT gateway" },
  { value: "relay", label: "Relay-only" },
];

function formatOptionalDateTime(value: string | null | undefined): string {
  if (!value) return "Never";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function credentialSourceLabel(source: string): string {
  switch (source) {
    case "environment": return "Environment variables";
    case "admin": return "Admin settings";
    default: return "Not configured";
  }
}

const MAP_CONTEXTS = [
  { key: "task_builder", label: "Task Builder" },
  { key: "scoring", label: "Scoring" },
  { key: "logbook_replay", label: "Logbook" },
  { key: "dashboard_live", label: "Dash Live" },
  { key: "public_live", label: "Public Live" },
  { key: "airspace_explorer", label: "Airspace" },
  { key: "soaring_forecast", label: "Forecast" },
  { key: "admin_site_preview", label: "Admin" },
] as const;

const MAP_GROUPS = [
  { key: "tasks", label: "Tasks", maps: ["task_builder", "scoring", "dashboard_live", "public_live"] },
  { key: "airspace", label: "Airspace", maps: ["task_builder", "scoring", "dashboard_live", "airspace_explorer"] },
  { key: "flight_tracks", label: "Flight Tracks", maps: ["task_builder", "scoring", "logbook_replay", "dashboard_live", "public_live"] },
  { key: "live_tracking", label: "Live Tracking", maps: ["dashboard_live", "public_live"] },
  { key: "replay", label: "Replay", maps: ["logbook_replay"] },
  { key: "weather", label: "Weather", maps: ["soaring_forecast"] },
  { key: "map_controls", label: "Map Controls", maps: ["task_builder", "scoring", "logbook_replay", "dashboard_live", "public_live", "airspace_explorer", "admin_site_preview"] },
  { key: "site_preview", label: "Site Preview", maps: ["admin_site_preview"] },
] as const;
type UserSortField = "first_name" | "last_name" | "username" | "role" | "status";
type SortDir = "asc" | "desc";

// ---------------------------------------------------------------------------
// MeshDeviceEditModal
// ---------------------------------------------------------------------------

type MeshDeviceLookupResult = {
  device_id: string | null;
  assigned_to: { user_id: number; username: string; full_name: string } | null;
};

interface MeshDeviceEditModalProps {
  user: AdminUserRecord;
  device: MeshDeviceRecord | null;
  apiBase: string;
  token: string;
  onSaved: (updatedUser: AdminUserRecord) => void;
  onClose: () => void;
}

function MeshDeviceEditModal({ user, device, apiBase, token, onSaved, onClose }: MeshDeviceEditModalProps) {
  const [draft, setDraft] = useState({
    device_id: device?.device_id ?? user.mesh_device_id ?? "",
    label: device?.label ?? "",
    purpose: (device?.purpose ?? "tracking") as MeshDevicePurpose,
  });
  const [lookupResult, setLookupResult] = useState<MeshDeviceLookupResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const trimmed = draft.device_id.trim();
    if (!trimmed || trimmed === (device?.device_id ?? user.mesh_device_id ?? "")) {
      setLookupResult(null);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(
          `${apiBase}/api/auth/admin/mesh-device-lookup?device_id=${encodeURIComponent(trimmed)}`,
          { headers: { Authorization: `Bearer ${token}` } },
        );
        if (res.ok) {
          setLookupResult((await res.json()) as MeshDeviceLookupResult);
        }
      } catch {
        // silently ignore lookup errors
      }
    }, 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [draft.device_id, device?.device_id, user.mesh_device_id, apiBase, token]);

  const trimmedInput = draft.device_id.trim();
  const unchanged = device
    ? trimmedInput === device.device_id &&
      draft.label === device.label &&
      draft.purpose === device.purpose
    : trimmedInput === (user.mesh_device_id ?? "");
  const saveDisabled = saving || unchanged || trimmedInput === "";

  const conflictUser =
    lookupResult?.assigned_to &&
    lookupResult.assigned_to.user_id !== user.id
      ? lookupResult.assigned_to
      : null;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = device
        ? await fetch(`${apiBase}/api/auth/users/${user.id}/mesh-devices/${encodeURIComponent(device.device_id)}`, {
            method: "PATCH",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              device_id: trimmedInput,
              label: draft.label,
              purpose: draft.purpose,
            }),
          })
        : await fetch(`${apiBase}/api/auth/users/${user.id}/mesh-device`, {
            method: "PATCH",
            headers: {
              Authorization: `Bearer ${token}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ mesh_device_id: trimmedInput || null }),
          });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? `Server error ${res.status}`);
      }
      const updated = (await res.json()) as AdminUserRecord;
      onSaved(updated);
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not save device ID.");
    } finally {
      setSaving(false);
    }
  }

  async function handleClearTracker() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/api/auth/users/${user.id}/mesh-devices/tracking`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ mesh_device_id: null }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? `Server error ${res.status}`);
      }
      const updated = (await res.json()) as AdminUserRecord;
      onSaved(updated);
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not clear pilot tracker.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="confirm-overlay"
      onClick={() => { if (!saving) onClose(); }}
    >
      <div
        className="confirm-dialog confirm-dialog-wide"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Edit Mesh Device"
      >
        <strong>Edit Mesh Device</strong>
        <div style={{ fontSize: "0.85rem", color: "var(--color-text-muted, #888)", marginBottom: "4px" }}>
          {user.full_name || user.username}
        </div>
        <label className="stack compact">
          <span>Mesh Device ID</span>
          <input
            value={draft.device_id}
            onChange={(e) => setDraft((current) => ({ ...current, device_id: e.target.value }))}
            placeholder="!c0ac2c6e"
            style={{ fontFamily: "monospace" }}
            autoFocus
          />
        </label>
        <div style={{ fontSize: "0.75rem", color: "var(--color-text-muted, #888)", marginTop: "2px" }}>
          Format: !abcdef12
        </div>
        {conflictUser ? (
          <div
            style={{
              marginTop: "8px",
              padding: "8px 10px",
              background: "rgba(245, 158, 11, 0.08)",
              borderLeft: "3px solid #f59e0b",
              borderRadius: "3px",
              fontSize: "0.8125rem",
              color: "#b45309",
            }}
          >
            <span>&#9888; This device is currently assigned to </span>
            <strong>{conflictUser.full_name}</strong>
            <span>. Saving will reclaim it from that user.</span>
          </div>
        ) : lookupResult && !lookupResult.assigned_to ? (
          <div style={{ marginTop: "8px", fontSize: "0.8rem", color: "var(--color-text-muted, #888)" }}>
            Not currently assigned to anyone.
          </div>
        ) : null}
        {device ? (
          <>
            <label className="stack compact" style={{ marginTop: "8px" }}>
              <span>Label</span>
              <input
                value={draft.label}
                onChange={(e) => setDraft((current) => ({ ...current, label: e.target.value }))}
                placeholder="Pilot tracker"
              />
            </label>
            <label className="stack compact">
              <span>Purpose</span>
              <select
                value={draft.purpose}
                onChange={(e) => setDraft((current) => ({ ...current, purpose: e.target.value as MeshDevicePurpose }))}
              >
                {MESH_DEVICE_PURPOSE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
          </>
        ) : null}
        {error ? <div className="status-chip error" style={{ marginTop: "8px" }}>{error}</div> : null}
        <div className="confirm-actions" style={{ marginTop: "12px" }}>
          <button
            type="button"
            className="ghost-button"
            disabled={saving}
            onClick={onClose}
          >
            Cancel
          </button>
          {user.mesh_device_id && (!device || user.mesh_device_id === device.device_id) ? (
            <button
              type="button"
              className="ghost-button danger-button"
              disabled={saving}
              onClick={() => void handleClearTracker()}
            >
              Clear tracker
            </button>
          ) : null}
          <button
            type="button"
            disabled={saveDisabled}
            onClick={() => void handleSave()}
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

export interface AdminSectionProps {
  user: User | null;
  adminUsers: AdminUserRecord[];
  setAdminUsers: (users: AdminUserRecord[] | ((current: AdminUserRecord[]) => AdminUserRecord[])) => void;
  adminFeedback: { type: "success" | "error"; text: string } | null;
  saveAdminUser: (userRecord: AdminUserRecord) => void;
  deleteAdminUser: (userRecord: AdminUserRecord) => void;
  clearAdminUserDevice: (userId: number) => void;
  updateUserCredentials: (userId: number, payload: { username?: string; password?: string }) => Promise<void>;
  adminSites: AdminSiteRecord[];
  setAdminSites: (sites: AdminSiteRecord[] | ((current: AdminSiteRecord[]) => AdminSiteRecord[])) => void;
  adminSitesFeedback: { type: "success" | "error" | "pending"; text: string } | null;
  saveAdminSite: (siteRecord: AdminSiteRecord) => void;
  deleteAdminSite: (siteRecord: AdminSiteRecord) => void;
  rescanAdminFlightSites: () => void;
  scanIgcForNewSites: () => void;
  siteSettings: SiteSettingsRecord;
  setSiteSettings: (settings: SiteSettingsRecord | ((current: SiteSettingsRecord) => SiteSettingsRecord)) => void;
  siteSettingsFeedback: { type: "success" | "error"; text: string } | null;
  saveSiteSettings: () => void;
  debugStatus: DebugStatusResponse | null;
  refreshDebugStatus: () => void;
  mapOverlayConfig: MapOverlayConfigRecord;
  setMapOverlayConfig: (config: MapOverlayConfigRecord | ((current: MapOverlayConfigRecord) => MapOverlayConfigRecord)) => void;
  mapOverlayConfigFeedback: { type: "success" | "error"; text: string } | null;
  saveMapOverlayConfig: () => void;
  token: string;
  apiBase: string;
}

export default function AdminSection(props: AdminSectionProps) {
  const {
    user,
    adminUsers,
    setAdminUsers,
    adminFeedback,
    saveAdminUser,
    deleteAdminUser,
    updateUserCredentials,
    adminSites,
    setAdminSites,
    adminSitesFeedback,
    saveAdminSite,
    deleteAdminSite,
    rescanAdminFlightSites,
    scanIgcForNewSites,
    siteSettings,
    setSiteSettings,
    siteSettingsFeedback,
    saveSiteSettings,
    debugStatus,
    refreshDebugStatus,
    mapOverlayConfig,
    setMapOverlayConfig,
    mapOverlayConfigFeedback,
    saveMapOverlayConfig,
    token,
    apiBase,
  } = props;
  const [activeTab, setActiveTab] = useState<AdminTab>("platform_users");
  const [meshNodes, setMeshNodes] = useState<MeshNode[]>([]);
  const [userSearch, setUserSearch] = useState("");
  const [userSortField, setUserSortField] = useState<UserSortField>("last_name");
  const [userSortDir, setUserSortDir] = useState<SortDir>("asc");
  const [selectedUserIds, setSelectedUserIds] = useState<Record<number, boolean>>({});
  const [editingCredentials, setEditingCredentials] = useState<AdminUserRecord | null>(null);
  const [credentialsUsername, setCredentialsUsername] = useState("");
  const [credentialsPassword, setCredentialsPassword] = useState("");
  const [credentialsSaving, setCredentialsSaving] = useState(false);
  const [credentialsError, setCredentialsError] = useState<string | null>(null);
  const [editingMeshDevice, setEditingMeshDevice] = useState<{ user: AdminUserRecord; device: MeshDeviceRecord | null } | null>(null);
  const [expandedUserIds, setExpandedUserIds] = useState<Record<number, boolean>>({});
  const [meshActionFeedback, setMeshActionFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [faaCredentials, setFaaCredentials] = useState<FaaCredentialsRecord>(DEFAULT_FAA_CREDENTIALS);
  const [faaClientId, setFaaClientId] = useState("");
  const [faaClientSecret, setFaaClientSecret] = useState("");
  const [faaFeedback, setFaaFeedback] = useState<{ type: "success" | "error" | "pending"; text: string } | null>(null);
  const [faaLoading, setFaaLoading] = useState(false);
  const [cloudflareDdnsFeedback, setCloudflareDdnsFeedback] = useState<{ type: "success" | "error" | "pending"; text: string } | null>(null);
  const [cloudflareDdnsLoading, setCloudflareDdnsLoading] = useState(false);
  const mqttBrokerMode = normalizeMqttBrokerMode(siteSettings.mqtt_broker_mode);

  const toggleUserSort = useCallback((field: UserSortField) => {
    setUserSortField((prev) => {
      if (prev === field) {
        setUserSortDir((d) => (d === "asc" ? "desc" : "asc"));
        return prev;
      }
      setUserSortDir("asc");
      return field;
    });
  }, []);

  const filteredSortedUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase();
    let list = adminUsers;
    if (q) {
      list = list.filter((u) => {
        const hay = `${u.first_name ?? ""} ${u.last_name ?? ""} ${u.full_name} ${u.username} ${u.email ?? ""} ${u.competition_number ?? ""} ${u.role}`.toLowerCase();
        return hay.includes(q);
      });
    }
    return [...list].sort((a, b) => {
      const dir = userSortDir === "asc" ? 1 : -1;
      switch (userSortField) {
        case "first_name":
          return dir * (a.first_name ?? a.full_name).localeCompare(b.first_name ?? b.full_name);
        case "last_name":
          return dir * (a.last_name ?? "").localeCompare(b.last_name ?? "");
        case "username":
          return dir * a.username.localeCompare(b.username);
        case "role": {
          const order: Record<string, number> = { admin: 0, organizer: 1, pilot: 2 };
          return dir * ((order[a.role] ?? 3) - (order[b.role] ?? 3));
        }
        case "status":
          return dir * (Number(b.is_active) - Number(a.is_active));
        default:
          return 0;
      }
    });
  }, [adminUsers, userSearch, userSortField, userSortDir]);

  const [selectedSiteId, setSelectedSiteId] = useState<number | null>(null);
  const [sitePreviewFitNonce, setSitePreviewFitNonce] = useState(0);
  const [siteMatchRadiusInput, setSiteMatchRadiusInput] = useState(() => siteSettings.site_match_radius_m.toLocaleString());
  const [isEditingSiteMatchRadius, setIsEditingSiteMatchRadius] = useState(false);

  useEffect(() => {
    if (!adminSites.length) {
      setSelectedSiteId(null);
      return;
    }
    if (selectedSiteId == null || !adminSites.some((site) => site.id === selectedSiteId)) {
      setSelectedSiteId(adminSites[0].id);
    }
  }, [adminSites, selectedSiteId]);

  useEffect(() => {
    if (!isEditingSiteMatchRadius) {
      setSiteMatchRadiusInput(siteSettings.site_match_radius_m.toLocaleString());
    }
  }, [isEditingSiteMatchRadius, siteSettings.site_match_radius_m]);

  const loadFaaCredentials = useCallback(async () => {
    setFaaLoading(true);
    setFaaFeedback(null);
    try {
      const res = await fetch(`${apiBase}/api/admin/integrations/faa_notams`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? `Server error ${res.status}`);
      }
      setFaaCredentials((await res.json()) as FaaCredentialsRecord);
    } catch (caught) {
      setFaaFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not load FAA credentials." });
    } finally {
      setFaaLoading(false);
    }
  }, [apiBase, token]);

  useEffect(() => {
    if (activeTab !== "faa_credentials") return;
    void loadFaaCredentials();
  }, [activeTab, loadFaaCredentials]);

  async function saveFaaCredentials() {
    setFaaLoading(true);
    setFaaFeedback({ type: "pending", text: "Saving FAA credentials..." });
    try {
      const payload: Record<string, string | boolean> = {
        enabled: faaCredentials.enabled,
        base_url: faaCredentials.base_url,
        client_id_header: faaCredentials.client_id_header,
        client_secret_header: faaCredentials.client_secret_header,
      };
      if (faaClientId.trim()) payload.client_id = faaClientId.trim();
      if (faaClientSecret.trim()) payload.client_secret = faaClientSecret.trim();
      const res = await fetch(`${apiBase}/api/admin/integrations/faa_notams`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? `Server error ${res.status}`);
      }
      setFaaCredentials((await res.json()) as FaaCredentialsRecord);
      setFaaClientId("");
      setFaaClientSecret("");
      setFaaFeedback({ type: "success", text: "FAA credentials saved." });
    } catch (caught) {
      setFaaFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not save FAA credentials." });
    } finally {
      setFaaLoading(false);
    }
  }

  async function clearFaaCredentials() {
    const confirmed = window.confirm("Clear saved FAA client ID and client secret?");
    if (!confirmed) return;
    setFaaLoading(true);
    setFaaFeedback({ type: "pending", text: "Clearing FAA credentials..." });
    try {
      const res = await fetch(`${apiBase}/api/admin/integrations/faa_notams`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          enabled: false,
          base_url: faaCredentials.base_url,
          client_id_header: faaCredentials.client_id_header,
          client_secret_header: faaCredentials.client_secret_header,
          clear_credentials: true,
        }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? `Server error ${res.status}`);
      }
      setFaaCredentials((await res.json()) as FaaCredentialsRecord);
      setFaaClientId("");
      setFaaClientSecret("");
      setFaaFeedback({ type: "success", text: "Saved FAA credentials cleared." });
    } catch (caught) {
      setFaaFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not clear FAA credentials." });
    } finally {
      setFaaLoading(false);
    }
  }

  async function testFaaCredentials() {
    setFaaLoading(true);
    setFaaFeedback({ type: "pending", text: "Testing FAA credentials..." });
    try {
      const res = await fetch(`${apiBase}/api/admin/integrations/faa_notams/test`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? `Server error ${res.status}`);
      }
      const next = (await res.json()) as FaaCredentialsRecord;
      setFaaCredentials(next);
      setFaaFeedback({
        type: next.last_test_status === "success" ? "success" : "error",
        text: next.last_test_message ?? "FAA credential test completed.",
      });
    } catch (caught) {
      setFaaFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not test FAA credentials." });
    } finally {
      setFaaLoading(false);
    }
  }

  async function checkCloudflareDdns() {
    setCloudflareDdnsLoading(true);
    setCloudflareDdnsFeedback({ type: "pending", text: "Checking Cloudflare DNS..." });
    try {
      const res = await fetch(`${apiBase}/api/site-settings/cloudflare-ddns/check`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? `Server error ${res.status}`);
      }
      const next = (await res.json()) as SiteSettingsRecord;
      setSiteSettings({
        ...next,
        cloudflare_ddns_api_token: null,
        cloudflare_ddns_clear_api_token: false,
      });
      setCloudflareDdnsFeedback({
        type: next.cloudflare_ddns_last_error ? "error" : "success",
        text: next.cloudflare_ddns_last_error ?? next.cloudflare_ddns_last_update_result ?? "Cloudflare DNS check completed.",
      });
    } catch (caught) {
      setCloudflareDdnsFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not check Cloudflare DNS." });
    } finally {
      setCloudflareDdnsLoading(false);
    }
  }

  const loadMeshNodes = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/api/admin/mesh-nodes?minutes=60`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
      if (res.ok) {
        setMeshNodes((await res.json()) as MeshNode[]);
      }
    } catch {
      // Keep the last known mesh-node data visible if an auto-refresh fails.
    }
  }, [apiBase, token]);

  useEffect(() => {
    if (activeTab !== "live_tracking") return;
    refreshDebugStatus();
    const interval = setInterval(() => {
      refreshDebugStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, [activeTab, refreshDebugStatus]);

  useEffect(() => {
    if (activeTab !== "live_tracking") return;
    void loadMeshNodes();
    const interval = setInterval(() => { void loadMeshNodes(); }, 10_000);
    return () => {
      clearInterval(interval);
    };
  }, [activeTab, loadMeshNodes]);

  function applyAdminUserUpdate(updatedUser: AdminUserRecord) {
    setAdminUsers((current) =>
      current.map((entry) => (entry.id === updatedUser.id ? updatedUser : entry)),
    );
  }

  async function setAdminUserPilotTracker(account: AdminUserRecord, meshDeviceId: string | null) {
    setMeshActionFeedback(null);
    try {
      const res = await fetch(`${apiBase}/api/auth/users/${account.id}/mesh-devices/tracking`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ mesh_device_id: meshDeviceId }),
      });
      if (!res.ok) {
        const data = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail ?? `Server error ${res.status}`);
      }
      const updated = (await res.json()) as AdminUserRecord;
      applyAdminUserUpdate(updated);
      setMeshActionFeedback({
        type: "success",
        text: meshDeviceId ? "Pilot tracker updated." : "Pilot tracker cleared.",
      });
    } catch (caught) {
      setMeshActionFeedback({
        type: "error",
        text: caught instanceof Error ? caught.message : "Could not update pilot tracker.",
      });
    }
  }

  const selectedSite = useMemo(
    () => adminSites.find((site) => site.id === selectedSiteId) ?? null,
    [adminSites, selectedSiteId],
  );
  const previewTurnpoints = useMemo<MapTurnpoint[]>(
    () =>
      selectedSite
        ? [
            {
              id: selectedSite.id,
              name: selectedSite.name || "Site",
              code: selectedSite.city_state || null,
              latitude: selectedSite.latitude,
              longitude: selectedSite.longitude,
            },
          ]
        : [],
    [selectedSite],
  );
  const previewTaskPoints = useMemo<MapTaskPoint[]>(
    () =>
      selectedSite
        ? [
            {
              position: 1,
              point_type: "site_match_radius",
              radius_m: siteSettings.site_match_radius_m,
              name: selectedSite.name || "Site",
              latitude: selectedSite.latitude,
              longitude: selectedSite.longitude,
            },
          ]
        : [],
    [selectedSite, siteSettings.site_match_radius_m],
  );

  function addSiteDraft() {
    setAdminSites((current) => [
      ...current,
      {
        id: -Date.now(),
        name: "",
        city_state: "",
        latitude: 0,
        longitude: 0,
        is_active: true,
        flight_count: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    ]);
  }

  function focusSitePreview(siteId: number) {
    setSelectedSiteId(siteId);
    setSitePreviewFitNonce((current) => current + 1);
  }

  function commitSiteMatchRadius(rawValue: string) {
    const digitsOnly = rawValue.replace(/[^0-9]/g, "");
    const nextRadius = Math.max(1, Number(digitsOnly || 1));
    setSiteSettings((current) => ({
      ...current,
      site_match_radius_m: nextRadius,
    }));
    setSiteMatchRadiusInput(nextRadius.toLocaleString());
  }

  return (
    <div className="section-stack">
      <div className="tab-row">
        <button
          type="button"
          className={activeTab === "platform_users" ? "tab-button active" : "tab-button"}
          onClick={() => setActiveTab("platform_users")}
        >
          Platform users
        </button>
        <button
          type="button"
          className={activeTab === "site_settings" ? "tab-button active" : "tab-button"}
          onClick={() => setActiveTab("site_settings")}
        >
          Site settings
        </button>
        <button
          type="button"
          className={activeTab === "sites_database" ? "tab-button active" : "tab-button"}
          onClick={() => setActiveTab("sites_database")}
        >
          Flying Sites
        </button>
        <button
          type="button"
          className={activeTab === "map_config" ? "tab-button active" : "tab-button"}
          onClick={() => setActiveTab("map_config")}
        >
          Map overlays
        </button>
        <button
          type="button"
          className={activeTab === "faa_credentials" ? "tab-button active" : "tab-button"}
          onClick={() => setActiveTab("faa_credentials")}
        >
          FAA credentials
        </button>
        <button
          type="button"
          className={activeTab === "meshtastic" ? "tab-button active" : "tab-button"}
          onClick={() => setActiveTab("meshtastic")}
        >
          Meshtastic
        </button>
        <button
          type="button"
          className={activeTab === "live_tracking" ? "tab-button active" : "tab-button"}
          onClick={() => setActiveTab("live_tracking")}
        >
          Live Tracking Debugging
        </button>
      </div>
      {activeTab === "platform_users" ? (
        <SectionCard title="Platform users">
          <div className="stack form-block">
            {adminFeedback ? <div className={`status-chip ${adminFeedback.type}`}>{adminFeedback.text}</div> : null}
            {meshActionFeedback ? <div className={`status-chip ${meshActionFeedback.type}`}>{meshActionFeedback.text}</div> : null}
            <div className="admin-users-search-row">
              <input
                type="text"
                placeholder="Search users by name, email, comp #..."
                value={userSearch}
                onChange={(event) => setUserSearch(event.target.value)}
                className="admin-users-search"
              />
              <span className="hint">{filteredSortedUsers.length} of {adminUsers.length} users</span>
              {(() => {
                const selectedCount = Object.keys(selectedUserIds).filter((k) => selectedUserIds[Number(k)]).length;
                return selectedCount > 0 ? (
                  <button
                    type="button"
                    className="ghost-button danger-button"
                    onClick={() => {
                      if (!window.confirm(`Delete ${selectedCount} user(s)?`)) return;
                      const ids = Object.keys(selectedUserIds).filter((k) => selectedUserIds[Number(k)]).map(Number);
                      for (const id of ids) {
                        const target = adminUsers.find((u) => u.id === id);
                        if (target && target.id !== user?.id) void deleteAdminUser(target);
                      }
                      setSelectedUserIds({});
                    }}
                  >
                    Delete selected ({selectedCount})
                  </button>
                ) : null;
              })()}
            </div>
            <div className="participant-table-wrap admin-users-table-wrap">
              <table className="participant-table admin-users-table">
                <thead>
                  <tr>
                    <th className="admin-users-select-column">
                      <input
                        type="checkbox"
                        aria-label="Select all users"
                        checked={filteredSortedUsers.length > 0 && filteredSortedUsers.every((u) => selectedUserIds[u.id])}
                        ref={(el) => {
                          if (el) {
                            const count = filteredSortedUsers.filter((u) => selectedUserIds[u.id]).length;
                            el.indeterminate = count > 0 && count < filteredSortedUsers.length;
                          }
                        }}
                        onChange={(event) => {
                          if (event.target.checked) {
                            setSelectedUserIds((current) => ({
                              ...current,
                              ...Object.fromEntries(filteredSortedUsers.map((u) => [u.id, true])),
                            }));
                          } else {
                            setSelectedUserIds({});
                          }
                        }}
                      />
                    </th>
                    <SortHeader field="first_name" label="First" current={userSortField} dir={userSortDir} toggle={toggleUserSort} />
                    <SortHeader field="last_name" label="Last" current={userSortField} dir={userSortDir} toggle={toggleUserSort} />
                    <SortHeader field="username" label="Username" current={userSortField} dir={userSortDir} toggle={toggleUserSort} />
                    <SortHeader field="role" label="Role" current={userSortField} dir={userSortDir} toggle={toggleUserSort} />
                    <SortHeader field="status" label="Status" current={userSortField} dir={userSortDir} toggle={toggleUserSort} />
                    <th>Mesh Device</th>
                    <th className="participant-table-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSortedUsers.length ? (
                    filteredSortedUsers.map((account) => {
                      const meshDevices = account.mesh_devices ?? [];
                      const primaryMeshDevice = meshDevices.find((device) => device.device_id === account.mesh_device_id) ?? meshDevices[0] ?? null;
                      const hasMultipleMeshDevices = meshDevices.length > 1;
                      const meshExpanded = expandedUserIds[account.id] ?? false;
                      return (
                      <Fragment key={account.id}>
                      <tr>
                        <td className="admin-users-select-column">
                          <input
                            type="checkbox"
                            aria-label={`Select ${account.full_name}`}
                            checked={selectedUserIds[account.id] ?? false}
                            onChange={(event) => setSelectedUserIds((current) => ({ ...current, [account.id]: event.target.checked }))}
                          />
                        </td>
                        <td>{account.first_name ?? account.full_name}</td>
                        <td>{account.last_name ?? ""}</td>
                        <td>{account.username}</td>
                        <td>
                          <select
                            value={account.role}
                            disabled={account.id === user?.id}
                            onChange={(event) => {
                              const updated = { ...account, role: event.target.value as AdminUserRecord["role"] };
                              setAdminUsers((current) => current.map((entry) => entry.id === account.id ? updated : entry));
                              void saveAdminUser(updated);
                            }}
                          >
                            <option value="admin">Admin</option>
                            <option value="organizer">Organizer</option>
                            <option value="pilot">Pilot</option>
                          </select>
                        </td>
                        <td>
                          <label className="task-advanced-toggle">
                            <input
                              type="checkbox"
                              checked={account.is_active}
                              disabled={account.id === user?.id}
                              onChange={(event) => {
                                const updated = { ...account, is_active: event.target.checked };
                                setAdminUsers((current) => current.map((entry) => entry.id === account.id ? updated : entry));
                                void saveAdminUser(updated);
                              }}
                            />
                            <span>{account.is_active ? "Active" : "Disabled"}</span>
                          </label>
                        </td>
                        <td>
                          <div className="admin-mesh-summary">
                            {hasMultipleMeshDevices ? (
                              <button
                                type="button"
                                className="ghost-button admin-mesh-expand-button"
                                aria-label={meshExpanded ? `Collapse mesh devices for ${account.full_name}` : `Expand mesh devices for ${account.full_name}`}
                                aria-expanded={meshExpanded}
                                onClick={() => setExpandedUserIds((current) => ({ ...current, [account.id]: !meshExpanded }))}
                              >
                                {meshExpanded ? "-" : "+"}
                              </button>
                            ) : null}
                            {primaryMeshDevice ? (
                              <>
                                <input
                                  type="checkbox"
                                  checked={account.mesh_device_id === primaryMeshDevice.device_id}
                                  title="Pilot tracker"
                                  aria-label={`Use ${primaryMeshDevice.device_id} as pilot tracker`}
                                  onChange={(event) => void setAdminUserPilotTracker(account, event.target.checked ? primaryMeshDevice.device_id : null)}
                                />
                                <span
                                  title="Aervyx pilot tracker assignment. Other mesh devices can still relay packets."
                                  className="admin-mesh-device-id"
                                >
                                  {primaryMeshDevice.device_id}
                                </span>
                                <span className="hint">{hasMultipleMeshDevices ? `${meshDevices.length} devices` : meshPurposeLabel(primaryMeshDevice.purpose)}</span>
                                <button
                                  type="button"
                                  className="ghost-button"
                                  title="Edit mesh device"
                                  onClick={() => setEditingMeshDevice({ user: account, device: primaryMeshDevice })}
                                >
                                  Edit
                                </button>
                              </>
                            ) : (
                              <>
                                <span className="admin-mesh-device-id muted">-</span>
                                <button
                                  type="button"
                                  className="ghost-button"
                                  title="Add pilot tracker pairing"
                                  onClick={() => setEditingMeshDevice({ user: account, device: null })}
                                >
                                  Add tracker
                                </button>
                              </>
                            )}
                          </div>
                        </td>
                        <td className="participant-table-actions">
                          <div className="compact-slot-actions">
                            <button
                              type="button"
                              className="ghost-button"
                              onClick={() => {
                                setEditingCredentials(account);
                                setCredentialsUsername(account.username);
                                setCredentialsPassword("");
                                setCredentialsError(null);
                              }}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="ghost-button danger-button"
                              disabled={account.id === user?.id}
                              onClick={() => {
                                if (!window.confirm(`Delete ${account.full_name}?`)) return;
                                void deleteAdminUser(account);
                              }}
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                      {hasMultipleMeshDevices && meshExpanded ? (
                        <tr className="admin-mesh-detail-row">
                          <td colSpan={8}>
                            <table className="admin-mesh-devices-table">
                              <thead>
                                <tr>
                                  <th>Pilot Tracker</th>
                                  <th>Mesh Device ID</th>
                                  <th>Purpose</th>
                                  <th>Label</th>
                                  <th>Actions</th>
                                </tr>
                              </thead>
                              <tbody>
                                {meshDevices.map((device) => (
                                  <tr key={device.device_id}>
                                    <td>
                                      <input
                                        type="checkbox"
                                        checked={account.mesh_device_id === device.device_id}
                                        aria-label={`${account.mesh_device_id === device.device_id ? "Clear" : "Use"} ${device.device_id} as pilot tracker`}
                                        onChange={(event) => void setAdminUserPilotTracker(account, event.target.checked ? device.device_id : null)}
                                      />
                                    </td>
                                    <td className="admin-mesh-device-id">{device.device_id}</td>
                                    <td>{meshPurposeLabel(device.purpose)}</td>
                                    <td>{device.label}</td>
                                    <td>
                                      <button
                                        type="button"
                                        className="ghost-button"
                                        onClick={() => setEditingMeshDevice({ user: account, device })}
                                      >
                                        Edit
                                      </button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </td>
                        </tr>
                      ) : null}
                      </Fragment>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={8} className="participant-table-empty">{userSearch ? "No matching users." : "No platform users found."}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {editingCredentials ? (
              <div className="confirm-overlay" onClick={() => { if (!credentialsSaving) setEditingCredentials(null); }}>
                <div className="confirm-dialog confirm-dialog-wide" onClick={(e) => e.stopPropagation()}>
                  <strong>Edit credentials — {editingCredentials.full_name || editingCredentials.username}</strong>
                  <label className="stack compact">
                    <span>Username</span>
                    <input value={credentialsUsername} onChange={(event) => setCredentialsUsername(event.target.value)} />
                  </label>
                  <label className="stack compact">
                    <span>New password (leave blank to keep current)</span>
                    <input type="password" value={credentialsPassword} onChange={(event) => setCredentialsPassword(event.target.value)} autoComplete="new-password" />
                  </label>
                  {credentialsError ? <div className="status-chip error">{credentialsError}</div> : null}
                  <div className="confirm-actions">
                    <button type="button" className="ghost-button" disabled={credentialsSaving} onClick={() => setEditingCredentials(null)}>Cancel</button>
                    <button
                      type="button"
                      disabled={credentialsSaving}
                      onClick={async () => {
                        if (!editingCredentials) return;
                        setCredentialsSaving(true);
                        setCredentialsError(null);
                        try {
                          const payload: { username?: string; password?: string } = {};
                          const nextUsername = credentialsUsername.trim();
                          if (nextUsername && nextUsername !== editingCredentials.username) payload.username = nextUsername;
                          if (credentialsPassword.trim()) payload.password = credentialsPassword.trim();
                          if (Object.keys(payload).length === 0) {
                            setEditingCredentials(null);
                            return;
                          }
                          await updateUserCredentials(editingCredentials.id, payload);
                          setEditingCredentials(null);
                        } catch (caught) {
                          setCredentialsError(caught instanceof Error ? caught.message : "Could not update credentials.");
                        } finally {
                          setCredentialsSaving(false);
                        }
                      }}
                    >
                      {credentialsSaving ? "Saving…" : "Save"}
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
            {editingMeshDevice ? (
              <MeshDeviceEditModal
                user={editingMeshDevice.user}
                device={editingMeshDevice.device}
                apiBase={apiBase}
                token={token}
                onSaved={(updatedUser) => {
                  applyAdminUserUpdate(updatedUser);
                  setEditingMeshDevice(null);
                }}
                onClose={() => setEditingMeshDevice(null)}
              />
            ) : null}
          </div>
        </SectionCard>
      ) : activeTab === "sites_database" ? (
        <SectionCard title="Flying Sites">
          <div className="stack form-block compact-clusters">
            {adminSitesFeedback ? <div className={`status-chip ${adminSitesFeedback.type}`}>{adminSitesFeedback.text}</div> : null}
            {siteSettingsFeedback ? <div className={`status-chip ${siteSettingsFeedback.type}`}>{siteSettingsFeedback.text}</div> : null}
            <div className="logbook-bulk-actions">
              <div className="button-row compact">
                <button type="button" className="ghost-button" onClick={addSiteDraft}>
                  Add site
                </button>
                <button type="button" className="ghost-button" onClick={() => void saveSiteSettings()}>
                  Save matching settings
                </button>
                <button
                  type="button"
                  className="ghost-button"
                  onClick={() => {
                    const confirmed = window.confirm("Scan all IGC files for new takeoff sites? This will create new sites for any unique takeoff locations not already in the database.");
                    if (confirmed) {
                      void scanIgcForNewSites();
                    }
                  }}
                >
                  Scan IGC for new sites
                </button>
                <button
                  type="button"
                  className="ghost-button danger-button"
                  onClick={() => {
                    const confirmed = window.confirm("Rescan all unmatched IGC-backed flights for site matches?");
                    if (confirmed) {
                      void rescanAdminFlightSites();
                    }
                  }}
                >
                  Rescan all flights for site match
                </button>
              </div>
              <label className="stack compact logbook-site-radius-control">
                <span>Site match radius (m)</span>
                <input
                  type="text"
                  inputMode="numeric"
                  value={siteMatchRadiusInput}
                  onFocus={() => {
                    setIsEditingSiteMatchRadius(true);
                    setSiteMatchRadiusInput(String(siteSettings.site_match_radius_m));
                  }}
                  onChange={(event) => {
                    setSiteMatchRadiusInput(event.target.value.replace(/[^0-9]/g, ""));
                  }}
                  onBlur={() => {
                    setIsEditingSiteMatchRadius(false);
                    commitSiteMatchRadius(siteMatchRadiusInput);
                  }}
                />
              </label>
            </div>
            <div className="admin-sites-layout">
              <div className="results-table-wrap site-database-table-wrap">
                <table className="results-table logbook-table site-database-table">
                  <colgroup>
                    <col className="site-database-site-column" />
                    <col className="site-database-city-column" />
                    <col className="site-database-flights-column" />
                    <col className="site-database-actions-column" />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Site name</th>
                      <th>City / State</th>
                      <th>Flights</th>
                      <th className="participant-table-actions">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {adminSites.length ? (
                      adminSites.map((site) => {
                        const isSelected = selectedSiteId === site.id;
                        return (
                          <tr
                            key={site.id}
                            className={isSelected ? "site-database-row selected" : "site-database-row"}
                            onClick={() => focusSitePreview(site.id)}
                          >
                            <td className="site-database-name-cell">
                              <input
                                value={site.name}
                                placeholder="Site name"
                                onChange={(event) =>
                                  setAdminSites((current) =>
                                    current.map((entry) => (entry.id === site.id ? { ...entry, name: event.target.value } : entry)),
                                  )
                                }
                              />
                            </td>
                            <td className="site-database-city-cell">
                              <input
                                value={site.city_state}
                                placeholder="City / State"
                                onChange={(event) =>
                                  setAdminSites((current) =>
                                    current.map((entry) => (entry.id === site.id ? { ...entry, city_state: event.target.value } : entry)),
                                  )
                                }
                              />
                            </td>
                            <td className="site-database-flight-count">{(site.flight_count ?? 0).toLocaleString()}</td>
                            <td className="participant-table-actions">
                              <div className="compact-slot-actions site-database-actions">
                                <button type="button" className="ghost-button" onClick={() => void saveAdminSite(site)}>
                                  Save
                                </button>
                                <button
                                  type="button"
                                  className="ghost-button danger-button"
                                  onClick={() => {
                                    const confirmed = window.confirm(`Delete ${site.name || "this site"}?`);
                                    if (confirmed) {
                                      void deleteAdminSite(site);
                                    }
                                  }}
                                >
                                  Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })
                    ) : (
                      <tr>
                        <td colSpan={4} className="participant-table-empty">No flying sites yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <div className="logbook-site-preview">
                <div className="section-card-header">
                  <div>
                    <h3>Map preview</h3>
                    <p className="hint">{selectedSite ? "Visual confirmation for the selected site." : "Select a site to preview its map location."}</p>
                  </div>
                </div>
                <div className="logbook-site-preview-map">
                  {selectedSite ? (
                    <TaskMap
                      key={selectedSite ? `${selectedSite.id}:${sitePreviewFitNonce}` : "site-preview-empty"}
                      turnpoints={previewTurnpoints}
                      taskPoints={previewTaskPoints}
                      optimizedRoute={[]}
                      legMetrics={[]}
                      track={null}
                      editable={false}
                      fitKey={selectedSite ? `${selectedSite.id}:${sitePreviewFitNonce}` : "site-preview-empty"}
                      fitMaxZoom={11}
                      overlayConfig={mapOverlayConfig.config?.admin_site_preview}
                    />
                  ) : (
                    <div className="logbook-site-preview-label empty">
                      <strong>No site selected</strong>
                      <span>Select a site row to preview it on the map.</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </SectionCard>
      ) : activeTab === "map_config" ? (
        <SectionCard title="Map overlay configuration">
          <div className="stack form-block">
            {mapOverlayConfigFeedback ? <div className={`status-chip ${mapOverlayConfigFeedback.type}`}>{mapOverlayConfigFeedback.text}</div> : null}
            <p className="hint">Toggle overlays and controls for each map context. Changes take effect on next page load.</p>
            <div style={{ overflowX: "auto" }}>
              <table className="admin-map-config-table">
                <thead>
                  <tr>
                    <th>Feature</th>
                    {MAP_CONTEXTS.map((ctx) => (
                      <th key={ctx.key}>{ctx.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {MAP_GROUPS.map((group) => (
                    <tr key={group.key}>
                      <td>{group.label}</td>
                      {MAP_CONTEXTS.map((ctx) => {
                        const native = (group.maps as readonly string[]).includes(ctx.key);
                        const groupConfig = mapOverlayConfig.config?.groups?.[ctx.key];
                        const checked = groupConfig?.[group.key] === true || (native && groupConfig?.[group.key] !== false);
                        return (
                          <td key={ctx.key} style={{ textAlign: "center" }}>
                            {native ? (
                              <input
                                type="checkbox"
                                checked={checked}
                                onChange={() => {
                                  setMapOverlayConfig((prev) => ({
                                    ...prev,
                                    config: {
                                      ...prev.config,
                                      schema_version: 2,
                                      groups: {
                                        ...(prev.config?.groups ?? {}),
                                        [ctx.key]: {
                                          ...(prev.config?.groups?.[ctx.key] ?? {}),
                                          [group.key]: !checked,
                                        },
                                      },
                                    },
                                  }));
                                }}
                              />
                            ) : (
                              <span aria-hidden="true">-</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="button-row">
              <button type="button" className="primary-button" onClick={() => void saveMapOverlayConfig()}>
                Save map overlay config
              </button>
            </div>
          </div>
        </SectionCard>
      ) : activeTab === "meshtastic" ? (
        <SectionCard title="Meshtastic Configuration">
          <div className="stack form-block compact-clusters">
            <MeshProfilesTable siteSettings={siteSettings} setSiteSettings={setSiteSettings} />
            <fieldset className="fieldset-cluster">
              <legend>Fixed Gateway MQTT</legend>
              <div className="cluster-stack">
                <label className="stack compact">
                  <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <input
                      type="checkbox"
                      checked={siteSettings.mqtt_enabled ?? false}
                      onChange={(event) =>
                        setSiteSettings((current) => ({
                          ...current,
                          mqtt_enabled: event.target.checked,
                        }))
                      }
                    />
                    Enable fixed gateway MQTT
                  </span>
                </label>
                <label className="stack compact">
                  <span>Gateway broker mode</span>
                  <select
                    value={mqttBrokerMode}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        mqtt_broker_mode: event.target.value as MqttBrokerMode,
                      }))
                    }
                  >
                    <option value="local_mosquitto">Local Mosquitto on Aervyx machine</option>
                    <option value="cloud_vm">Cloud VM broker</option>
                  </select>
                </label>
                <label className="stack compact">
                  <span>Gateway MQTT host</span>
                  <input
                    type="text"
                    placeholder={mqttBrokerMode === "local_mosquitto" ? "LAN IP or DNS radios can reach" : "mqtt.example.com"}
                    value={siteSettings.mqtt_host ?? ""}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        mqtt_host: event.target.value || null,
                      }))
                    }
                  />
                </label>
                <label className="stack compact">
                  <span>Gateway MQTT port</span>
                  <input
                    type="number"
                    min={1}
                    max={65535}
                    step={1}
                    value={siteSettings.mqtt_port ?? 1883}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        mqtt_port: Number(event.target.value || 1883),
                      }))
                    }
                  />
                </label>
                <label className="stack compact">
                  <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <input
                      type="checkbox"
                      checked={siteSettings.mqtt_tls_enabled ?? false}
                      onChange={(event) =>
                        setSiteSettings((current) => ({
                          ...current,
                          mqtt_tls_enabled: event.target.checked,
                        }))
                      }
                    />
                    TLS enabled
                  </span>
                </label>
                <label className="stack compact">
                  <span>Gateway MQTT username</span>
                  <input
                    type="text"
                    placeholder="Fleet username"
                    value={siteSettings.mqtt_username ?? ""}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        mqtt_username: event.target.value || null,
                      }))
                    }
                  />
                </label>
                <label className="stack compact">
                  <span>Gateway MQTT password</span>
                  <input
                    type="password"
                    placeholder="Fleet password"
                    value={siteSettings.mqtt_password ?? ""}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        mqtt_password: event.target.value || null,
                      }))
                    }
                  />
                </label>
                <label className="stack compact">
                  <span>Topic prefix</span>
                  <input
                    type="text"
                    placeholder="msh"
                    value={siteSettings.mqtt_topic_prefix ?? "msh"}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        mqtt_topic_prefix: event.target.value,
                      }))
                    }
                  />
                </label>
                <label className="stack compact">
                  <span>Channel PSK</span>
                  <input
                    type="text"
                    placeholder="Optional — for encrypted channels"
                    value={siteSettings.mqtt_channel_psk ?? ""}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        mqtt_channel_psk: event.target.value || null,
                      }))
                    }
                  />
                </label>
              </div>
            </fieldset>
            <fieldset className="fieldset-cluster">
              <legend>Cloudflare MQTT DNS Sync</legend>
              <div className="cluster-stack">
                <label className="stack compact">
                  <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <input
                      type="checkbox"
                      checked={siteSettings.cloudflare_ddns_enabled ?? false}
                      onChange={(event) =>
                        setSiteSettings((current) => ({
                          ...current,
                          cloudflare_ddns_enabled: event.target.checked,
                        }))
                      }
                    />
                    Enabled
                  </span>
                </label>
                <label className="stack compact">
                  <span>Cloudflare zone ID</span>
                  <input
                    type="text"
                    placeholder="Zone ID for aervyx.net"
                    value={siteSettings.cloudflare_ddns_zone_id ?? ""}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        cloudflare_ddns_zone_id: event.target.value || null,
                      }))
                    }
                  />
                </label>
                <label className="stack compact">
                  <span>API token</span>
                  <input
                    type="password"
                    placeholder={siteSettings.cloudflare_ddns_api_token_configured ? "Token saved; enter a new token to replace" : "Cloudflare DNS Edit token"}
                    value={siteSettings.cloudflare_ddns_api_token ?? ""}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        cloudflare_ddns_api_token: event.target.value || null,
                        cloudflare_ddns_clear_api_token: false,
                      }))
                    }
                  />
                </label>
                <label className="stack compact">
                  <span>DNS records</span>
                  <textarea
                    rows={3}
                    value={(siteSettings.cloudflare_ddns_record_names ?? []).join("\n")}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        cloudflare_ddns_record_names: event.target.value
                          .split(/[\n,]/)
                          .map((entry) => entry.trim())
                          .filter(Boolean),
                      }))
                    }
                  />
                </label>
                <label className="stack compact">
                  <span>Check interval (hours)</span>
                  <input
                    type="number"
                    min={1}
                    max={168}
                    step={1}
                    value={siteSettings.cloudflare_ddns_check_interval_hours ?? 12}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        cloudflare_ddns_check_interval_hours: Number(event.target.value || 12),
                      }))
                    }
                  />
                </label>
                <div className="stack compact">
                  <span>Last check</span>
                  <strong>{formatOptionalDateTime(siteSettings.cloudflare_ddns_last_checked_at)}</strong>
                </div>
                <div className="stack compact">
                  <span>Current public IP</span>
                  <strong>{siteSettings.cloudflare_ddns_last_public_ip ?? "Unknown"}</strong>
                </div>
                <div className="stack compact">
                  <span>Status</span>
                  <strong>{siteSettings.cloudflare_ddns_last_error ?? siteSettings.cloudflare_ddns_last_update_result ?? "Not checked yet"}</strong>
                </div>
                <div className="button-row" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                  <button type="button" className="ghost-button" disabled={cloudflareDdnsLoading} onClick={() => void checkCloudflareDdns()}>
                    {cloudflareDdnsLoading ? "Checking..." : "Check now"}
                  </button>
                  {siteSettings.cloudflare_ddns_api_token_configured ? <span className="status-chip success">API token saved</span> : <span className="status-chip pending">API token not saved</span>}
                  {cloudflareDdnsFeedback ? <div className={`status-chip ${cloudflareDdnsFeedback.type}`}>{cloudflareDdnsFeedback.text}</div> : null}
                </div>
              </div>
            </fieldset>
            <div className="button-row" style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <button type="button" onClick={() => void saveSiteSettings()}>
                Save Meshtastic settings
              </button>
              {siteSettingsFeedback ? <div className={`status-chip ${siteSettingsFeedback.type}`}>{siteSettingsFeedback.text}</div> : null}
            </div>
          </div>
        </SectionCard>
      ) : activeTab === "faa_credentials" ? (
        <SectionCard title="FAA credentials">
          <div className="stack form-block compact-clusters">
            {faaFeedback ? <div className={`status-chip ${faaFeedback.type}`}>{faaFeedback.text}</div> : null}
            <div className="fieldset-grid two-up">
              <fieldset className="fieldset-cluster">
                <legend>FAA NOTAMS API</legend>
                <div className="cluster-stack">
                  <label className="stack compact">
                    <span style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <input
                        type="checkbox"
                        checked={faaCredentials.enabled}
                        onChange={(event) =>
                          setFaaCredentials((current) => ({
                            ...current,
                            enabled: event.target.checked,
                          }))
                        }
                      />
                      Enabled
                    </span>
                  </label>
                  <label className="stack compact">
                    <span>FAA API base URL</span>
                    <input
                      type="url"
                      value={faaCredentials.base_url}
                      placeholder="https://api.faa.gov"
                      onChange={(event) =>
                        setFaaCredentials((current) => ({
                          ...current,
                          base_url: event.target.value,
                        }))
                      }
                    />
                  </label>
                  <div className="fieldset-grid two-up">
                    <label className="stack compact">
                      <span>Client ID header</span>
                      <input
                        type="text"
                        value={faaCredentials.client_id_header}
                        placeholder="client_id"
                        onChange={(event) =>
                          setFaaCredentials((current) => ({
                            ...current,
                            client_id_header: event.target.value,
                          }))
                        }
                      />
                    </label>
                    <label className="stack compact">
                      <span>Client secret header</span>
                      <input
                        type="text"
                        value={faaCredentials.client_secret_header}
                        placeholder="client_secret"
                        onChange={(event) =>
                          setFaaCredentials((current) => ({
                            ...current,
                            client_secret_header: event.target.value,
                          }))
                        }
                      />
                    </label>
                  </div>
                </div>
              </fieldset>
              <fieldset className="fieldset-cluster">
                <legend>Credentials</legend>
                <div className="cluster-stack">
                  <label className="stack compact">
                    <span>Client ID</span>
                    <input
                      type="password"
                      value={faaClientId}
                      placeholder={faaCredentials.admin_client_id_configured ? "Configured; leave blank to keep current" : "Enter FAA client ID"}
                      onChange={(event) => setFaaClientId(event.target.value)}
                      autoComplete="off"
                    />
                  </label>
                  <label className="stack compact">
                    <span>Client secret</span>
                    <input
                      type="password"
                      value={faaClientSecret}
                      placeholder={faaCredentials.admin_client_secret_configured ? "Configured; leave blank to keep current" : "Enter FAA client secret"}
                      onChange={(event) => setFaaClientSecret(event.target.value)}
                      autoComplete="off"
                    />
                  </label>
                  <div className="stack compact">
                    <span className="hint">Source: {credentialSourceLabel(faaCredentials.credential_source)}</span>
                    <span className="hint">Client ID: {faaCredentials.client_id_configured ? "configured" : "missing"} / Client secret: {faaCredentials.client_secret_configured ? "configured" : "missing"}</span>
                    {faaCredentials.env_override ? <span className="hint">Environment variables are currently taking precedence.</span> : null}
                  </div>
                </div>
              </fieldset>
            </div>
            <fieldset className="fieldset-cluster">
              <legend>Status</legend>
              <div className="fieldset-grid two-up">
                <div className="stack compact">
                  <span className="hint">Last updated</span>
                  <strong>{formatOptionalDateTime(faaCredentials.updated_at)}</strong>
                </div>
                <div className="stack compact">
                  <span className="hint">Last tested</span>
                  <strong>{formatOptionalDateTime(faaCredentials.last_tested_at)}</strong>
                </div>
                <div className="stack compact">
                  <span className="hint">Test result</span>
                  <strong>{faaCredentials.last_test_status ?? "Not tested"}</strong>
                </div>
                <div className="stack compact">
                  <span className="hint">Message</span>
                  <strong>{faaCredentials.last_test_message ?? "-"}</strong>
                </div>
              </div>
            </fieldset>
            <div className="button-row" style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
              <button type="button" disabled={faaLoading} onClick={() => void saveFaaCredentials()}>
                {faaLoading ? "Working..." : "Save FAA credentials"}
              </button>
              <button type="button" className="ghost-button" disabled={faaLoading} onClick={() => void testFaaCredentials()}>
                Test connection
              </button>
              <button type="button" className="ghost-button danger-button" disabled={faaLoading || (!faaCredentials.admin_client_id_configured && !faaCredentials.admin_client_secret_configured)} onClick={() => void clearFaaCredentials()}>
                Clear credentials
              </button>
              <button type="button" className="ghost-button" disabled={faaLoading} onClick={() => void loadFaaCredentials()}>
                Refresh
              </button>
            </div>
          </div>
        </SectionCard>
      ) : activeTab === "live_tracking" ? (
        <LiveTrackingTab
          debugStatus={debugStatus}
          meshNodes={meshNodes}
          overlayConfig={mapOverlayConfig.config.dashboard_live}
        />
      ) : (
        <SectionCard title="Site settings">
          <div className="stack form-block compact-clusters">
            {siteSettingsFeedback ? <div className={`status-chip ${siteSettingsFeedback.type}`}>{siteSettingsFeedback.text}</div> : null}
            <div className="fieldset-grid two-up">
              <fieldset className="fieldset-cluster">
                <legend>Flight telemetry</legend>
                <div className="cluster-stack">
                  <label className="stack compact">
                    <span>Vertical speed smoothing</span>
                    <input
                      type="number"
                      min={0}
                      max={30}
                      step={1}
                      value={siteSettings.telemetry_vario_smoothing_seconds}
                      onChange={(event) =>
                        setSiteSettings((current) => ({
                          ...current,
                          telemetry_vario_smoothing_seconds: Number(event.target.value || 0),
                        }))
                      }
                    />
                  </label>
                  <label className="stack compact">
                    <span>Altitude smoothing</span>
                    <input
                      type="number"
                      min={0}
                      max={30}
                      step={1}
                      value={siteSettings.telemetry_altitude_smoothing_seconds}
                      onChange={(event) =>
                        setSiteSettings((current) => ({
                          ...current,
                          telemetry_altitude_smoothing_seconds: Number(event.target.value || 0),
                        }))
                      }
                    />
                  </label>
                </div>
              </fieldset>
              <fieldset className="fieldset-cluster">
                <legend>Replay smoothing</legend>
                <div className="cluster-stack">
                  <label className="stack compact">
                    <span>Speed smoothing</span>
                    <input
                      type="number"
                      min={0}
                      max={30}
                      step={1}
                      value={siteSettings.telemetry_speed_smoothing_seconds}
                      onChange={(event) =>
                        setSiteSettings((current) => ({
                          ...current,
                          telemetry_speed_smoothing_seconds: Number(event.target.value || 0),
                        }))
                      }
                    />
                  </label>
                  <label className="stack compact">
                    <span>L/D smoothing</span>
                    <input
                      type="number"
                      min={0}
                      max={30}
                      step={1}
                      value={siteSettings.telemetry_glide_ratio_smoothing_seconds}
                      onChange={(event) =>
                        setSiteSettings((current) => ({
                          ...current,
                          telemetry_glide_ratio_smoothing_seconds: Number(event.target.value || 0),
                        }))
                      }
                    />
                  </label>
                </div>
              </fieldset>
              <fieldset className="fieldset-cluster">
                <legend>Map view</legend>
                <div className="cluster-stack">
                  <label className="stack compact">
                    <span>Maximum map pitch</span>
                    <input
                      type="number"
                      min={0}
                      max={85}
                      step={1}
                      value={siteSettings.max_map_pitch_degrees}
                      onChange={(event) =>
                        setSiteSettings((current) => ({
                          ...current,
                          max_map_pitch_degrees: Number(event.target.value || 0),
                        }))
                      }
                    />
                  </label>
                </div>
              </fieldset>
            </div>
            <p className="hint">Use 0 to disable smoothing. Smoothing values allow 0 to 30 seconds. Maximum map pitch allows 0 to 85 degrees, where 0 is top-down and higher values tilt closer to horizontal.</p>
            <div className="button-row">
              <button type="button" onClick={() => void saveSiteSettings()}>
                Save site settings
              </button>
            </div>
          </div>
        </SectionCard>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  SortHeader helper for admin users table                           */
/* ------------------------------------------------------------------ */

function SortHeader({ field, label, current, dir, toggle }: { field: UserSortField; label: string; current: UserSortField; dir: SortDir; toggle: (f: UserSortField) => void }) {
  const active = current === field;
  const arrow = active ? (dir === "asc" ? " \u25B2" : " \u25BC") : "";
  return (
    <th className={`sortable-th${active ? " active" : ""}`} onClick={() => toggle(field)}>
      {label}{arrow}
    </th>
  );
}

/* ------------------------------------------------------------------ */
/*  Debugging tab helpers + sub-component                             */
/* ------------------------------------------------------------------ */

function relativeTime(isoOrNull: string | null | undefined): string {
  if (!isoOrNull) return "\u2014";
  const diffMs = Date.now() - new Date(isoOrNull).getTime();
  if (diffMs < 0) return "just now";
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

function lastSeenColor(isoOrNull: string | null | undefined): "green" | "orange" | "red" {
  if (!isoOrNull) return "red";
  const diffMs = Date.now() - new Date(isoOrNull).getTime();
  if (diffMs <= 10 * 60_000) return "green";
  if (diffMs <= 6 * 60 * 60_000) return "orange";
  return "red";
}

function meshStatusLabel(status: MeshConnectionStatus | null | undefined): string {
  switch (status) {
    case "live":
      return "Live";
    case "stale":
      return "Stale";
    case "offline":
      return "Offline";
    default:
      return "Never seen";
  }
}

function meshSourcePillLabel(status: MeshConnectionStatus | null | undefined, source?: string | null): string {
  if (status === "never_seen" || !status) return "Never seen";
  if (source === "mesh_relay") return `${meshStatusLabel(status)} via app`;
  if (source === "mqtt_gateway") return `${meshStatusLabel(status)} via MQTT`;
  return `${meshStatusLabel(status)} mesh`;
}

function meshStatusClass(status: MeshConnectionStatus | null | undefined): string {
  if (status === "live") return "";
  if (status === "stale") return " stale";
  return " offline";
}

function meshStatusColor(status: MeshConnectionStatus | null | undefined): string {
  if (status === "live") return "#22c55e";
  if (status === "stale") return "#f59e0b";
  return "#ef4444";
}

function packetTypeLabel(packetType: string | null | undefined): string | null {
  if (!packetType) return null;
  const labels: Record<string, string> = {
    POSITION_APP: "Position",
    NODEINFO_APP: "NodeInfo",
    TELEMETRY_APP: "Telemetry",
    NEIGHBORINFO_APP: "NeighborInfo",
    MAP_REPORT_APP: "MapReport",
    ROUTING_APP: "Routing",
    ENCRYPTED_APP: "Encrypted",
    UNKNOWN_APP: "Unknown",
  };
  return labels[packetType] ?? packetType.replace(/^unknown_/, "Unknown ");
}

function meshDiagnostic(device: MeshDeviceStatus): string {
  const packet = packetTypeLabel(device.lastPacketType);
  if (!packet) return device.lastSeenAt ? "Packet heard" : "No mesh packets heard";
  const gateway = meshGatewayDisplayLabel(device);
  if (device.source === "mesh_relay") {
    if (isSameMeshNode(device.lastGatewayId, device.deviceId)) return `Received own ${packet} through Aervyx mobile app`;
    if (device.lastGatewayId) return `Received ${packet} through ${gateway}'s Aervyx mobile app`;
    return `Received ${packet} through Aervyx mobile app`;
  }
  if (isSameMeshNode(device.lastGatewayId, device.deviceId)) return `Published ${packet} to MQTT`;
  if (device.lastGatewayId) return `${packet} via ${gateway}`;
  return packet;
}

function meshDeviceDisplayLabel(device: MeshDeviceStatus): string {
  return device.label || device.deviceId;
}

function meshDeliveryTransportLabel(source: string | null | undefined): string | null {
  if (source === "mesh_relay") return "Aervyx mobile app";
  if (source === "mqtt_gateway") return "MQTT";
  if (source === "app") return "Phone app";
  return null;
}

function meshDeliveryPath(device: MeshDeviceStatus): string {
  if (!device.lastSeenAt) return "Path not observed yet";

  const sender = meshDeviceDisplayLabel(device);
  const transport = meshDeliveryTransportLabel(device.source);
  if (!transport) return `${sender} -> Aervyx Web`;

  if (device.lastGatewayId && !isSameMeshNode(device.lastGatewayId, device.deviceId)) {
    return `${sender} -> ${meshGatewayDisplayLabel(device)} -> ${transport} -> Aervyx Web`;
  }
  return `${sender} -> ${transport} -> Aervyx Web`;
}

function meshDebugDetail(device: MeshDeviceStatus): string {
  const path = meshDeliveryPath(device);
  return path === "Path not observed yet" ? meshDiagnostic(device) : `Path: ${path}`;
}

function normalizedMeshNodeId(value: string | null | undefined): string | null {
  const normalized = (value ?? "").trim().toLowerCase().replace(/^!/, "");
  return normalized || null;
}

function isSameMeshNode(left: string | null | undefined, right: string | null | undefined): boolean {
  const normalizedLeft = normalizedMeshNodeId(left);
  const normalizedRight = normalizedMeshNodeId(right);
  return normalizedLeft != null && normalizedRight != null && normalizedLeft === normalizedRight;
}

function meshGatewayDisplayLabel(device: MeshDeviceStatus): string {
  if (device.lastGatewayDisplayName) return device.lastGatewayDisplayName;
  if (isSameMeshNode(device.lastGatewayId, device.deviceId)) return meshDeviceDisplayLabel(device);
  if (device.lastGatewayId) return `Node ${device.lastGatewayId}`;
  return "Not heard yet";
}

function meshFixSummary(device: MeshDeviceStatus): string {
  if (device.lastPosition) return formatDebugPosition(device.lastPosition);
  return device.lastSeenAt ? "No GPS fix" : "No fix yet";
}

function phoneSourcePillClass(session: import("./types").DebugActiveSession | null): string {
  if (session?.is_online) return "tracking-source-pill phone";
  const freshness = lastSeenColor(session?.last_seen_at);
  if (freshness === "orange") return "tracking-source-pill phone stale";
  return "tracking-source-pill phone offline";
}

function phoneStatusColor(session: import("./types").DebugActiveSession | null): string {
  if (session?.is_online) return "#3b82f6";
  const freshness = lastSeenColor(session?.last_seen_at);
  if (freshness === "orange") return "#f59e0b";
  return "#ef4444";
}

function latestTimestamp(left: string | null | undefined, right: string | null | undefined): string | null {
  if (!left) return right ?? null;
  if (!right) return left;
  return new Date(right).getTime() > new Date(left).getTime() ? right : left;
}

function meshDeviceFromDebug(device: MeshDeviceDebug): MeshDeviceStatus {
  return {
    key: `registered-${device.device_id}`,
    deviceId: device.device_id,
    label: device.label,
    purpose: device.purpose,
    isConnected: device.is_connected,
    meshStatus: device.mesh_status,
    registeredOwnerUserId: device.owner_user_id,
    registeredOwnerName: device.owner_name,
    ownerPilotId: device.owner_pilot_id,
    source: device.source,
    positionSource: "mesh",
    batteryLevel: device.battery_level,
    lastSeenAt: device.last_seen_at,
    lastPacketType: device.last_packet_type,
    lastGatewayId: device.last_gateway_id,
    lastGatewayDisplayName: device.last_gateway_display_name,
    lastTopic: device.last_topic,
    packetCount: device.packet_count,
    lastPosition: device.last_position,
  };
}

function meshDeviceFromNode(node: MeshNode): MeshDeviceStatus {
  return {
    key: `node-${node.device_id}`,
    deviceId: node.device_id,
    label: node.device_label,
    purpose: node.device_purpose,
    isConnected: node.mesh_status === "live",
    meshStatus: node.mesh_status,
    registeredOwnerUserId: node.registered_owner_user_id,
    registeredOwnerName: node.registered_owner_name,
    ownerPilotId: node.pilot_id,
    source: node.source,
    positionSource: node.position_source,
    batteryLevel: node.battery_level,
    lastSeenAt: node.timestamp,
    lastPacketType: node.last_packet_type,
    lastGatewayId: node.last_gateway_id,
    lastGatewayDisplayName: node.last_gateway_display_name,
    lastTopic: node.last_topic,
    packetCount: node.packet_count,
    lastPosition: node.lat != null && node.lon != null ? {
      lat: node.lat,
      lon: node.lon,
      alt: node.alt,
      speed: node.speed,
      heading: node.heading,
    } : null,
  };
}

function formatDebugPosition(position: MeshDeviceStatus["lastPosition"] | import("./types").DebugActiveSession["last_position"] | null | undefined): string {
  if (!position) return "\u2014";
  const parts = [`${position.lat.toFixed(5)}, ${position.lon.toFixed(5)}`];
  if (position.alt != null) parts.push(`${Math.round(position.alt)}m`);
  if (position.speed != null) parts.push(`${position.speed.toFixed(1)} km/h`);
  if ("heading" in position && position.heading != null) parts.push(`${Math.round(position.heading)}deg`);
  return parts.join(" | ");
}

function LiveTrackingTab({
  debugStatus,
  meshNodes,
  overlayConfig,
}: {
  debugStatus: import("./types").DebugStatusResponse | null;
  meshNodes: MeshNode[];
  overlayConfig?: MapOverlayConfigRecord["config"]["dashboard_live"];
}) {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());
  const [focusPos, setFocusPos] = useState<{ lat: number; lon: number; key: string | number } | null>(null);

  function handleRowClick(d: UnifiedDevice) {
    const newestMesh = d.meshDevices
      .filter((device) => device.lastPosition && (device.lastPosition.lat !== 0 || device.lastPosition.lon !== 0))
      .sort((a, b) => {
        const ta = a.lastSeenAt ? new Date(a.lastSeenAt).getTime() : 0;
        const tb = b.lastSeenAt ? new Date(b.lastSeenAt).getTime() : 0;
        return tb - ta;
      })[0];
    const useMesh = newestMesh != null && (
      !d.session?.last_seen_at ||
      new Date(newestMesh.lastSeenAt ?? 0).getTime() > new Date(d.session.last_seen_at).getTime()
    );
    const pos = useMesh ? newestMesh.lastPosition : d.session?.last_position;
    if (!pos || (pos.lat === 0 && pos.lon === 0)) return;
    setFocusPos({ lat: pos.lat, lon: pos.lon, key: `${d.key}-${Date.now()}` });
  }

  const unified = useMemo<UnifiedDevice[]>(() => {
    const byKey = new Map<string, UnifiedDevice>();

    function ensureRow(key: string, pilotId: number | null, userId: number | null, name: string, profileType: string | null): UnifiedDevice {
      const existing = byKey.get(key);
      if (existing) {
        if (existing.user_id == null && userId != null) existing.user_id = userId;
        if (!existing.profile_type && profileType) existing.profile_type = profileType;
        if (existing.pilot_name === key && name) existing.pilot_name = name;
        return existing;
      }
      const created: UnifiedDevice = {
        key,
        pilot_id: pilotId,
        user_id: userId,
        pilot_name: name,
        profile_type: profileType,
        session: null,
        meshDevices: [],
        hasPhone: false,
        hasMesh: false,
        isOnline: false,
        lastSeenAt: null,
      };
      byKey.set(key, created);
      return created;
    }

    for (const session of (debugStatus?.active_sessions ?? [])) {
      const key = session.pilot_id != null
        ? `pilot-${session.pilot_id}`
        : session.user_id != null
          ? `user-${session.user_id}`
          : `session-${session.started_at ?? session.pilot_name}`;
      const row = ensureRow(key, session.pilot_id, session.user_id, session.pilot_name, session.profile_type);
      row.session = session;
      row.hasPhone = true;
      row.isOnline = row.isOnline || session.is_online;
      row.lastSeenAt = latestTimestamp(row.lastSeenAt, session.last_seen_at);
    }

    const registeredDeviceIds = new Set((debugStatus?.registered_mesh_devices ?? []).map((device) => device.device_id));
    for (const device of (debugStatus?.registered_mesh_devices ?? [])) {
      const entry = meshDeviceFromDebug(device);
      const key = device.owner_pilot_id != null ? `pilot-${device.owner_pilot_id}` : `user-${device.owner_user_id}`;
      const row = ensureRow(key, device.owner_pilot_id, device.owner_user_id, device.owner_name ?? device.label ?? device.device_id, null);
      row.meshDevices.push(entry);
      row.hasMesh = true;
      row.isOnline = row.isOnline || entry.isConnected;
      row.lastSeenAt = latestTimestamp(row.lastSeenAt, entry.lastSeenAt);
    }

    for (const node of meshNodes) {
      if (registeredDeviceIds.has(node.device_id)) continue;
      const entry = meshDeviceFromNode(node);
      const key = node.pilot_id != null
        ? `pilot-${node.pilot_id}`
        : node.registered_owner_user_id != null
          ? `user-${node.registered_owner_user_id}`
          : `device-${node.device_id}`;
      const row = ensureRow(key, node.pilot_id, node.registered_owner_user_id, node.registered_owner_name ?? node.pilot_name ?? node.device_id, node.profile_type);
      row.meshDevices.push(entry);
      row.hasMesh = true;
      row.isOnline = row.isOnline || entry.isConnected;
      row.lastSeenAt = latestTimestamp(row.lastSeenAt, entry.lastSeenAt);
    }

    const list = Array.from(byKey.values());
    for (const row of list) {
      row.meshDevices.sort((a, b) => {
        if (a.isConnected !== b.isConnected) return a.isConnected ? -1 : 1;
        return (a.label ?? a.deviceId).localeCompare(b.label ?? b.deviceId);
      });
    }
    list.sort((a, b) => {
      if (a.isOnline !== b.isOnline) return a.isOnline ? -1 : 1;
      const ta = a.lastSeenAt ? new Date(a.lastSeenAt).getTime() : 0;
      const tb = b.lastSeenAt ? new Date(b.lastSeenAt).getTime() : 0;
      return tb - ta;
    });
    return list;
  }, [debugStatus, meshNodes]);

  const livePositions = useMemo<MapLivePosition[]>(() => {
    const positions: MapLivePosition[] = [];
    for (const d of unified) {
      // Phone position
      if (d.hasPhone && d.session?.last_position) {
        const pos = d.session.last_position;
        if (pos.lat !== 0 || pos.lon !== 0) {
          positions.push({
            id: `${d.key}-phone`,
            pilotId: d.pilot_id,
            pilotName: d.pilot_name,
            latitude: pos.lat,
            longitude: pos.lon,
            altitudeM: pos.alt,
            speedKmh: pos.speed,
            heading: null,
            timestamp: d.session.last_seen_at ?? new Date().toISOString(),
            batteryLevel: d.session.battery_level ?? null,
            source: d.session.source ?? "app",
            color: "#3b82f6",  // blue for phone
            aircraftType: "hang_glider",
            profileType: (d.profile_type ?? "pilot") as "pilot" | "driver" | "stationary_node",
            positionSource: "cellular",
          });
        }
      }
      for (const meshDevice of d.meshDevices) {
        const pos = meshDevice.lastPosition;
        if (pos && (pos.lat !== 0 || pos.lon !== 0)) {
          const meshLabel = meshDevice.label
            ? `${meshDevice.label}${meshDevice.registeredOwnerName ? ` - ${meshDevice.registeredOwnerName}` : ""}`
            : d.hasPhone ? `${d.pilot_name} (Mesh)` : d.pilot_name;
          positions.push({
            id: `${d.key}-${meshDevice.deviceId}-mesh`,
            pilotId: d.pilot_id,
            pilotName: meshLabel,
            latitude: pos.lat,
            longitude: pos.lon,
            altitudeM: pos.alt,
            speedKmh: pos.speed,
            heading: pos.heading ?? null,
            timestamp: meshDevice.lastSeenAt ?? new Date().toISOString(),
            batteryLevel: meshDevice.batteryLevel ?? null,
            source: meshDevice.source ?? "mqtt_gateway",
            color: "#22c55e",  // green for mesh
            aircraftType: "hang_glider",
            profileType: (d.profile_type ?? "pilot") as "pilot" | "driver" | "stationary_node",
            positionSource: "mesh",
          });
        }
      }
    }
    return positions;
  }, [unified]);

  function toggleExpand(key: string) {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <SectionCard>
      <div className="stack form-block live-tracking-debugging-body">
        <div className="participant-table-wrap live-tracking-debugging-table-wrap">
          <table className="participant-table live-tracking-debugging-table">
            <thead>
              <tr>
                <th style={{ width: "24px" }}></th>
                <th>Status</th>
                <th>Device / Pilot</th>
                <th>Purpose</th>
                <th>Sources</th>
                <th>Device ID</th>
                <th>Battery</th>
                <th>Fix / Path</th>
                <th>Last Heard</th>
              </tr>
            </thead>
            <tbody>
              {unified.length ? (
                unified.map((d) => {
                  const color = lastSeenColor(d.lastSeenAt);
                  const borderColor = color === "green" ? "#22c55e" : color === "orange" ? "#f59e0b" : "#ef4444";
                  const isExpanded = expandedKeys.has(d.key);
                  const canExpand = true; // Always expandable for position detail

                  return (
                    <Fragment key={d.key}>
                      <tr style={{ borderLeft: `3px solid ${borderColor}`, cursor: "pointer" }} onClick={() => handleRowClick(d)}>
                        <td
                          className={canExpand ? `tracking-expand-toggle${isExpanded ? " expanded" : ""}` : ""}
                          onClick={canExpand ? (event) => {
                            event.stopPropagation();
                            toggleExpand(d.key);
                          } : undefined}
                        >
                          {canExpand ? (isExpanded ? "▾" : "▸") : ""}
                        </td>
                        <td></td>
                        <td>
                          <strong>{d.pilot_name}</strong>
                        </td>
                        <td></td>
                        <td></td>
                        <td></td>
                        <td></td>
                        <td></td>
                        <td></td>
                      </tr>
                      {isExpanded && (
                        <>
                          {d.hasPhone && (
                            <tr
                              className="tracking-sub-row"
                              style={{ cursor: d.session?.last_position ? "pointer" : undefined }}
                              onClick={() => {
                                const pos = d.session?.last_position;
                                if (pos && (pos.lat !== 0 || pos.lon !== 0)) {
                                  setFocusPos({ lat: pos.lat, lon: pos.lon, key: `${d.key}-phone-${Date.now()}` });
                                }
                              }}
                            >
                              <td></td>
                              <td>
                                <span
                                  style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", backgroundColor: phoneStatusColor(d.session), marginRight: "4px" }}
                                  title={d.session?.is_online ? "Phone app live" : "Phone app offline"}
                                />
                              </td>
                              <td>Phone</td>
                              <td>Phone app</td>
                              <td><span className={phoneSourcePillClass(d.session)}>Phone app</span></td>
                              <td style={{ fontFamily: "monospace", fontSize: "0.72rem", color: "var(--muted)" }}>{d.session?.device_id ?? "\u2014"}</td>
                              <td>{d.session?.battery_level != null ? `${d.session?.battery_level}%` : "\u2014"}</td>
                              <td>{formatDebugPosition(d.session?.last_position)}</td>
                              <td style={{ color: lastSeenColor(d.session?.last_seen_at) === "green" ? "inherit" : lastSeenColor(d.session?.last_seen_at) === "orange" ? "#f59e0b" : "#ef4444" }}>
                                {relativeTime(d.session?.last_seen_at)}
                              </td>
                            </tr>
                          )}
                          {d.meshDevices.map((meshDevice) => {
                            const meshFixColor = lastSeenColor(meshDevice.lastSeenAt);
                            const meshLastFixColor = meshFixColor === "green" ? "inherit" : meshFixColor === "orange" ? "#f59e0b" : "#ef4444";
                            const meshDotColor = meshStatusColor(meshDevice.meshStatus);
                            return (
                              <tr
                                key={`${d.key}-${meshDevice.deviceId}`}
                                className="tracking-sub-row"
                                style={{ cursor: meshDevice.lastPosition ? "pointer" : undefined }}
                                onClick={() => {
                                  const pos = meshDevice.lastPosition;
                                  if (pos && (pos.lat !== 0 || pos.lon !== 0)) {
                                    setFocusPos({ lat: pos.lat, lon: pos.lon, key: `${d.key}-${meshDevice.deviceId}-${Date.now()}` });
                                  }
                                }}
                              >
                                <td></td>
                                <td>
                                  <span
                                    style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", backgroundColor: meshDotColor, marginRight: "4px" }}
                                    title={meshSourcePillLabel(meshDevice.meshStatus, meshDevice.source)}
                                  />
                                </td>
                                <td>
                                  <strong>{meshDevice.label ?? meshDevice.deviceId}</strong>
                                </td>
                                <td>{meshPurposeLabel(meshDevice.purpose)}</td>
                                <td>
                                  <span className={`tracking-source-pill mesh${meshStatusClass(meshDevice.meshStatus)}`}>
                                    {meshSourcePillLabel(meshDevice.meshStatus, meshDevice.source)}
                                  </span>
                                </td>
                                <td style={{ fontFamily: "monospace", fontSize: "0.72rem", color: "var(--muted)" }}>{meshDevice.deviceId}</td>
                                <td>{meshDevice.batteryLevel != null ? `${meshDevice.batteryLevel}%` : "\u2014"}</td>
                                <td>
                                  <div>{meshFixSummary(meshDevice)}</div>
                                  <div className="hint">Packets heard: {meshDevice.packetCount}</div>
                                  <div className="hint">{meshDebugDetail(meshDevice)}</div>
                                </td>
                                <td style={{ color: meshLastFixColor }}>{relativeTime(meshDevice.lastSeenAt)}</td>
                              </tr>
                            );
                          })}
                        </>
                      )}
                    </Fragment>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={9} className="participant-table-empty">No active tracking sessions or mesh devices.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* C) Map */}
        <div className="live-tracking-debugging-map">
          <TaskMap
            turnpoints={[]}
            taskPoints={[]}
            optimizedRoute={[]}
            legMetrics={[]}
            track={null}
            editable={false}
            livePositions={livePositions}
            liveMarkerScale={1.8}
            fitKey={`live-tracking-${livePositions.length}`}
            focusPosition={focusPos}
            mode="live"
            overlayConfig={overlayConfig}
          />
        </div>
      </div>
    </SectionCard>
  );
}

/* ------------------------------------------------------------------ */
/*  Meshtastic Profiles table                                          */
/* ------------------------------------------------------------------ */

// Curated set of Meshtastic device settings exposed per profile.
// Mirrors the categories in the official Meshtastic Android app.
// MUST stay in lockstep with backend/app/routers/site_settings.py
// and mobile/lib/models/meshtastic_protobufs.dart.
const DEFAULT_MESH_PROFILES: Record<string, Record<string, unknown>> = {
  pilot: {
    // Device
    role: "tracker", rebroadcast_mode: "all", node_info_broadcast_secs: 10800, serial_enabled: true,
    // Position
    gps_mode: "enabled", gps_update_interval: 30, position_broadcast_secs: 30,
    smart_position_enabled: true, smart_min_distance: 100, smart_min_interval: 30, position_flags: 1,
    // LoRa
    region: "unset", modem_preset: "long_fast", hop_limit: 3, tx_power: 0, tx_enabled: true, sx126x_rx_boosted_gain: true,
    // Power
    power_saving: false, on_battery_shutdown_after_secs: 0, ls_secs: 300, wait_bluetooth_secs: 60,
    // Bluetooth — always on + fixed PIN so headless devices can't lock admins out
    bluetooth_enabled: true, bluetooth_mode: "fixed_pin", bluetooth_fixed_pin: 123456,
    // Network (Wi-Fi SSID/PSK are device-specific, set per device on the phone app)
    wifi_enabled: false, eth_enabled: false,
    // Display
    display_timeout_secs: 30, auto_screen_carousel_secs: 0, wake_on_tap_or_motion: true,
    // Modules
    telemetry_interval_secs: 86400, device_telemetry_enabled: true, environment_telemetry_enabled: false,
    neighbor_info_enabled: false, neighbor_info_interval_secs: 14400,
    store_forward_enabled: false, store_forward_is_server: false,
  },
  driver: {
    role: "client", rebroadcast_mode: "all", node_info_broadcast_secs: 10800, serial_enabled: true,
    gps_mode: "enabled", gps_update_interval: 60, position_broadcast_secs: 120,
    smart_position_enabled: true, smart_min_distance: 200, smart_min_interval: 60, position_flags: 1,
    region: "unset", modem_preset: "long_fast", hop_limit: 3, tx_power: 0, tx_enabled: true, sx126x_rx_boosted_gain: true,
    power_saving: false, on_battery_shutdown_after_secs: 0, ls_secs: 300, wait_bluetooth_secs: 60,
    bluetooth_enabled: true, bluetooth_mode: "fixed_pin", bluetooth_fixed_pin: 123456,
    wifi_enabled: false, eth_enabled: false,
    display_timeout_secs: 60, auto_screen_carousel_secs: 0, wake_on_tap_or_motion: true,
    telemetry_interval_secs: 86400, device_telemetry_enabled: true, environment_telemetry_enabled: false,
    neighbor_info_enabled: false, neighbor_info_interval_secs: 14400,
    store_forward_enabled: false, store_forward_is_server: false,
  },
  driver_wifi: {
    role: "client", rebroadcast_mode: "all", node_info_broadcast_secs: 10800, serial_enabled: true,
    gps_mode: "enabled", gps_update_interval: 30, position_broadcast_secs: 60,
    smart_position_enabled: true, smart_min_distance: 200, smart_min_interval: 30, position_flags: 1,
    region: "unset", modem_preset: "long_fast", hop_limit: 3, tx_power: 0, tx_enabled: true, sx126x_rx_boosted_gain: true,
    power_saving: false, on_battery_shutdown_after_secs: 0, ls_secs: 300, wait_bluetooth_secs: 60,
    bluetooth_enabled: true, bluetooth_mode: "fixed_pin", bluetooth_fixed_pin: 123456,
    wifi_enabled: true, eth_enabled: false,
    display_timeout_secs: 60, auto_screen_carousel_secs: 0, wake_on_tap_or_motion: true,
    telemetry_interval_secs: 86400, device_telemetry_enabled: true, environment_telemetry_enabled: false,
    neighbor_info_enabled: false, neighbor_info_interval_secs: 14400,
    store_forward_enabled: false, store_forward_is_server: false,
  },
  repeater: {
    role: "router", rebroadcast_mode: "all", node_info_broadcast_secs: 10800, serial_enabled: true,
    gps_mode: "enabled", gps_update_interval: 0, position_broadcast_secs: 300,
    smart_position_enabled: false, smart_min_distance: 0, smart_min_interval: 0, position_flags: 1,
    region: "unset", modem_preset: "long_fast", hop_limit: 3, tx_power: 0, tx_enabled: true, sx126x_rx_boosted_gain: true,
    power_saving: false, on_battery_shutdown_after_secs: 0, ls_secs: 300, wait_bluetooth_secs: 60,
    bluetooth_enabled: true, bluetooth_mode: "fixed_pin", bluetooth_fixed_pin: 123456,
    wifi_enabled: true, eth_enabled: false,
    display_timeout_secs: 0, auto_screen_carousel_secs: 0, wake_on_tap_or_motion: false,
    telemetry_interval_secs: 86400, device_telemetry_enabled: true, environment_telemetry_enabled: false,
    neighbor_info_enabled: true, neighbor_info_interval_secs: 14400,
    store_forward_enabled: true, store_forward_is_server: true,
  },
};

const PROFILE_KEYS = ["pilot", "driver", "driver_wifi", "repeater"] as const;
const PROFILE_LABELS: Record<string, string> = { pilot: "Pilot", driver: "Driver", driver_wifi: "Driver Wi-Fi", repeater: "Base Station" };

// Role options shown in the dropdown, per-profile.
// Pilots are always trackers — picking anything else would break the firmware's
// position-priority handling. Every other profile gets the full set.
const ROLE_OPTIONS_PILOT = ["tracker"] as const;
const ROLE_OPTIONS_OTHER = ["tracker", "router", "client"] as const;

type ProfileRowDef = {
  key: string;
  label: string;
  kind: "select" | "number" | "boolean" | "string" | "flag_bit";
  options?: string[];
  // Optional override: per-profile-key option lists.
  // When present, takes precedence over `options` for that profile column.
  perProfileOptions?: Record<string, readonly string[]>;
  min?: number;
  max?: number;
  description?: string;
  // Mark text inputs that should hide their value (Wi-Fi PSK, etc.).
  secret?: boolean;
  // For flag_bit rows: name of the backing bitmask field + the bit to toggle.
  storageKey?: string;
  bit?: number;
  // Unit conversion: divide stored value by this factor for display, multiply on save.
  // e.g. displayScale: 3600 converts seconds <-> hours.
  displayScale?: number;
};

// Meshtastic PositionFlags bitmask — mirrors the official config.proto.
// Each bit toggles whether that field is included in outgoing position packets.
const POSITION_FLAG_ALTITUDE = 0x01;
const POSITION_FLAG_ALTITUDE_MSL = 0x02;
const POSITION_FLAG_GEOIDAL_SEPARATION = 0x04;
const POSITION_FLAG_DOP = 0x08;
const POSITION_FLAG_HVDOP = 0x10;
const POSITION_FLAG_SATELLITES_IN_VIEW = 0x20;
const POSITION_FLAG_SEQ_NO = 0x40;
const POSITION_FLAG_TIMESTAMP = 0x80;
const POSITION_FLAG_HEADING = 0x100;
const POSITION_FLAG_SPEED = 0x200;

// Shared option lists for enum-typed fields. Snake-case values match the
// strings the backend stores and the mobile app's _xxxFromString helpers.
const REBROADCAST_OPTIONS = ["all", "all_skip_decoding", "local_only", "known_only", "none", "core_portnums_only"];
const GPS_MODE_OPTIONS = ["disabled", "enabled", "not_present"];
const MODEM_PRESET_OPTIONS = ["long_fast", "long_moderate", "long_slow", "very_long_slow", "medium_slow", "medium_fast", "short_slow", "short_fast", "short_turbo", "long_turbo"];
const BLUETOOTH_MODE_OPTIONS = ["random_pin", "fixed_pin", "no_pin"];

// Groups mirror the official Meshtastic Android app: Device, Position, LoRa,
// Power, Bluetooth, Network, Display, Modules. ~38 fields total.
const PROFILE_ROW_GROUPS: { group: string; readonly?: boolean; rows: ProfileRowDef[] }[] = [
  {
    group: "Device",
    rows: [
      {
        key: "role",
        label: "Role",
        kind: "select",
        options: [...ROLE_OPTIONS_OTHER],
        perProfileOptions: {
          pilot: ROLE_OPTIONS_PILOT,
          driver: ROLE_OPTIONS_OTHER,
          driver_wifi: ROLE_OPTIONS_OTHER,
          repeater: ROLE_OPTIONS_OTHER,
        },
        description: "Tracker: firmware prioritizes position packets — required for pilots. Router: always-on radio relay that extends mesh coverage — best for repeaters. Client: standard node, lower power draw — suitable for drivers and base stations. Pilot is locked to Tracker.",
      },
      { key: "rebroadcast_mode", label: "Rebroadcast", kind: "select", options: REBROADCAST_OPTIONS, description: "Which packets this device will relay onward. \"all\" is the recommended default. \"none\" turns the device into a leaf node." },
      { key: "node_info_broadcast_secs", label: "Node info (h)", kind: "number", min: 0, displayScale: 3600, description: "How often the device announces its NodeInfo (name, hardware, role) on the mesh. Default 3 hours. Lower values speed up new-node discovery but add traffic." },
      { key: "serial_enabled", label: "Serial console", kind: "boolean", description: "Enable the USB serial console / API on the device. Required for hardwired flashing and CLI access. Safe to leave enabled." },
    ],
  },
  {
    group: "Position",
    rows: [
      { key: "gps_mode", label: "GPS mode", kind: "select", options: GPS_MODE_OPTIONS, description: "Controls the internal GPS receiver. \"enabled\" lets the device produce its own position fixes. \"not_present\" tells the firmware there is no GPS at all (e.g. base station fed by phone)." },
      { key: "gps_update_interval", label: "GPS poll (s)", kind: "number", min: 0, description: "How often the GPS chip is sampled (seconds). 0 = firmware default (120s). Lower values increase battery drain but produce fresher fixes." },
      { key: "position_broadcast_secs", label: "Broadcast (s)", kind: "number", min: 0, description: "How often (in seconds) the device broadcasts its GPS position to the mesh network. Lower values give more frequent updates but increase radio traffic and battery drain. Setting to 0 reverts to firmware default (900s / 15 min). Pilots typically use 30s, drivers 60-120s, repeaters 300s." },
      { key: "smart_position_enabled", label: "Smart pos.", kind: "boolean", description: "When enabled, the device sends position updates early if it detects significant movement (based on min distance and min interval thresholds), rather than waiting for the full broadcast interval. Helps capture turns and altitude changes for pilots in flight." },
      { key: "smart_min_distance", label: "Min dist (m)", kind: "number", min: 0, description: "Minimum distance traveled (in meters) before triggering a smart position update. Only applies when smart position is enabled. Setting to 0 reverts to firmware default (100m)." },
      { key: "smart_min_interval", label: "Min interval (s)", kind: "number", min: 0, description: "Minimum time (in seconds) between smart position updates. Prevents excessive updates during rapid movement even if the distance threshold is met repeatedly. Setting to 0 reverts to firmware default (30s)." },
      // Position packet contents — each toggle flips a bit in the
      // `position_flags` bitmask stored on the server. Mirrors the fields the
      // Meshtastic firmware can attach to each outgoing POSITION packet.
      { key: "pflag_altitude", label: "· Send altitude", kind: "flag_bit", storageKey: "position_flags", bit: POSITION_FLAG_ALTITUDE, description: "Include GPS altitude (HAE, ellipsoid) in every position packet. Required for competition scoring." },
      { key: "pflag_altitude_msl", label: "· Send altitude MSL", kind: "flag_bit", storageKey: "position_flags", bit: POSITION_FLAG_ALTITUDE_MSL, description: "Include mean-sea-level altitude alongside the HAE altitude. Most devices only provide one; leave off unless your receiver specifically needs MSL." },
      { key: "pflag_geoidal", label: "· Send geoidal sep.", kind: "flag_bit", storageKey: "position_flags", bit: POSITION_FLAG_GEOIDAL_SEPARATION, description: "Include the geoidal separation (HAE − MSL) so receivers can convert between the two. Adds a few bytes per packet." },
      { key: "pflag_dop", label: "· Send DOP", kind: "flag_bit", storageKey: "position_flags", bit: POSITION_FLAG_DOP, description: "Include a combined GPS dilution-of-precision value. Useful for debugging fix quality." },
      { key: "pflag_hvdop", label: "· Send HDOP/VDOP", kind: "flag_bit", storageKey: "position_flags", bit: POSITION_FLAG_HVDOP, description: "Include horizontal + vertical DOP as separate values. Mutually exclusive with the combined DOP above." },
      { key: "pflag_sats", label: "· Send satellite count", kind: "flag_bit", storageKey: "position_flags", bit: POSITION_FLAG_SATELLITES_IN_VIEW, description: "Include the number of satellites currently in view. Handy for signal-quality overlays on the map." },
      { key: "pflag_seq_no", label: "· Send sequence #", kind: "flag_bit", storageKey: "position_flags", bit: POSITION_FLAG_SEQ_NO, description: "Include a monotonic packet sequence number so receivers can detect missed packets." },
      { key: "pflag_timestamp", label: "· Send timestamp", kind: "flag_bit", storageKey: "position_flags", bit: POSITION_FLAG_TIMESTAMP, description: "Include the GPS fix timestamp (UTC seconds). Required for accurate competition track replay." },
      { key: "pflag_heading", label: "· Send heading", kind: "flag_bit", storageKey: "position_flags", bit: POSITION_FLAG_HEADING, description: "Include the current course-over-ground heading in degrees." },
      { key: "pflag_speed", label: "· Send speed", kind: "flag_bit", storageKey: "position_flags", bit: POSITION_FLAG_SPEED, description: "Include the current speed-over-ground. Small packet size cost, useful for driver tracking." },
    ],
  },
  {
    group: "LoRa",
    // Region is intentionally NOT exposed here. It's device-specific and
    // operators set it on the mobile Meshtastic settings screen on their
    // own phone. Shipping a fleet-wide region from the admin would risk
    // silencing radios that were already on a legal frequency.
    rows: [
      { key: "modem_preset", label: "Modem preset", kind: "select", options: MODEM_PRESET_OPTIONS, description: "LoRa radio modulation settings. All devices on the same mesh must use the same preset or they will not see each other. Long Fast is the standard competition preset." },
      { key: "hop_limit", label: "Hop limit", kind: "number", min: 1, max: 7, description: "Maximum number of times a packet can be relayed across the mesh (1-7). 3 is the standard value — higher values increase coverage but add congestion." },
      { key: "tx_power", label: "TX power (dBm)", kind: "number", min: 0, max: 30, description: "Transmit power in dBm (0-30). 0 = use the legal maximum for the selected region. Lower values reduce range and battery drain." },
      { key: "tx_enabled", label: "TX enabled", kind: "boolean", description: "Master transmit kill-switch. When false the device receives only — useful for monitor-only base stations." },
      { key: "sx126x_rx_boosted_gain", label: "RX boosted gain", kind: "boolean", description: "On SX126x radios, enables boosted receive gain. Increases sensitivity at the cost of slightly higher idle current. Recommended on for trackers." },
    ],
  },
  {
    group: "Power",
    rows: [
      { key: "power_saving", label: "Power saving", kind: "boolean", description: "Aggressively conserves power by disabling BLE / Wi-Fi / serial when idle. Not recommended for competition devices that need to be responsive." },
      { key: "on_battery_shutdown_after_secs", label: "Shutdown on battery (s)", kind: "number", min: 0, description: "Auto-shutdown delay (seconds) after the device starts running on battery. 0 = never auto-shutdown. Useful for solar-powered repeaters that should sleep when the panel stops charging." },
      { key: "ls_secs", label: "Light sleep (s)", kind: "number", min: 0, description: "Light sleep duration on ESP32 devices, in seconds (default 300). Higher values save more power but increase wake latency." },
      { key: "wait_bluetooth_secs", label: "BT wait (s)", kind: "number", min: 0, description: "How long the device keeps Bluetooth on at boot before sleeping it (default 60s). Increase if you have trouble pairing on cold boot." },
    ],
  },
  {
    group: "Bluetooth",
    rows: [
      { key: "bluetooth_enabled", label: "Bluetooth", kind: "boolean", description: "BLE is required for phone-to-device communication. Disabling will prevent the Aervyx app from configuring the device. ESP32 devices auto-disable BT when Wi-Fi is on." },
      { key: "bluetooth_mode", label: "Pairing mode", kind: "select", options: BLUETOOTH_MODE_OPTIONS, description: "BLE pairing security: random_pin (display shows a fresh PIN each time), fixed_pin (always uses the same PIN below), no_pin (no PIN — least secure)." },
      { key: "bluetooth_fixed_pin", label: "Fixed PIN", kind: "number", min: 0, max: 999999, description: "PIN used when pairing mode is fixed_pin. Six digits, default 123456. Ignored in random_pin / no_pin modes." },
    ],
  },
  {
    group: "Network",
    rows: [
      { key: "wifi_enabled", label: "Wi-Fi", kind: "boolean", description: "Whether Wi-Fi is active on the device. Use this for fixed gateway profiles that publish to the private MQTT broker; normal pilot trackers should rely on the Aervyx app relay. Wi-Fi SSID / password are device-specific — set them per device from the mobile app." },
      { key: "eth_enabled", label: "Ethernet", kind: "boolean", description: "Enable wired Ethernet on devices that support it. No-op on devices without an Ethernet port." },
    ],
  },
  {
    group: "Display",
    rows: [
      { key: "display_timeout_secs", label: "Display timeout (s)", kind: "number", min: 0, description: "Seconds before the device screen turns off to save power. 0 = always on. Minimum 10 seconds otherwise — values below 10 are clamped to 0 when saved to the device, because 1–4 s just cycles the OLED and drains battery without meaningfully saving power." },
      { key: "auto_screen_carousel_secs", label: "Carousel (s)", kind: "number", min: 0, description: "How long the screen lingers on each page before auto-rotating to the next. 0 = no auto-rotation." },
      { key: "wake_on_tap_or_motion", label: "Wake on tap/motion", kind: "boolean", description: "Wake the screen when the device is tapped or moved (requires accelerometer). Useful for handheld trackers." },
    ],
  },
  {
    group: "Modules",
    rows: [
      { key: "telemetry_interval_secs", label: "Telemetry (h)", kind: "number", min: 0, displayScale: 3600, description: "How often the device reports telemetry (battery, voltage, temperature) to the mesh. Default 24 hours — effectively suppresses unnecessary traffic during a competition." },
      { key: "device_telemetry_enabled", label: "Device telemetry", kind: "boolean", description: "Master enable for device-metrics telemetry (battery %, voltage, channel utilization). Required for the dashboard to track battery status." },
      { key: "environment_telemetry_enabled", label: "Env telemetry", kind: "boolean", description: "Enable environmental sensor reporting (temperature, humidity, pressure). No-op on devices without an env sensor." },
      { key: "neighbor_info_enabled", label: "Neighbor info", kind: "boolean", description: "Enable the Neighbor Info module — periodically broadcasts a list of one-hop neighbors so the dashboard can show network topology." },
      { key: "neighbor_info_interval_secs", label: "Neighbor int. (h)", kind: "number", min: 4, displayScale: 3600, description: "How often Neighbor Info is broadcast. Minimum 4 hours per Meshtastic spec." },
      { key: "store_forward_enabled", label: "Store & forward", kind: "boolean", description: "Enable the Store & Forward module — caches messages for offline clients. Recommended only on AC-powered nodes." },
      { key: "store_forward_is_server", label: "S&F server", kind: "boolean", description: "Designate this node as the Store & Forward server. Only one server is needed per mesh — typically a repeater." },
    ],
  },
];

/* ------------------------------------------------------------------ */
/*  Number formatting helpers for MeshProfilesTable                   */
/* ------------------------------------------------------------------ */

function formatNumber(n: number): string {
  return n.toLocaleString();
}

/**
 * A number input that shows a comma-formatted display value when blurred
 * and reverts to a plain numeric string when focused for editing.
 */
function FormattedNumberInput({
  value,
  min,
  max,
  step,
  onChange,
  style,
}: {
  value: number;
  min?: number;
  max?: number;
  step?: number;
  onChange: (n: number) => void;
  style?: React.CSSProperties;
}) {
  const [focused, setFocused] = useState(false);
  const [draft, setDraft] = useState("");

  const displayValue = focused ? draft : formatNumber(value);

  return (
    <input
      type={focused ? "number" : "text"}
      inputMode={step && step % 1 !== 0 ? "decimal" : "numeric"}
      min={min}
      max={max}
      step={step}
      value={displayValue}
      style={style}
      onFocus={() => {
        setDraft(String(value));
        setFocused(true);
      }}
      onChange={(e) => {
        setDraft(e.target.value);
      }}
      onBlur={() => {
        setFocused(false);
        const parsed = Number(draft);
        if (!Number.isNaN(parsed)) onChange(parsed);
      }}
    />
  );
}

function MeshProfilesTable({
  siteSettings,
  setSiteSettings,
}: {
  siteSettings: SiteSettingsRecord;
  setSiteSettings: (s: SiteSettingsRecord | ((c: SiteSettingsRecord) => SiteSettingsRecord)) => void;
}) {
  const [expandedInfo, setExpandedInfo] = useState<string | null>(null);
  const profiles = siteSettings.mesh_profiles ?? DEFAULT_MESH_PROFILES;

  function updateCell(profileKey: string, settingKey: string, newValue: unknown) {
    setSiteSettings((current) => ({
      ...current,
      mesh_profiles: {
        ...(current.mesh_profiles ?? DEFAULT_MESH_PROFILES),
        [profileKey]: {
          ...(current.mesh_profiles ?? DEFAULT_MESH_PROFILES)[profileKey],
          [settingKey]: newValue,
        },
      },
    }));
  }

  // Shared cell/input styles — all profile columns have equal fixed width.
  const PROFILE_COL_WIDTH = "13%";

  const cellStyle: React.CSSProperties = {
    padding: "3px 6px",
    verticalAlign: "middle",
    textAlign: "center",
  };

  const labelCellStyle: React.CSSProperties = {
    padding: "3px 10px 3px 10px",
    verticalAlign: "middle",
    textAlign: "left",
    width: "calc(100% - 4 * 13%)",
  };

  const inputStyle: React.CSSProperties = {
    fontSize: "0.75rem",
    padding: "2px 6px",
    width: "100%",
    minWidth: 0,
    boxSizing: "border-box",
    textAlign: "center",
  };

  const selectStyle: React.CSSProperties = {
    ...inputStyle,
    width: "100%",
  };

  const groupHeaderStyle: React.CSSProperties = {
    fontSize: "0.68rem",
    fontWeight: 700,
    letterSpacing: "0.06em",
    textTransform: "uppercase",
    color: "var(--ink-secondary)",
    background: "var(--wash-alt)",
    padding: "5px 10px",
    borderTop: "2px solid var(--line)",
    borderLeft: "3px solid var(--accent)",
  };

  return (
    <div style={{ marginTop: "16px" }}>
      <div style={{ fontWeight: 600, fontSize: "0.875rem", marginBottom: "10px" }}>Meshtastic Profiles</div>
      <div style={{ overflowX: "auto", borderRadius: "var(--r-md)", border: "1px solid var(--line)", boxShadow: "var(--shadow-sm)" }}>
        <table style={{ borderCollapse: "collapse", fontSize: "0.8rem", width: "100%", minWidth: "600px", tableLayout: "fixed" }}>
          <thead>
            <tr style={{ background: "var(--wash-alt)" }}>
              <th style={{ textAlign: "left", padding: "6px 10px", fontSize: "0.72rem", fontWeight: 700, borderBottom: "2px solid var(--line-strong)", textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--ink-secondary)" }}>
                Setting
              </th>
              {PROFILE_KEYS.map((pk) => (
                <th key={pk} style={{ textAlign: "center", padding: "6px 8px", fontSize: "0.72rem", fontWeight: 700, borderBottom: "2px solid var(--line-strong)", textTransform: "uppercase", letterSpacing: "0.04em", color: "var(--ink-secondary)", width: PROFILE_COL_WIDTH }}>
                  {PROFILE_LABELS[pk]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {PROFILE_ROW_GROUPS.map(({ group, rows }) => (
              <Fragment key={group}>
                <tr>
                  <td colSpan={PROFILE_KEYS.length + 1} style={groupHeaderStyle}>{group}</td>
                </tr>
                {rows.map((row, rowIdx) => {
                  // Alternating zebra striping within each group (odd rows get a wash tint).
                  const isOdd = rowIdx % 2 === 1;
                  const rowBg = isOdd ? "var(--wash)" : "var(--panel)";
                  return (
                    <tr
                      key={row.key}
                      style={{
                        borderBottom: "1px solid var(--line)",
                        background: rowBg,
                        transition: "background 0.1s",
                      }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = "var(--accent-softer)"; }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = rowBg; }}
                    >
                      <td style={labelCellStyle}>
                        <span style={{ display: "flex", alignItems: "center", gap: "4px", whiteSpace: "nowrap" }}>
                          <span style={{ fontSize: "0.75rem", color: "var(--ink-secondary)", fontWeight: 500 }}>{row.label}</span>
                          {row.description && (
                            <button
                              type="button"
                              onClick={() => setExpandedInfo(expandedInfo === row.key ? null : row.key)}
                              title={row.description}
                              style={{
                                background: "none",
                                border: "none",
                                cursor: "pointer",
                                padding: "0 2px",
                                fontSize: "0.72rem",
                                color: expandedInfo === row.key ? "var(--accent)" : "var(--ink-muted)",
                                lineHeight: 1,
                                flexShrink: 0,
                              }}
                            >
                              &#9432;
                            </button>
                          )}
                        </span>
                        {expandedInfo === row.key && row.description && (
                          <div style={{
                            fontSize: "0.68rem",
                            color: "var(--muted)",
                            marginTop: "4px",
                            whiteSpace: "normal",
                            maxWidth: "300px",
                            lineHeight: 1.5,
                            padding: "5px 8px",
                            background: "var(--accent-softer)",
                            border: "1px solid var(--accent-soft)",
                            borderRadius: "var(--r-sm)",
                          }}>
                            {row.description}
                          </div>
                        )}
                      </td>
                      {PROFILE_KEYS.map((pk) => {
                        const rawVal = row.kind === "flag_bit"
                          ? profiles[pk]?.[row.storageKey ?? ""]
                          : profiles[pk]?.[row.key];
                        const options = row.perProfileOptions?.[pk] ?? row.options ?? [];
                        const lockedSelect = row.kind === "select" && options.length === 1;
                        return (
                          <td key={pk} style={cellStyle}>
                            {row.kind === "flag_bit" ? (
                              <input
                                type="checkbox"
                                checked={((Number(rawVal ?? 0)) & (row.bit ?? 0)) !== 0}
                                onChange={(e) => {
                                  const current = Number(profiles[pk]?.[row.storageKey ?? ""] ?? 0);
                                  const next = e.target.checked
                                    ? current | (row.bit ?? 0)
                                    : current & ~(row.bit ?? 0);
                                  updateCell(pk, row.storageKey ?? "", next);
                                }}
                                style={{ cursor: "pointer", display: "block", margin: "0 auto" }}
                              />
                            ) : row.kind === "boolean" ? (
                              <input
                                type="checkbox"
                                checked={Boolean(rawVal)}
                                onChange={(e) => updateCell(pk, row.key, e.target.checked)}
                                style={{ cursor: "pointer", display: "block", margin: "0 auto" }}
                              />
                            ) : row.kind === "select" ? (
                              <select
                                value={String(rawVal ?? "")}
                                onChange={(e) => updateCell(pk, row.key, e.target.value)}
                                style={selectStyle}
                                disabled={lockedSelect}
                                title={lockedSelect ? "Locked — pilots must always be trackers." : undefined}
                              >
                                {options.map((opt) => (
                                  <option key={opt} value={opt}>{opt}</option>
                                ))}
                              </select>
                            ) : row.kind === "string" ? (
                              <input
                                type={row.secret ? "password" : "text"}
                                value={String(rawVal ?? "")}
                                onChange={(e) => updateCell(pk, row.key, e.target.value)}
                                style={inputStyle}
                                autoComplete="off"
                              />
                            ) : (
                              <FormattedNumberInput
                                value={row.displayScale ? Number(rawVal ?? 0) / row.displayScale : Number(rawVal ?? 0)}
                                min={row.min}
                                max={row.max}
                                step={row.displayScale ? 0.5 : undefined}
                                onChange={(n) => updateCell(pk, row.key, row.displayScale ? n * row.displayScale : n)}
                                style={inputStyle}
                              />
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint" style={{ marginTop: "6px" }}>Profile defaults are applied when mesh_profiles is null. Edit cells to customise per-profile settings.</p>
    </div>
  );
}
