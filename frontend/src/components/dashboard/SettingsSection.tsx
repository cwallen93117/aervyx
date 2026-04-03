"use client";

import { useState, type FormEvent } from "react";
import BuddyGroupsManager from "./BuddyGroupsManager";
import type { AccountSettingsRecord } from "./types";

export interface SettingsSectionProps {
  token: string;
  settingsForm: AccountSettingsRecord;
  setSettingsForm: (form: AccountSettingsRecord | ((current: AccountSettingsRecord) => AccountSettingsRecord)) => void;
  settingsPasswordForm: { current_password: string; new_password: string; confirm_password: string };
  setSettingsPasswordForm: (form: { current_password: string; new_password: string; confirm_password: string } | ((current: { current_password: string; new_password: string; confirm_password: string }) => { current_password: string; new_password: string; confirm_password: string })) => void;
  showCurrentSettingsPassword: boolean;
  setShowCurrentSettingsPassword: (show: boolean | ((current: boolean) => boolean)) => void;
  settingsFeedback: {
    profile: { type: "success" | "error"; text: string } | null;
    password: { type: "success" | "error"; text: string } | null;
  };
  saveAccountSettings: (event: FormEvent<HTMLFormElement>) => void;
  savePasswordSettings: (event: FormEvent<HTMLFormElement>) => void;
}

type SettingsTab = "profile" | "units" | "password" | "buddies";

const TABS: { key: SettingsTab; label: string }[] = [
  { key: "profile", label: "Profile" },
  { key: "units", label: "Units" },
  { key: "password", label: "Password" },
  { key: "buddies", label: "Pilot Buddies" },
];

export default function SettingsSection(props: SettingsSectionProps) {
  const {
    token,
    settingsForm,
    setSettingsForm,
    settingsPasswordForm,
    setSettingsPasswordForm,
    showCurrentSettingsPassword,
    setShowCurrentSettingsPassword,
    settingsFeedback,
    saveAccountSettings,
    savePasswordSettings,
  } = props;

  const [activeTab, setActiveTab] = useState<SettingsTab>("profile");

  return (
    <div className="section-stack">
      <div className="tab-row">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            className={`tab-button${activeTab === tab.key ? " active" : ""}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "profile" && (
        <div className="settings-tab-panel">
          <div className="settings-summary-row">
            <label className="settings-type-control">
              <span>Profile type</span>
              <select
                value={settingsForm.profile_type}
                onChange={(event) => setSettingsForm((current) => ({ ...current, profile_type: event.target.value as "pilot" | "driver" }))}
              >
                <option value="pilot">Pilot</option>
                <option value="driver">Driver</option>
              </select>
            </label>
          </div>
          <form className="stack form-block" onSubmit={saveAccountSettings}>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Username / email</span>
                <input
                  type="email"
                  value={settingsForm.username ?? ""}
                  onChange={(event) =>
                    setSettingsForm((current) => ({
                      ...current,
                      username: event.target.value,
                      email: event.target.value,
                    }))
                  }
                  placeholder="pilot@example.com"
                  required
                />
              </label>
              <label className="stack compact">
                <span>Display name</span>
                <input value={settingsForm.full_name ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, full_name: event.target.value }))} required />
              </label>
            </div>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Nation</span>
                <input value={settingsForm.nation ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, nation: event.target.value.toUpperCase() }))} maxLength={3} />
              </label>
              <label className="stack compact">
                <span>Competition number</span>
                <input value={settingsForm.competition_number ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, competition_number: event.target.value }))} />
              </label>
            </div>
            <div className="inline-grid">
              <label className="stack compact">
                <span>First name</span>
                <input value={settingsForm.first_name ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, first_name: event.target.value }))} />
              </label>
              <label className="stack compact">
                <span>Last name</span>
                <input value={settingsForm.last_name ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, last_name: event.target.value }))} />
              </label>
            </div>
            <div className="inline-grid">
              <label className="stack compact">
                <span>CIVL ID</span>
                <input value={settingsForm.civl_id ?? ""} onChange={(event) => setSettingsForm((current) => ({ ...current, civl_id: event.target.value }))} />
              </label>
              <div />
            </div>
            <div className="button-row">
              <button type="submit">Save account settings</button>
            </div>
            {settingsFeedback.profile ? <div className={`status-chip ${settingsFeedback.profile.type}`}>{settingsFeedback.profile.text}</div> : null}
          </form>
        </div>
      )}

      {activeTab === "units" && (
        <div className="settings-tab-panel">
          <form className="stack form-block" onSubmit={saveAccountSettings}>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Altitude</span>
                <select
                  value={settingsForm.altitude_unit}
                  onChange={(event) => setSettingsForm((current) => ({ ...current, altitude_unit: event.target.value as "ft" | "m" }))}
                >
                  <option value="ft">Feet (ft)</option>
                  <option value="m">Meters (m)</option>
                </select>
              </label>
              <label className="stack compact">
                <span>Speed</span>
                <select
                  value={settingsForm.speed_unit}
                  onChange={(event) => setSettingsForm((current) => ({ ...current, speed_unit: event.target.value as "kph" | "mph" }))}
                >
                  <option value="kph">Kilometers per hour (kph)</option>
                  <option value="mph">Miles per hour (mph)</option>
                </select>
              </label>
            </div>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Distance</span>
                <select
                  value={settingsForm.distance_unit}
                  onChange={(event) => setSettingsForm((current) => ({ ...current, distance_unit: event.target.value as "km" | "mi" }))}
                >
                  <option value="km">Kilometers (km)</option>
                  <option value="mi">Miles (mi)</option>
                </select>
              </label>
              <label className="stack compact">
                <span>Vario</span>
                <select
                  value={settingsForm.vario_unit}
                  onChange={(event) => setSettingsForm((current) => ({ ...current, vario_unit: event.target.value as "fpm" | "ms" }))}
                >
                  <option value="fpm">Feet per minute (ft/min)</option>
                  <option value="ms">Meters per second (m/s)</option>
                </select>
              </label>
            </div>
            <div className="button-row">
              <button type="submit">Save unit preferences</button>
            </div>
            {settingsFeedback.profile ? <div className={`status-chip ${settingsFeedback.profile.type}`}>{settingsFeedback.profile.text}</div> : null}
          </form>
        </div>
      )}

      {activeTab === "password" && (
        <div className="settings-tab-panel">
          {!settingsForm.has_password && (
            <p className="settings-description">Your account was created via Google Sign-In and has no password yet. Set one here to enable mobile app login.</p>
          )}
          <form className="stack form-block" onSubmit={savePasswordSettings}>
            {settingsForm.has_password ? (
              <>
                <label className="stack compact">
                  <span>Current password</span>
                  <input
                    type={showCurrentSettingsPassword ? "text" : "password"}
                    value={settingsPasswordForm.current_password}
                    onChange={(event) => setSettingsPasswordForm((current) => ({ ...current, current_password: event.target.value }))}
                    autoComplete="current-password"
                    required
                  />
                </label>
                <div className="button-row">
                  <button type="button" className="ghost-button" onClick={() => setShowCurrentSettingsPassword((current: boolean) => !current)}>
                    {showCurrentSettingsPassword ? "Hide" : "Show"}
                  </button>
                </div>
              </>
            ) : null}
            <div className="inline-grid">
              <label className="stack compact">
                <span>New password</span>
                <input type="password" value={settingsPasswordForm.new_password} onChange={(event) => setSettingsPasswordForm((current) => ({ ...current, new_password: event.target.value }))} autoComplete="new-password" required />
              </label>
              <label className="stack compact">
                <span>Confirm new password</span>
                <input type="password" value={settingsPasswordForm.confirm_password} onChange={(event) => setSettingsPasswordForm((current) => ({ ...current, confirm_password: event.target.value }))} autoComplete="new-password" required />
              </label>
            </div>
            <div className="button-row">
              <button type="submit">{settingsForm.has_password ? "Update password" : "Set password"}</button>
            </div>
            {settingsFeedback.password ? <div className={`status-chip ${settingsFeedback.password.type}`}>{settingsFeedback.password.text}</div> : null}
          </form>
        </div>
      )}

      {activeTab === "buddies" && (
        <div className="settings-tab-panel">
          <BuddyGroupsManager token={token} />
        </div>
      )}
    </div>
  );
}
