"use client";

import { Fragment, useCallback, useEffect, useMemo, useState } from "react";

import { type MapTaskPoint, type MapTurnpoint, TaskMap } from "../TaskMap";
import { SectionCard } from "../SectionCard";
import type { AdminSiteRecord, AdminUserRecord, DebugStatusResponse, MapOverlayConfigRecord, SiteSettingsRecord, User } from "./types";

type AdminTab = "platform_users" | "site_settings" | "sites_database" | "debugging" | "map_config";

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
  } = props;
  const [activeTab, setActiveTab] = useState<AdminTab>("platform_users");
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
    if (activeTab !== "debugging") return;
    refreshDebugStatus();
    const interval = setInterval(() => {
      refreshDebugStatus();
    }, 5000);
    return () => clearInterval(interval);
  }, [activeTab, refreshDebugStatus]);

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
          className={activeTab === "debugging" ? "tab-button active" : "tab-button"}
          onClick={() => setActiveTab("debugging")}
        >
          Debugging
        </button>
        <button
          type="button"
          className={activeTab === "map_config" ? "tab-button active" : "tab-button"}
          onClick={() => setActiveTab("map_config")}
        >
          Map overlays
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
      ) : activeTab === "debugging" ? (
        <DebugTab debugStatus={debugStatus} refreshDebugStatus={refreshDebugStatus} />
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
            </div>
            <p className="hint">Use 0 to disable smoothing. Smoothing values allow 0 to 30 seconds. Maximum map pitch allows 0 to 85 degrees, where 0 is top-down and higher values tilt closer to horizontal.</p>
            <MeshProfilesTable siteSettings={siteSettings} setSiteSettings={setSiteSettings} />
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

function DebugTab({ debugStatus, refreshDebugStatus }: { debugStatus: import("./types").DebugStatusResponse | null; refreshDebugStatus: () => void }) {
  if (!debugStatus) {
    return (
      <SectionCard title="Debugging">
        <div className="stack form-block">
          <div className="status-chip pending">Loading debug status...</div>
        </div>
      </SectionCard>
    );
  }

  const { sse_subscriber_count, active_sessions, recent_sos_alerts, position_stats } = debugStatus;
  const meshRatio = position_stats.last_hour_total > 0 ? Math.round((position_stats.last_hour_mesh / position_stats.last_hour_total) * 100) : 0;

  return (
    <SectionCard title="Debugging" description="Live tracking system diagnostics and connected device status.">
      <div className="stack form-block">
        {/* Status cards row */}
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "160px", padding: "12px 16px" }}>
            <div className="hint" style={{ marginBottom: "4px" }}>Live Viewers</div>
            <strong style={{ fontSize: "1.25rem" }}>{sse_subscriber_count}</strong>
          </div>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "160px", padding: "12px 16px" }}>
            <div className="hint" style={{ marginBottom: "4px" }}>Connected Devices</div>
            <strong style={{ fontSize: "1.25rem" }}>{active_sessions.length}</strong>
          </div>
        </div>

        {/* Connected Devices table */}
        <div className="participant-table-wrap">
          <table className="participant-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Pilot</th>
                <th>Source</th>
                <th>Mesh</th>
                <th>Task</th>
                <th>Positions</th>
                <th>Interval</th>
                <th>Last Fix</th>
              </tr>
            </thead>
            <tbody>
              {active_sessions.length ? (
                active_sessions.map((session) => {
                  const color = lastSeenColor(session.last_seen_at);
                  const borderColor = color === "green" ? "#22c55e" : color === "orange" ? "#f59e0b" : "#ef4444";
                  const interval = session.positions_last_60s > 0 ? Math.round(60 / session.positions_last_60s) : null;
                  const sourceLabel = session.source === "app" ? "App (cellular)" : session.source === "mqtt_gateway" ? "Mesh (MQTT)" : session.source ?? "\u2014";
                  const lastFixColor = color === "green" ? "inherit" : color === "orange" ? "#f59e0b" : "#ef4444";
                  return (
                    <tr key={session.pilot_id} style={{ borderLeft: `3px solid ${borderColor}` }}>
                      <td>
                        <span style={{
                          display: "inline-block",
                          width: 10,
                          height: 10,
                          borderRadius: "50%",
                          backgroundColor: session.is_online ? "#22c55e" : "#6b7280",
                          boxShadow: session.is_online ? "0 0 6px #22c55e80" : undefined,
                        }} title={session.is_online ? "Online" : "Offline"} />
                      </td>
                      <td><strong>{session.pilot_name}</strong></td>
                      <td>{sourceLabel}</td>
                      <td>
                        <span style={{
                          display: "inline-block",
                          width: 10,
                          height: 10,
                          borderRadius: "50%",
                          backgroundColor: session.has_mesh ? "#22c55e" : "#6b7280",
                          boxShadow: session.has_mesh ? "0 0 6px #22c55e80" : undefined,
                        }} title={session.has_mesh ? "Meshtastic active" : "No mesh"} />
                      </td>
                      <td>{session.task_name ?? "Free flight"}</td>
                      <td>{session.position_count.toLocaleString()}</td>
                      <td>{interval != null ? `every ${interval}s` : "\u2014"}</td>
                      <td style={{ color: lastFixColor }}>{relativeTime(session.last_seen_at)}</td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} className="participant-table-empty">No active tracking sessions. Enable Debug Mode in the mobile app to test.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Bottom row: SOS Alerts + Position Sources */}
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
  pilot: { role: "tracker", rebroadcast_mode: "all", gps_mode: "enabled", position_broadcast_secs: 30, smart_position_enabled: true, smart_min_distance: 100, smart_min_interval: 30, modem_preset: "long_fast", hop_limit: 3, power_saving: false, bluetooth_enabled: true, wifi_enabled: false, position_flags: 1, display_timeout_secs: 30, telemetry_interval_secs: 900 },
  driver: { role: "client", rebroadcast_mode: "all", gps_mode: "enabled", position_broadcast_secs: 120, smart_position_enabled: true, smart_min_distance: 200, smart_min_interval: 60, modem_preset: "long_fast", hop_limit: 3, power_saving: false, bluetooth_enabled: true, wifi_enabled: false, position_flags: 1, display_timeout_secs: 60, telemetry_interval_secs: 900 },
  driver_wifi: { role: "client", rebroadcast_mode: "all", gps_mode: "enabled", position_broadcast_secs: 60, smart_position_enabled: true, smart_min_distance: 200, smart_min_interval: 30, modem_preset: "long_fast", hop_limit: 3, power_saving: false, bluetooth_enabled: true, wifi_enabled: true, position_flags: 1, display_timeout_secs: 60, telemetry_interval_secs: 900 },
  repeater: { role: "router", rebroadcast_mode: "all", gps_mode: "enabled", position_broadcast_secs: 300, smart_position_enabled: false, smart_min_distance: 0, smart_min_interval: 0, modem_preset: "long_fast", hop_limit: 3, power_saving: false, bluetooth_enabled: true, wifi_enabled: true, position_flags: 1, display_timeout_secs: 0, telemetry_interval_secs: 3600 },
};

const PROFILE_KEYS = ["pilot", "driver", "driver_wifi", "repeater"] as const;
const PROFILE_LABELS: Record<string, string> = { pilot: "Pilot", driver: "Driver", driver_wifi: "Driver Wi-Fi", repeater: "Repeater" };

type ProfileRowDef = {
  key: string;
  label: string;
  kind: "select" | "number" | "boolean";
  options?: string[];
  min?: number;
  max?: number;
};

const PROFILE_ROW_GROUPS: { group: string; rows: ProfileRowDef[] }[] = [
  {
    group: "Device",
    rows: [
      { key: "role", label: "Role", kind: "select", options: ["client", "tracker", "router"] },
      { key: "rebroadcast_mode", label: "Rebroadcast", kind: "select", options: ["all", "all_skip_decoding", "local_only", "known_only", "none", "core_portnums_only"] },
      { key: "power_saving", label: "Power saving", kind: "boolean" },
    ],
  },
  {
    group: "Position & GPS",
    rows: [
      { key: "gps_mode", label: "GPS mode", kind: "select", options: ["disabled", "enabled", "not_present"] },
      { key: "position_broadcast_secs", label: "Broadcast (s)", kind: "number", min: 0 },
      { key: "smart_position_enabled", label: "Smart pos.", kind: "boolean" },
      { key: "smart_min_distance", label: "Min dist (m)", kind: "number", min: 0 },
      { key: "smart_min_interval", label: "Min interval (s)", kind: "number", min: 0 },
    ],
  },
  {
    group: "Radio",
    rows: [
      { key: "modem_preset", label: "Modem preset", kind: "select", options: ["long_fast", "long_slow", "very_long_slow", "medium_slow", "medium_fast", "short_slow", "short_fast", "long_moderate", "short_turbo", "long_turbo"] },
      { key: "hop_limit", label: "Hop limit", kind: "number", min: 0, max: 7 },
    ],
  },
  {
    group: "Connectivity",
    rows: [
      { key: "bluetooth_enabled", label: "Bluetooth", kind: "boolean" },
      { key: "wifi_enabled", label: "Wi-Fi", kind: "boolean" },
    ],
  },
  {
    group: "Display & Telemetry",
    rows: [
      { key: "display_timeout_secs", label: "Display timeout (s)", kind: "number", min: 0 },
      { key: "telemetry_interval_secs", label: "Telemetry (s)", kind: "number", min: 0 },
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
                    <td style={{ ...cellStyle, padding: "3px 8px", fontSize: "0.75rem", color: "var(--color-muted, #6b7280)", whiteSpace: "nowrap" }}>{row.label}</td>
                    {PROFILE_KEYS.map((pk) => {
                      const rawVal = profiles[pk]?.[row.key];
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
                            >
                              {(row.options ?? []).map((opt) => (
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
