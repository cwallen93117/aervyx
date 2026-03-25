"use client";

import type { FormEvent } from "react";
import { SectionCard } from "../SectionCard";
import type { EventRecord, PilotRecord } from "./types";

export interface ParticipantCardsProps {
  selectedEventId: number | null;
  selectedEvent: EventRecord | null;
  pilots: PilotRecord[];
  availableDirectoryPilots: PilotRecord[];
  selectedDirectoryPilotId: number | null;
  setSelectedDirectoryPilotId: (id: number | null) => void;
  pilotForm: { first_name: string; last_name: string; email: string; nation: string; competition_number: string; civl_id: string };
  setPilotForm: (form: { first_name: string; last_name: string; email: string; nation: string; competition_number: string; civl_id: string }) => void;
  canManagePlatform: boolean;
  assignExistingPilot: () => void;
  createPilot: (event: FormEvent<HTMLFormElement>) => void;
  removePilot: (pilot: PilotRecord) => void;
  uploadFile: <T>(path: string, file: File) => Promise<T>;
  loadEvent: (activeToken: string, eventId: number) => Promise<void>;
  refreshPilotDirectory: (activeToken: string) => Promise<PilotRecord[]>;
  refreshEvents: (activeToken: string) => Promise<EventRecord[]>;
  token: string;
  setMessage: (msg: string) => void;
}

export default function ParticipantCards(props: ParticipantCardsProps) {
  const {
    selectedEventId,
    selectedEvent,
    pilots,
    availableDirectoryPilots,
    selectedDirectoryPilotId,
    setSelectedDirectoryPilotId,
    pilotForm,
    setPilotForm,
    canManagePlatform,
    assignExistingPilot,
    createPilot,
    removePilot,
    uploadFile,
    loadEvent,
    refreshPilotDirectory,
    refreshEvents,
    token,
    setMessage,
  } = props;

  if (!selectedEventId) {
    return (
      <SectionCard title="Participants" description="Create or select an event first.">
        <p className="hint">An event must be selected before participants can be managed.</p>
      </SectionCard>
    );
  }
  return (
    <div className="participant-workspace">
      <SectionCard title="Participant intake" description="Add a pilot manually or import a roster CSV for the selected event.">
        {canManagePlatform ? (
          <div className="participant-intake-stack">
            <div className="record-card stack compact participant-directory-card">
              <strong>Add existing person</strong>
              <span>Select from the global people directory, including pilots who created their own accounts.</span>
              <div className="participant-intake-row">
                <select value={selectedDirectoryPilotId ?? ""} onChange={(event) => setSelectedDirectoryPilotId(event.target.value ? Number(event.target.value) : null)}>
                  <option value="">Select a person</option>
                  {availableDirectoryPilots.map((pilot) => (
                    <option key={pilot.id} value={pilot.id}>
                      {pilot.first_name} {pilot.last_name}{pilot.email ? ` - ${pilot.email}` : ""}{pilot.competition_number ? ` - #${pilot.competition_number}` : ""}
                    </option>
                  ))}
                </select>
                <button type="button" onClick={() => void assignExistingPilot()} disabled={!selectedDirectoryPilotId}>Add to event</button>
              </div>
            </div>
            <form className="stack form-block compact participant-intake-form" onSubmit={createPilot}>
              <div className="participant-intake-grid participant-intake-grid--two">
                <input placeholder="First name" value={pilotForm.first_name} onChange={(event) => setPilotForm({ ...pilotForm, first_name: event.target.value })} />
                <input placeholder="Last name" value={pilotForm.last_name} onChange={(event) => setPilotForm({ ...pilotForm, last_name: event.target.value })} />
              </div>
              <div className="participant-intake-grid participant-intake-grid--three">
                <input placeholder="Email" value={pilotForm.email} onChange={(event) => setPilotForm({ ...pilotForm, email: event.target.value })} />
                <input placeholder="Nation" value={pilotForm.nation} onChange={(event) => setPilotForm({ ...pilotForm, nation: event.target.value })} />
                <input placeholder="Competition #" value={pilotForm.competition_number} onChange={(event) => setPilotForm({ ...pilotForm, competition_number: event.target.value })} />
                <input placeholder="CIVL ID" value={pilotForm.civl_id} onChange={(event) => setPilotForm({ ...pilotForm, civl_id: event.target.value })} />
              </div>
              <div className="button-row participant-intake-actions">
                <button type="submit">Create new pilot</button>
                <label className="file-input">
                  Import CSV
                  <input
                    type="file"
                    accept=".csv"
                    onChange={async (event) => {
                      const file = event.target.files?.[0];
                      if (!file) return;
                      await uploadFile<unknown>(`/api/events/${selectedEventId}/pilots/import-csv`, file);
                      setMessage(`Imported pilots from ${file.name}.`);
                      await loadEvent(token, selectedEventId);
                      await refreshPilotDirectory(token);
                      await refreshEvents(token);
                      event.currentTarget.value = "";
                    }}
                  />
                </label>
              </div>
            </form>
          </div>
        ) : (
          <p className="hint">Pilot management is available to organizers and admins. Pilots can still review the roster below.</p>
        )}
      </SectionCard>
      <SectionCard title="Current participants" description={`${pilots.length} pilots assigned to ${selectedEvent?.name ?? "this event"}.`}>
        <div className="participant-table-wrap">
          <table className="participant-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Competition #</th>
                <th>Email</th>
                <th>Portal</th>
                {canManagePlatform ? <th className="participant-table-actions">Actions</th> : null}
              </tr>
            </thead>
            <tbody>
              {pilots.length ? (
                pilots.map((pilot) => (
                  <tr key={pilot.id}>
                    <td>
                      <strong>{pilot.first_name} {pilot.last_name}</strong>
                    </td>
                    <td>{pilot.competition_number ?? "No comp #"}</td>
                    <td>{pilot.email ?? "No email"}</td>
                    <td>{pilot.portal_username ?? "No portal user"}</td>
                    {canManagePlatform ? (
                      <td className="participant-table-actions">
                        <button type="button" className="ghost-button danger-button" onClick={() => removePilot(pilot)}>Remove</button>
                      </td>
                    ) : null}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={canManagePlatform ? 5 : 4} className="participant-table-empty">No participants assigned to this event yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
