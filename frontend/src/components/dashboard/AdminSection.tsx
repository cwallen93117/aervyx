"use client";

import { SectionCard } from "../SectionCard";
import type { AdminUserRecord, SiteSettingsRecord, User } from "./types";

export interface AdminSectionProps {
  user: User | null;
  adminUsers: AdminUserRecord[];
  setAdminUsers: (users: AdminUserRecord[] | ((current: AdminUserRecord[]) => AdminUserRecord[])) => void;
  adminFeedback: { type: "success" | "error"; text: string } | null;
  saveAdminUser: (userRecord: AdminUserRecord) => void;
  deleteAdminUser: (userRecord: AdminUserRecord) => void;
  siteSettings?: SiteSettingsRecord;
  setSiteSettings?: (settings: SiteSettingsRecord | ((current: SiteSettingsRecord) => SiteSettingsRecord)) => void;
  siteSettingsFeedback?: { type: "success" | "error"; text: string } | null;
  saveSiteSettings?: () => void;
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

  return (
    <div className="section-stack">
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
      {siteSettings && setSiteSettings && saveSiteSettings ? (
        <SectionCard title="Site settings" description="These admin-only settings control how telemetry is smoothed on the Scores map.">
        <div className="stack form-block">
          {siteSettingsFeedback ? <div className={`status-chip ${siteSettingsFeedback.type}`}>{siteSettingsFeedback.text}</div> : null}
          <div className="inline-grid">
            <label className="stack compact">
              <span>Vertical speed smoothing window (seconds)</span>
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
              <span>Altitude smoothing window (seconds)</span>
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
          <label className="stack compact">
            <span>Speed smoothing window (seconds)</span>
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
          <p className="hint">Use 0 to disable smoothing. Allowed range is 0 to 30 seconds.</p>
          <div className="button-row">
            <button type="button" onClick={() => void saveSiteSettings()}>
              Save site settings
            </button>
          </div>
        </div>
        </SectionCard>
      ) : null}
    </div>
  );
}
