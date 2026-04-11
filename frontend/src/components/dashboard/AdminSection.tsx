"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import { type MapLivePosition, type MapTaskPoint, type MapTurnpoint, TaskMap } from "../TaskMap";
import { SectionCard } from "../SectionCard";
import type { AdminSiteRecord, AdminUserRecord, DebugStatusResponse, MapOverlayConfigRecord, SiteSettingsRecord, User } from "./types";

type AdminTab = "platform_users" | "site_settings" | "sites_database" | "live_tracking" | "map_config" | "meshtastic";

type MeshNode = {
  device_id: string;
  pilot_id: number | null;
  pilot_name: string | null;
  profile_type: string | null;
  lat: number;
  lon: number;
  alt: number | null;
  speed: number | null;
  heading: number | null;
  battery_level: number | null;
  timestamp: string;
  source: string | null;
  position_source: string;
};

type UnifiedDevice = {
  key: string;
  pilot_id: number | null;
  pilot_name: string;
  profile_type: string | null;
  session: import("./types").DebugActiveSession | null;
  meshNode: MeshNode | null;
  hasPhone: boolean;
  hasMesh: boolean;
  isOnline: boolean;
  lastSeenAt: string | null;
};

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

const ALL_FEATURES = [
  { key: "turnpoints", label: "Turnpoints", maps: ["task_builder", "scoring", "dashboard_live", "public_live", "admin_site_preview"] },
  { key: "task_route", label: "Task route", maps: ["task_builder", "scoring", "dashboard_live", "public_live"] },
  { key: "task_cylinders", label: "Task cylinders", maps: ["task_builder", "scoring", "dashboard_live", "public_live"] },
  { key: "optimized_route", label: "Optimized route", maps: ["task_builder", "scoring"] },
  { key: "leg_labels", label: "Leg labels", maps: ["task_builder", "scoring"] },
  { key: "airspaces", label: "Airspace regions", maps: ["task_builder", "scoring", "dashboard_live"] },
  { key: "airspace_labels", label: "Airspace labels", maps: ["task_builder", "scoring", "dashboard_live"] },
  { key: "flight_track", label: "Flight track", maps: ["task_builder", "scoring", "logbook_replay", "dashboard_live", "public_live"] },
  { key: "track_highlight", label: "Track highlight", maps: ["scoring", "logbook_replay"] },
  { key: "live_positions", label: "Live positions", maps: ["dashboard_live", "public_live"] },
  { key: "live_labels", label: "Live pilot labels", maps: ["dashboard_live", "public_live"] },
  { key: "distance_summary", label: "Distance summary", maps: ["task_builder", "scoring"] },
  { key: "gps_button", label: "GPS follow button", maps: ["public_live"] },
  { key: "replay_scrubber", label: "Replay scrubber", maps: ["logbook_replay"] },
  { key: "replay_speed", label: "Replay speed", maps: ["logbook_replay"] },
  { key: "click_to_add_turnpoint", label: "Click to add TP", maps: ["task_builder"] },
  { key: "fullscreen_editor_panel", label: "Fullscreen editor", maps: ["task_builder", "scoring"] },
  { key: "fullscreen_toggle", label: "Fullscreen toggle", maps: ["task_builder", "scoring", "logbook_replay", "dashboard_live", "public_live", "admin_site_preview"] },
  { key: "2d_3d_toggle", label: "2D/3D toggle", maps: ["task_builder", "scoring", "logbook_replay", "dashboard_live", "public_live", "airspace_explorer", "admin_site_preview"] },
  { key: "basemap_selector", label: "Basemap selector", maps: ["task_builder", "scoring", "logbook_replay", "dashboard_live", "public_live", "admin_site_preview"] },
  { key: "altitude_slider", label: "Altitude slider", maps: ["task_builder", "scoring", "logbook_replay", "dashboard_live", "public_live", "admin_site_preview"] },
  { key: "airspace_regions", label: "Airspace regions (explorer)", maps: ["airspace_explorer"] },
  { key: "tfrs", label: "TFRs", maps: ["airspace_explorer"] },
  { key: "tfr_labels", label: "TFR labels", maps: ["airspace_explorer"] },
  { key: "category_toggles", label: "Category toggles", maps: ["airspace_explorer"] },
  { key: "export_openair", label: "Export OpenAir", maps: ["airspace_explorer"] },
  { key: "legend", label: "Legend", maps: ["airspace_explorer", "soaring_forecast"] },
  { key: "weather_raster", label: "Weather raster", maps: ["soaring_forecast"] },
  { key: "wind_barbs", label: "Wind barbs", maps: ["soaring_forecast"] },
  { key: "sounding_popup", label: "Sounding popup", maps: ["soaring_forecast"] },
  { key: "model_selector", label: "Model selector", maps: ["soaring_forecast"] },
  { key: "overlay_tabs", label: "Overlay tabs", maps: ["soaring_forecast"] },
  { key: "wind_barb_toggle", label: "Wind barb toggle", maps: ["soaring_forecast"] },
  { key: "opacity_slider", label: "Opacity slider", maps: ["soaring_forecast"] },
  { key: "time_scrubber", label: "Time scrubber", maps: ["soaring_forecast"] },
  { key: "model_run_selector", label: "Model run selector", maps: ["soaring_forecast"] },
] as const;
type UserSortField = "first_name" | "last_name" | "username" | "role" | "status";
type SortDir = "asc" | "desc";

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
    clearAdminUserDevice,
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
  const [meshNodesLoading, setMeshNodesLoading] = useState(false);
  const [userSearch, setUserSearch] = useState("");
  const [userSortField, setUserSortField] = useState<UserSortField>("last_name");
  const [userSortDir, setUserSortDir] = useState<SortDir>("asc");
  const [selectedUserIds, setSelectedUserIds] = useState<Record<number, boolean>>({});
  const [editingCredentials, setEditingCredentials] = useState<AdminUserRecord | null>(null);
  const [credentialsUsername, setCredentialsUsername] = useState("");
  const [credentialsPassword, setCredentialsPassword] = useState("");
  const [credentialsSaving, setCredentialsSaving] = useState(false);
  const [credentialsError, setCredentialsError] = useState<string | null>(null);

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
    let cancelled = false;
    const load = async () => {
      setMeshNodesLoading(true);
      try {
        const res = await fetch(`${apiBase}/api/admin/mesh-nodes?minutes=60`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok && !cancelled) {
          setMeshNodes((await res.json()) as MeshNode[]);
        }
      } catch {
        // ignore
      } finally {
        if (!cancelled) setMeshNodesLoading(false);
      }
    };
    void load();
    const interval = setInterval(load, 10_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [activeTab, token, apiBase]);

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
          Live Tracking
        </button>
      </div>
      {activeTab === "platform_users" ? (
        <SectionCard title="Platform users">
          <div className="stack form-block">
            {adminFeedback ? <div className={`status-chip ${adminFeedback.type}`}>{adminFeedback.text}</div> : null}
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
                    filteredSortedUsers.map((account) => (
                      <tr key={account.id}>
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
                          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                            <span
                              title="Auto-assigned when user pairs via the Aervyx app. BLE pairing always wins."
                              style={{ fontSize: "0.75rem", fontFamily: "monospace", opacity: account.mesh_device_id ? 1 : 0.4 }}
                            >
                              {account.mesh_device_id ?? "—"}
                            </span>
                            {account.mesh_device_id && (
                              <button
                                type="button"
                                className="ghost-button danger-button"
                                title="Clear device pairing (lost or stolen device)"
                                style={{ fontSize: "0.65rem", padding: "1px 4px", lineHeight: 1 }}
                                onClick={() => void clearAdminUserDevice(account.id)}
                              >
                                ✕
                              </button>
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
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} className="participant-table-empty">{userSearch ? "No matching users." : "No platform users found."}</td>
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
              <div className="results-table-wrap">
                <table className="results-table logbook-table">
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
                      totalDistanceKm={0}
                      optimizedDistanceKm={0}
                      track={null}
                      editable={false}
                      hideDistanceSummary
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
                  {ALL_FEATURES.map((feature) => (
                    <tr key={feature.key}>
                      <td>{feature.label}</td>
                      {MAP_CONTEXTS.map((ctx) => {
                        const native = (feature.maps as readonly string[]).includes(ctx.key);
                        const checked = mapOverlayConfig.config?.[ctx.key]?.[feature.key] === true || (native && mapOverlayConfig.config?.[ctx.key]?.[feature.key] !== false);
                        return (
                          <td key={ctx.key} style={{ textAlign: "center" }}>
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => {
                                setMapOverlayConfig((prev) => ({
                                  ...prev,
                                  config: {
                                    ...prev.config,
                                    [ctx.key]: {
                                      ...prev.config?.[ctx.key],
                                      [feature.key]: !checked,
                                    },
                                  },
                                }));
                              }}
                            />
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
            {siteSettingsFeedback ? <div className={`status-chip ${siteSettingsFeedback.type}`}>{siteSettingsFeedback.text}</div> : null}
            <MeshProfilesTable siteSettings={siteSettings} setSiteSettings={setSiteSettings} />
            <fieldset className="fieldset-cluster">
              <legend>MQTT / Mesh</legend>
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
                    MQTT enabled
                  </span>
                </label>
                <label className="stack compact">
                  <span>Broker mode</span>
                  <select
                    value={siteSettings.mqtt_broker_mode ?? "public"}
                    onChange={(event) =>
                      setSiteSettings((current) => ({
                        ...current,
                        mqtt_broker_mode: event.target.value,
                      }))
                    }
                  >
                    <option value="public">Public (mqtt.meshtastic.org)</option>
                    <option value="private">Private (custom broker)</option>
                  </select>
                </label>
                {(siteSettings.mqtt_broker_mode ?? "public") === "private" && (
                  <>
                    <label className="stack compact">
                      <span>MQTT host</span>
                      <input
                        type="text"
                        placeholder="mqtt.example.com"
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
                      <span>MQTT port</span>
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
                  </>
                )}
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
            <div className="button-row">
              <button type="button" onClick={() => void saveSiteSettings()}>
                Save Meshtastic settings
              </button>
            </div>
          </div>
        </SectionCard>
      ) : activeTab === "live_tracking" ? (
        <LiveTrackingTab debugStatus={debugStatus} refreshDebugStatus={refreshDebugStatus} meshNodes={meshNodes} meshNodesLoading={meshNodesLoading} />
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
  if (diffMs <= 30_000) return "green";
  if (diffMs <= 120_000) return "orange";
  return "red";
}

function LiveTrackingTab({
  debugStatus,
  refreshDebugStatus,
  meshNodes,
  meshNodesLoading,
}: {
  debugStatus: import("./types").DebugStatusResponse | null;
  refreshDebugStatus: () => void;
  meshNodes: MeshNode[];
  meshNodesLoading: boolean;
}) {
  const [expandedKeys, setExpandedKeys] = useState<Set<string>>(new Set());

  const unified = useMemo<UnifiedDevice[]>(() => {
    const byPilot = new Map<number, UnifiedDevice>();

    for (const session of (debugStatus?.active_sessions ?? [])) {
      byPilot.set(session.pilot_id, {
        key: `pilot-${session.pilot_id}`,
        pilot_id: session.pilot_id,
        pilot_name: session.pilot_name,
        profile_type: null,
        session,
        meshNode: null,
        hasPhone: true,
        hasMesh: false,
        isOnline: session.is_online,
        lastSeenAt: session.last_seen_at,
      });
    }

    for (const node of meshNodes) {
      if (node.pilot_id != null && byPilot.has(node.pilot_id)) {
        const existing = byPilot.get(node.pilot_id)!;
        const nodeTs = node.timestamp;
        const sessionTs = existing.lastSeenAt;
        const nodeIsNewer = !sessionTs || new Date(nodeTs).getTime() > new Date(sessionTs).getTime();
        byPilot.set(node.pilot_id, {
          ...existing,
          meshNode: node,
          hasMesh: true,
          profile_type: node.profile_type,
          lastSeenAt: nodeIsNewer ? nodeTs : sessionTs,
        });
      } else if (node.pilot_id != null) {
        byPilot.set(node.pilot_id, {
          key: `pilot-${node.pilot_id}`,
          pilot_id: node.pilot_id,
          pilot_name: node.pilot_name ?? node.device_id,
          profile_type: node.profile_type,
          session: null,
          meshNode: node,
          hasPhone: false,
          hasMesh: true,
          isOnline: false,
          lastSeenAt: node.timestamp,
        });
      } else {
        const deviceKey = `device-${node.device_id}`;
        byPilot.set(-(Math.random() * 1e9) | 0, {
          key: deviceKey,
          pilot_id: null,
          pilot_name: node.pilot_name ?? node.device_id,
          profile_type: node.profile_type,
          session: null,
          meshNode: node,
          hasPhone: false,
          hasMesh: true,
          isOnline: false,
          lastSeenAt: node.timestamp,
        });
      }
    }

    const list = Array.from(byPilot.values());
    list.sort((a, b) => {
      if (a.isOnline !== b.isOnline) return a.isOnline ? -1 : 1;
      const ta = a.lastSeenAt ? new Date(a.lastSeenAt).getTime() : 0;
      const tb = b.lastSeenAt ? new Date(b.lastSeenAt).getTime() : 0;
      return tb - ta;
    });
    return list;
  }, [debugStatus, meshNodes]);

  // Default-expand all rows to show position detail
  useEffect(() => {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      for (const d of unified) {
        next.add(d.key);
      }
      return next;
    });
  }, [unified]);

  const livePositions = useMemo<MapLivePosition[]>(() => {
    return unified.map((d): MapLivePosition => {
      // Prefer most-recent position source
      const useNode = d.meshNode != null && (
        !d.session?.last_seen_at ||
        new Date(d.meshNode.timestamp).getTime() > new Date(d.session.last_seen_at).getTime()
      );
      const lat = useNode ? d.meshNode!.lat : (d.session?.last_position?.lat ?? 0);
      const lon = useNode ? d.meshNode!.lon : (d.session?.last_position?.lon ?? 0);
      const alt = useNode ? d.meshNode!.alt : (d.session?.last_position?.alt ?? null);
      const speed = useNode ? d.meshNode!.speed : (d.session?.last_position?.speed ?? null);
      const heading = useNode ? (d.meshNode!.heading ?? null) : null;
      const battery = useNode ? d.meshNode!.battery_level : (d.session?.battery_level ?? null);
      const ts = d.lastSeenAt ?? new Date().toISOString();
      const posSource = useNode
        ? ((d.meshNode!.position_source ?? "mesh") as "cellular" | "mesh" | "other")
        : "cellular";
      return {
        id: d.key,
        pilotId: d.pilot_id,
        pilotName: d.pilot_name,
        latitude: lat,
        longitude: lon,
        altitudeM: alt,
        speedKmh: speed,
        heading: heading,
        timestamp: ts,
        batteryLevel: battery,
        source: useNode ? d.meshNode!.source : (d.session?.source ?? null),
        aircraftType: "hang_glider",
        profileType: (d.profile_type ?? "pilot") as "pilot" | "driver" | "stationary_node",
        positionSource: posSource,
      };
    }).filter((p) => p.latitude !== 0 || p.longitude !== 0);
  }, [unified]);

  const active_sessions = debugStatus?.active_sessions ?? [];
  const recent_sos_alerts = debugStatus?.recent_sos_alerts ?? [];
  const position_stats = debugStatus?.position_stats ?? { last_hour_total: 0, last_hour_cellular: 0, last_hour_mesh: 0 };
  const sse_subscriber_count = debugStatus?.sse_subscriber_count ?? 0;
  const meshRatio = position_stats.last_hour_total > 0 ? Math.round((position_stats.last_hour_mesh / position_stats.last_hour_total) * 100) : 0;

  function toggleExpand(key: string) {
    setExpandedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <SectionCard title="Live Tracking" description="Unified view of all active tracking sessions and mesh nodes.">
      <div className="stack form-block">
        {/* A) Status cards */}
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "140px", padding: "12px 16px" }}>
            <div className="hint" style={{ marginBottom: "4px" }}>Live Viewers</div>
            <strong style={{ fontSize: "1.25rem" }}>{sse_subscriber_count}</strong>
          </div>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "140px", padding: "12px 16px" }}>
            <div className="hint" style={{ marginBottom: "4px" }}>Connected Sessions</div>
            <strong style={{ fontSize: "1.25rem" }}>{active_sessions.length}</strong>
          </div>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "140px", padding: "12px 16px" }}>
            <div className="hint" style={{ marginBottom: "4px" }}>Mesh Nodes</div>
            <strong style={{ fontSize: "1.25rem" }}>{meshNodesLoading && meshNodes.length === 0 ? "…" : meshNodes.length}</strong>
          </div>
        </div>

        {/* B) Map */}
        <div style={{ height: 400, borderRadius: 8, overflow: "hidden" }}>
          <TaskMap
            turnpoints={[]}
            taskPoints={[]}
            optimizedRoute={[]}
            legMetrics={[]}
            totalDistanceKm={0}
            optimizedDistanceKm={0}
            track={null}
            editable={false}
            hideDistanceSummary
            livePositions={livePositions}
            fitKey={`live-tracking-${livePositions.length}`}
          />
        </div>

        {/* C) Unified tracking table */}
        <div className="participant-table-wrap">
          <table className="participant-table" style={{ fontSize: "0.82rem" }}>
            <thead>
              <tr>
                <th style={{ width: "24px" }}></th>
                <th>Status</th>
                <th>Pilot</th>
                <th>Sources</th>
                <th>Task</th>
                <th>Positions</th>
                <th>Battery</th>
                <th>Interval</th>
                <th>Last Fix</th>
              </tr>
            </thead>
            <tbody>
              {unified.length ? (
                unified.map((d) => {
                  const color = lastSeenColor(d.lastSeenAt);
                  const borderColor = color === "green" ? "#22c55e" : color === "orange" ? "#f59e0b" : "#ef4444";
                  const lastFixColor = color === "green" ? "inherit" : color === "orange" ? "#f59e0b" : "#ef4444";
                  const isExpanded = expandedKeys.has(d.key);
                  const canExpand = true; // Always expandable for position detail

                  // Summary values: prefer session for task/positions/interval; fallback to mesh
                  const interval = d.session && d.session.positions_last_60s > 0
                    ? Math.round(60 / d.session.positions_last_60s)
                    : null;

                  // Battery: pick whichever source is most recent
                  let battery: number | null = null;
                  if (d.hasPhone && d.hasMesh) {
                    const sessionTs = d.session?.last_seen_at ? new Date(d.session.last_seen_at).getTime() : 0;
                    const meshTs = d.meshNode?.timestamp ? new Date(d.meshNode.timestamp).getTime() : 0;
                    battery = sessionTs >= meshTs ? (d.session?.battery_level ?? null) : (d.meshNode?.battery_level ?? null);
                  } else if (d.hasPhone) {
                    battery = d.session?.battery_level ?? null;
                  } else {
                    battery = d.meshNode?.battery_level ?? null;
                  }

                  const deviceIdHint = d.session?.device_id ?? d.meshNode?.device_id ?? null;

                  return (
                    <Fragment key={d.key}>
                      <tr style={{ borderLeft: `3px solid ${borderColor}` }}>
                        <td
                          className={canExpand ? `tracking-expand-toggle${isExpanded ? " expanded" : ""}` : ""}
                          onClick={canExpand ? () => toggleExpand(d.key) : undefined}
                        >
                          {canExpand ? (isExpanded ? "▾" : "▸") : ""}
                        </td>
                        <td>
                          <span style={{
                            display: "inline-block",
                            width: 10,
                            height: 10,
                            borderRadius: "50%",
                            backgroundColor: d.isOnline ? "#22c55e" : color === "orange" ? "#f59e0b" : "#6b7280",
                            boxShadow: d.isOnline ? "0 0 6px #22c55e80" : undefined,
                          }} title={d.isOnline ? "Online" : "Offline"} />
                        </td>
                        <td>
                          <strong>{d.pilot_name}</strong>
                          {deviceIdHint && (
                            <div style={{ fontFamily: "monospace", fontSize: "0.72rem", color: "var(--muted)" }}>{deviceIdHint}</div>
                          )}
                        </td>
                        <td>
                          {d.hasPhone && <span className="tracking-source-pill phone">Phone</span>}
                          {d.hasMesh && <span className="tracking-source-pill mesh">Mesh</span>}
                        </td>
                        <td>{d.session ? (d.session.task_name ?? "Free flight") : "\u2014"}</td>
                        <td>{d.session ? d.session.position_count.toLocaleString() : "\u2014"}</td>
                        <td>{battery != null ? `${battery}%` : "\u2014"}</td>
                        <td>{interval != null ? `every ${interval}s` : "\u2014"}</td>
                        <td style={{ color: lastFixColor }}>{relativeTime(d.lastSeenAt)}</td>
                      </tr>
                      {isExpanded && (
                        <>
                          {/* Phone sub-row */}
                          {d.hasPhone && (
                            <tr className="tracking-sub-row">
                              <td></td>
                              <td>
                                <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", backgroundColor: "#3b82f6", marginRight: "4px" }} />
                              </td>
                              <td style={{ fontFamily: "monospace", fontSize: "0.72rem", color: "var(--muted)" }}>Phone</td>
                              <td colSpan={2}>
                                {d.session?.last_position
                                  ? `${d.session.last_position.lat.toFixed(5)}, ${d.session.last_position.lon.toFixed(5)}`
                                  : "\u2014"}
                                {d.session?.last_position?.alt != null && ` · ${Math.round(d.session.last_position.alt)}m`}
                                {d.session?.last_position?.speed != null && ` · ${d.session.last_position.speed.toFixed(1)} km/h`}
                              </td>
                              <td>{d.session?.battery_level != null ? `${d.session.battery_level}%` : "\u2014"}</td>
                              <td colSpan={2} style={{ color: lastSeenColor(d.session?.last_seen_at) === "green" ? "inherit" : lastSeenColor(d.session?.last_seen_at) === "orange" ? "#f59e0b" : "#ef4444" }}>
                                {relativeTime(d.session?.last_seen_at)}
                              </td>
                            </tr>
                          )}
                          {/* Mesh sub-row */}
                          {d.hasMesh && (
                            <tr className="tracking-sub-row">
                              <td></td>
                              <td>
                                <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", backgroundColor: "#22c55e", marginRight: "4px" }} />
                              </td>
                              <td style={{ fontFamily: "monospace", fontSize: "0.72rem", color: "var(--muted)" }}>Mesh</td>
                              <td colSpan={2}>
                                {d.meshNode
                                  ? `${d.meshNode.lat.toFixed(5)}, ${d.meshNode.lon.toFixed(5)}`
                                  : "\u2014"}
                                {d.meshNode?.alt != null && ` · ${Math.round(d.meshNode.alt)}m`}
                                {d.meshNode?.speed != null && ` · ${d.meshNode.speed.toFixed(1)} km/h`}
                              </td>
                              <td>{d.meshNode?.battery_level != null ? `${d.meshNode.battery_level}%` : "\u2014"}</td>
                              <td colSpan={2} style={{ color: lastSeenColor(d.meshNode?.timestamp) === "green" ? "inherit" : lastSeenColor(d.meshNode?.timestamp) === "orange" ? "#f59e0b" : "#ef4444" }}>
                                {relativeTime(d.meshNode?.timestamp)}
                              </td>
                            </tr>
                          )}
                        </>
                      )}
                    </Fragment>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={9} className="participant-table-empty">No active tracking sessions or mesh nodes.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* D) Bottom cards: SOS Alerts + Position Sources */}
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          <div
            className="section-card"
            style={{
              flex: "1 1 0",
              minWidth: "280px",
              padding: "12px 16px",
              borderLeft: recent_sos_alerts.length ? "3px solid #ef4444" : undefined,
            }}
          >
            <div style={{ marginBottom: "8px" }}>
              <strong>SOS Alerts</strong>
            </div>
            {recent_sos_alerts.length ? (
              <div className="stack" style={{ gap: "6px" }}>
                {recent_sos_alerts.map((alert, idx) => (
                  <div key={`${alert.pilot_id}-${alert.timestamp}-${idx}`} style={{ display: "flex", gap: "8px", alignItems: "baseline", fontSize: "0.875rem" }}>
                    <strong style={{ color: "#ef4444" }}>{alert.pilot_name}</strong>
                    <span className="hint">{relativeTime(alert.timestamp)}</span>
                    <span>{alert.message}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="hint">No active alerts</div>
            )}
          </div>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "280px", padding: "12px 16px" }}>
            <div style={{ marginBottom: "8px" }}>
              <strong>Position Sources</strong>
              <span className="hint" style={{ marginLeft: "8px" }}>(last hour)</span>
            </div>
            <div style={{ display: "flex", gap: "16px", fontSize: "0.875rem" }}>
              <div>
                <div className="hint">Total</div>
                <strong>{position_stats.last_hour_total.toLocaleString()}</strong>
              </div>
              <div>
                <div className="hint">Cellular</div>
                <strong>{position_stats.last_hour_cellular.toLocaleString()}</strong>
              </div>
              <div>
                <div className="hint">Mesh</div>
                <strong>{position_stats.last_hour_mesh.toLocaleString()}</strong>
              </div>
              <div>
                <div className="hint">Mesh ratio</div>
                <strong>{meshRatio}%</strong>
              </div>
            </div>
          </div>
        </div>

        {/* E) Refresh */}
        <div className="button-row">
          <button type="button" className="ghost-button" onClick={refreshDebugStatus}>
            Refresh now
          </button>
        </div>
      </div>
    </SectionCard>
  );
}

/* ------------------------------------------------------------------ */
/*  Meshtastic Profiles table                                          */
/* ------------------------------------------------------------------ */

const DEFAULT_MESH_PROFILES: Record<string, Record<string, unknown>> = {
  pilot: { role: "tracker", rebroadcast_mode: "all", gps_mode: "enabled", position_broadcast_secs: 30, smart_position_enabled: true, smart_min_distance: 100, smart_min_interval: 30, modem_preset: "long_fast", hop_limit: 3, power_saving: false, bluetooth_enabled: true, wifi_enabled: false, position_flags: 1, display_timeout_secs: 30, telemetry_interval_secs: 86400 },
  driver: { role: "client", rebroadcast_mode: "all", gps_mode: "enabled", position_broadcast_secs: 120, smart_position_enabled: true, smart_min_distance: 200, smart_min_interval: 60, modem_preset: "long_fast", hop_limit: 3, power_saving: false, bluetooth_enabled: true, wifi_enabled: false, position_flags: 1, display_timeout_secs: 60, telemetry_interval_secs: 86400 },
  driver_wifi: { role: "client", rebroadcast_mode: "all", gps_mode: "enabled", position_broadcast_secs: 60, smart_position_enabled: true, smart_min_distance: 200, smart_min_interval: 30, modem_preset: "long_fast", hop_limit: 3, power_saving: false, bluetooth_enabled: true, wifi_enabled: true, position_flags: 1, display_timeout_secs: 60, telemetry_interval_secs: 86400 },
  repeater: { role: "router", rebroadcast_mode: "all", gps_mode: "enabled", position_broadcast_secs: 300, smart_position_enabled: false, smart_min_distance: 0, smart_min_interval: 0, modem_preset: "long_fast", hop_limit: 3, power_saving: false, bluetooth_enabled: true, wifi_enabled: true, position_flags: 1, display_timeout_secs: 0, telemetry_interval_secs: 86400 },
};

const PROFILE_KEYS = ["pilot", "driver", "driver_wifi", "repeater"] as const;
const PROFILE_LABELS: Record<string, string> = { pilot: "Pilot", driver: "Driver", driver_wifi: "Driver Wi-Fi", repeater: "Repeater" };

// Role options shown in the dropdown, per-profile.
// Pilots are always trackers — picking anything else would break the firmware's
// position-priority handling. Every other profile gets the full set.
const ROLE_OPTIONS_PILOT = ["tracker"] as const;
const ROLE_OPTIONS_OTHER = ["tracker", "router", "client"] as const;

type ProfileRowDef = {
  key: string;
  label: string;
  kind: "select" | "number" | "boolean";
  options?: string[];
  // Optional override: per-profile-key option lists.
  // When present, takes precedence over `options` for that profile column.
  perProfileOptions?: Record<string, readonly string[]>;
  min?: number;
  max?: number;
  description?: string;
};

const PROFILE_ROW_GROUPS: { group: string; readonly?: boolean; rows: ProfileRowDef[] }[] = [
  {
    group: "Role",
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
    ],
  },
  {
    group: "Position",
    rows: [
      { key: "position_broadcast_secs", label: "Broadcast (s)", kind: "number", min: 0, description: "How often (in seconds) the device broadcasts its GPS position to the mesh network. Lower values give more frequent updates but increase radio traffic and battery drain. Setting to 0 reverts to firmware default (900s / 15 min). Pilots typically use 30s, drivers 60-120s, repeaters 300s." },
      { key: "smart_position_enabled", label: "Smart pos.", kind: "boolean", description: "When enabled, the device sends position updates early if it detects significant movement (based on min distance and min interval thresholds), rather than waiting for the full broadcast interval. Helps capture turns and altitude changes for pilots in flight." },
      { key: "smart_min_distance", label: "Min dist (m)", kind: "number", min: 0, description: "Minimum distance traveled (in meters) before triggering a smart position update. Only applies when smart position is enabled. Setting to 0 reverts to firmware default (100m). Lower values capture more detail but increase radio traffic. 100m is good for pilots, 200m for drivers." },
      { key: "smart_min_interval", label: "Min interval (s)", kind: "number", min: 0, description: "Minimum time (in seconds) between smart position updates. Prevents excessive updates during rapid movement even if the distance threshold is met repeatedly. Setting to 0 reverts to firmware default (30s). Only applies when smart position is enabled." },
      { key: "position_flags", label: "Position flags", kind: "number", min: 0, description: "Bitmask telling the firmware which extra fields to include in each position packet (altitude, heading, speed, satellites, etc.). 1 = altitude only (default for pilots), 0 = position only. See Meshtastic POSITION_APP docs for the full bitmask. Most installs should leave this at 1." },
    ],
  },
  {
    group: "Connectivity",
    rows: [
      { key: "wifi_enabled", label: "Wi-Fi", kind: "boolean", description: "Whether Wi-Fi is active on the device. When enabled, the device can connect to a WiFi network for direct MQTT over the internet (bypassing phone proxy). Uses significantly more power than BLE-only. Note: on ESP32 devices, WiFi takes precedence and disables Bluetooth automatically." },
      { key: "display_timeout_secs", label: "Display timeout (s)", kind: "number", min: 0, description: "Seconds before the device screen turns off to save power. Setting to 0 reverts to firmware default (600s / 10 minutes), it does NOT disable the screen. Use a very low value like 1 for effectively no screen, or use power saving mode for headless nodes." },
      { key: "bluetooth_enabled", label: "Bluetooth", kind: "boolean", description: "BLE is required for phone-to-device communication. Disabling will prevent the Aervyx app from configuring the device. Only disable for headless repeaters running entirely over Wi-Fi." },
    ],
  },
  {
    group: "LoRa radio",
    rows: [
      { key: "modem_preset", label: "Modem preset", kind: "select", options: ["long_fast", "long_moderate", "long_slow", "very_long_slow", "medium_slow", "medium_fast", "short_slow", "short_fast", "short_turbo", "long_turbo"], description: "LoRa radio modulation settings. All devices on the same mesh must use the same preset or they will not see each other. Long Fast is the standard competition preset." },
      { key: "hop_limit", label: "Hop limit", kind: "number", min: 1, max: 7, description: "Maximum number of times a packet can be relayed across the mesh (1-7). 3 is the standard value — higher values increase coverage but add congestion." },
      { key: "rebroadcast_mode", label: "Rebroadcast", kind: "select", options: ["all", "all_skip_decoding", "local_only", "known_only", "none", "core_portnums_only"], description: "Which packets this device will relay onward. \"all\" is the recommended default. \"none\" turns the device into a leaf node." },
      { key: "gps_mode", label: "GPS mode", kind: "select", options: ["disabled", "enabled", "not_present"], description: "Controls the internal GPS receiver. \"enabled\" lets the device produce its own position fixes. \"not_present\" tells the firmware there is no GPS at all (e.g. base station fed by phone)." },
    ],
  },
  {
    group: "Power & telemetry",
    rows: [
      { key: "power_saving", label: "Power saving", kind: "boolean", description: "Aggressively conserves power. Not recommended for competition devices that need to be responsive — drops radio responsiveness." },
      { key: "telemetry_interval_secs", label: "Telemetry (s)", kind: "number", min: 0, description: "How often the device reports telemetry (battery, voltage, temperature) to the mesh. A high value (86400 = 24 hours) effectively suppresses unnecessary traffic during a competition." },
    ],
  },
];

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

  const cellStyle = { padding: "2px 4px", verticalAlign: "middle" } as const;
  const inputStyle = { fontSize: "0.75rem", padding: "2px 4px", width: "100%", minWidth: "80px", boxSizing: "border-box" } as const;
  const selectStyle = { ...inputStyle, minWidth: "110px" } as const;
  const groupHeaderStyle = { fontSize: "0.7rem", fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase" as const, color: "var(--color-hint, #888)", background: "var(--color-surface-alt, #f4f4f5)", padding: "4px 8px", borderTop: "1px solid var(--color-border, #e5e7eb)" };

  return (
    <div style={{ marginTop: "16px" }}>
      <div style={{ fontWeight: 600, fontSize: "0.875rem", marginBottom: "8px" }}>Meshtastic Profiles</div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ borderCollapse: "collapse", fontSize: "0.8rem", width: "100%", minWidth: "520px" }}>
          <thead>
            <tr>
              <th style={{ textAlign: "left", padding: "4px 8px", fontSize: "0.75rem", fontWeight: 600, borderBottom: "1px solid var(--color-border, #e5e7eb)", minWidth: "130px" }}>Setting</th>
              {PROFILE_KEYS.map((pk) => (
                <th key={pk} style={{ textAlign: "center", padding: "4px 8px", fontSize: "0.75rem", fontWeight: 600, borderBottom: "1px solid var(--color-border, #e5e7eb)", minWidth: "110px" }}>
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
                {rows.map((row) => (
                  <tr key={row.key} style={{ borderBottom: "1px solid var(--color-border-subtle, #f3f4f6)" }}>
                    <td style={{ ...cellStyle, padding: "3px 8px", fontSize: "0.75rem", color: "var(--color-muted, #6b7280)" }}>
                      <span style={{ display: "flex", alignItems: "center", gap: "4px", whiteSpace: "nowrap" }}>
                        {row.label}
                        {row.description && (
                          <button
                            type="button"
                            onClick={() => setExpandedInfo(expandedInfo === row.key ? null : row.key)}
                            title={row.description}
                            style={{ background: "none", border: "none", cursor: "pointer", padding: "0 2px", fontSize: "0.7rem", color: expandedInfo === row.key ? "var(--color-accent, #2563eb)" : "var(--color-hint, #9ca3af)", lineHeight: 1 }}
                          >
                            &#9432;
                          </button>
                        )}
                      </span>
                      {expandedInfo === row.key && row.description && (
                        <div style={{ fontSize: "0.65rem", color: "var(--color-hint, #6b7280)", marginTop: "4px", whiteSpace: "normal", maxWidth: "260px", lineHeight: 1.4 }}>
                          {row.description}
                        </div>
                      )}
                    </td>
                    {PROFILE_KEYS.map((pk) => {
                      const rawVal = profiles[pk]?.[row.key];
                      const options = row.perProfileOptions?.[pk] ?? row.options ?? [];
                      const lockedSelect = row.kind === "select" && options.length === 1;
                      return (
                        <td key={pk} style={{ ...cellStyle, textAlign: "center" }}>
                          {row.kind === "boolean" ? (
                            <input
                              type="checkbox"
                              checked={Boolean(rawVal)}
                              onChange={(e) => updateCell(pk, row.key, e.target.checked)}
                              style={{ cursor: "pointer" }}
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
                          ) : (
                            <input
                              type="number"
                              min={row.min}
                              max={row.max}
                              value={Number(rawVal ?? 0)}
                              onChange={(e) => updateCell(pk, row.key, Number(e.target.value))}
                              style={inputStyle}
                            />
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint" style={{ marginTop: "6px" }}>Profile defaults are applied when mesh_profiles is null. Edit cells to customise per-profile settings.</p>
    </div>
  );
}
