"use client";

import { useState } from "react";

import { SectionCard } from "../SectionCard";
import type { AdminUserRecord, SiteSettingsRecord, User } from "./types";

type AdminTab = "platform_users" | "site_settings";

export interface AdminSectionProps {
  user: User | null;
  adminUsers: AdminUserRecord[];
  setAdminUsers: (users: AdminUserRecord[] | ((current: AdminUserRecord[]) => AdminUserRecord[])) => void;
  adminFeedback: { type: "success" | "error"; text: string } | null;
  saveAdminUser: (userRecord: AdminUserRecord) => void;
  deleteAdminUser: (userRecord: AdminUserRecord) => void;
  siteSettings: SiteSettingsRecord;
  setSiteSettings: (settings: SiteSettingsRecord | ((current: SiteSettingsRecord) => SiteSettingsRecord)) => void;
  siteSettingsFeedback: { type: "success" | "error"; text: string } | null;
  saveSiteSettings: () => void;
}

export default function AdminSection(props: AdminSectionProps) {
  const {
    user,
    adminUsers,
    setAdminUsers,
    adminFeedback,
    saveAdminUser,
    deleteAdminUser,
    siteSettings,
    setSiteSettings,
    siteSettingsFeedback,
    saveSiteSettings,
  } = props;
  const [activeTab, setActiveTab] = useState<AdminTab>("platform_users");

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
      ) : (
        <SectionCard title="Site settings" description="These admin-only settings control how telemetry is smoothed on the Scores map.">
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
            </div>
            <p className="hint">Use 0 to disable smoothing. Allowed range is 0 to 30 seconds.</p>
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
