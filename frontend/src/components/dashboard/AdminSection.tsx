"use client";

import { useEffect, useMemo, useState } from "react";

import { type MapTaskPoint, type MapTurnpoint, TaskMap } from "../TaskMap";
import { SectionCard } from "../SectionCard";
import type { AdminSiteRecord, AdminUserRecord, DebugStatusResponse, SiteSettingsRecord, User } from "./types";

type AdminTab = "platform_users" | "site_settings" | "sites_database" | "debugging";

export interface AdminSectionProps {
  user: User | null;
  adminUsers: AdminUserRecord[];
  setAdminUsers: (users: AdminUserRecord[] | ((current: AdminUserRecord[]) => AdminUserRecord[])) => void;
  adminFeedback: { type: "success" | "error"; text: string } | null;
  saveAdminUser: (userRecord: AdminUserRecord) => void;
  deleteAdminUser: (userRecord: AdminUserRecord) => void;
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
}

export default function AdminSection(props: AdminSectionProps) {
  const {
    user,
    adminUsers,
    setAdminUsers,
    adminFeedback,
    saveAdminUser,
    deleteAdminUser,
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
  } = props;
  const [activeTab, setActiveTab] = useState<AdminTab>("platform_users");
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
          Sites database
        </button>
        <button
          type="button"
          className={activeTab === "debugging" ? "tab-button active" : "tab-button"}
          onClick={() => setActiveTab("debugging")}
        >
          Debugging
        </button>
      </div>
      {activeTab === "platform_users" ? (
        <SectionCard title="Platform users" description="Admins can manage organizer and pilot accounts for the entire platform here.">
          <div className="stack form-block">
            {adminFeedback ? <div className={`status-chip ${adminFeedback.type}`}>{adminFeedback.text}</div> : null}
            <div className="participant-table-wrap">
              <table className="participant-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Username</th>
                    <th>Role</th>
                    <th>Email</th>
                    <th>Linked pilot</th>
                    <th>Status</th>
                    <th className="participant-table-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {adminUsers.length ? (
                    adminUsers.map((account) => (
                      <tr key={account.id}>
                        <td><strong>{account.full_name}</strong></td>
                        <td>{account.username}</td>
                        <td>
                          <select
                            value={account.role}
                            disabled={account.id === user?.id}
                            onChange={(event) => setAdminUsers((current) => current.map((entry) => entry.id === account.id ? { ...entry, role: event.target.value as AdminUserRecord["role"] } : entry))}
                          >
                            <option value="admin">Admin</option>
                            <option value="organizer">Organizer</option>
                            <option value="pilot">Pilot</option>
                          </select>
                        </td>
                        <td>{account.email ?? "-"}</td>
                        <td>{account.pilot_name ?? "-"}</td>
                        <td>
                          <label className="task-advanced-toggle">
                            <input
                              type="checkbox"
                              checked={account.is_active}
                              disabled={account.id === user?.id}
                              onChange={(event) => setAdminUsers((current) => current.map((entry) => entry.id === account.id ? { ...entry, is_active: event.target.checked } : entry))}
                            />
                            <span>{account.is_active ? "Active" : "Disabled"}</span>
                          </label>
                        </td>
                        <td className="participant-table-actions">
                          <div className="compact-slot-actions">
                            <button type="button" className="ghost-button" onClick={() => void saveAdminUser(account)}>Save</button>
                            <button type="button" className="ghost-button danger-button" disabled={account.id === user?.id} onClick={() => void deleteAdminUser(account)}>Delete</button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} className="participant-table-empty">No platform users found.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </SectionCard>
      ) : activeTab === "sites_database" ? (
        <SectionCard title="Sites database" description="Maintain the site catalog used by logbook site matching and future same-site flight discovery.">
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
                        <td colSpan={4} className="participant-table-empty">No sites in the database yet.</td>
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
      ) : (
        <SectionCard title="Site settings" description="These admin-only settings control replay smoothing and map behavior across the dashboard.">
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

function batteryColor(level: number | null): string {
  if (level == null) return "inherit";
  if (level > 50) return "#22c55e";
  if (level >= 20) return "#f59e0b";
  return "#ef4444";
}

function DebugTab({ debugStatus, refreshDebugStatus }: { debugStatus: import("./types").DebugStatusResponse | null; refreshDebugStatus: () => void }) {
  if (!debugStatus) {
    return (
      <SectionCard title="Debugging" description="Live tracking system diagnostics and connected device status.">
        <div className="stack form-block">
          <div className="status-chip pending">Loading debug status...</div>
        </div>
      </SectionCard>
    );
  }

  const { mqtt_connected, mqtt_last_message_at, sse_subscriber_count, active_sessions, recent_sos_alerts, position_stats } = debugStatus;
  const meshRatio = position_stats.last_hour_total > 0 ? Math.round((position_stats.last_hour_mesh / position_stats.last_hour_total) * 100) : 0;

  return (
    <SectionCard title="Debugging" description="Live tracking system diagnostics and connected device status.">
      <div className="stack form-block">
        {/* Status cards row */}
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "160px", padding: "12px 16px" }}>
            <div className="hint" style={{ marginBottom: "4px" }}>API</div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", background: "#22c55e" }} />
              <strong>Online</strong>
            </div>
          </div>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "160px", padding: "12px 16px" }}>
            <div className="hint" style={{ marginBottom: "4px" }}>MQTT Broker</div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span style={{ display: "inline-block", width: "8px", height: "8px", borderRadius: "50%", background: mqtt_connected ? "#22c55e" : "#ef4444" }} />
              <strong>{mqtt_connected ? "Connected" : "Disconnected"}</strong>
            </div>
            {mqtt_last_message_at ? <div className="hint" style={{ marginTop: "2px" }}>Last msg: {relativeTime(mqtt_last_message_at)}</div> : null}
          </div>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "160px", padding: "12px 16px" }}>
            <div className="hint" style={{ marginBottom: "4px" }}>SSE Listeners</div>
            <strong style={{ fontSize: "1.25rem" }}>{sse_subscriber_count}</strong>
          </div>
          <div className="section-card" style={{ flex: "1 1 0", minWidth: "160px", padding: "12px 16px" }}>
            <div className="hint" style={{ marginBottom: "4px" }}>Active Sessions</div>
            <strong style={{ fontSize: "1.25rem" }}>{active_sessions.length}</strong>
          </div>
        </div>

        {/* Connected Devices table */}
        <div className="participant-table-wrap">
          <table className="participant-table">
            <thead>
              <tr>
                <th>Pilot</th>
                <th>Device ID</th>
                <th>Source</th>
                <th>Task</th>
                <th>Battery</th>
                <th>Positions</th>
                <th>Rate</th>
                <th>Last Fix</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody>
              {active_sessions.length ? (
                active_sessions.map((session) => {
                  const color = lastSeenColor(session.last_seen_at);
                  const borderColor = color === "green" ? "#22c55e" : color === "orange" ? "#f59e0b" : "#ef4444";
                  const rate = (session.positions_last_60s / 60).toFixed(1);
                  const sourceLabel = session.source === "app" ? "App (cellular)" : session.source === "mqtt_gateway" ? "Mesh (MQTT)" : session.source ?? "\u2014";
                  const lastFixColor = color === "green" ? "inherit" : color === "orange" ? "#f59e0b" : "#ef4444";
                  return (
                    <tr key={session.pilot_id} style={{ borderLeft: `3px solid ${borderColor}` }}>
                      <td><strong>{session.pilot_name}</strong></td>
                      <td>{session.device_id ?? "\u2014"}</td>
                      <td>{sourceLabel}</td>
                      <td>{session.task_name ?? "Free flight"}</td>
                      <td style={{ color: batteryColor(session.battery_level) }}>
                        {session.battery_level != null ? `${session.battery_level}%` : "\u2014"}
                      </td>
                      <td>{session.position_count.toLocaleString()}</td>
                      <td>{rate}/s</td>
                      <td style={{ color: lastFixColor }}>{relativeTime(session.last_seen_at)}</td>
                      <td>{"\u2014"}</td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={9} className="participant-table-empty">No active tracking sessions.</td>
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
