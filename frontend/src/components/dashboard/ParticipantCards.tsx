"use client";

import { type FormEvent, useMemo, useState } from "react";
import { SectionCard } from "../SectionCard";
import type { EventRecord, PilotRecord } from "./types";

export interface ParticipantCardsProps {
  selectedEventId: number | null;
  selectedEvent: EventRecord | null;
  pilots: PilotRecord[];
  sitePilots: PilotRecord[];
  availableDirectoryPilots: PilotRecord[];
  pilotForm: { first_name: string; last_name: string; email: string; nation: string; competition_number: string; civl_id: string };
  setPilotForm: (form: { first_name: string; last_name: string; email: string; nation: string; competition_number: string; civl_id: string }) => void;
  canManagePlatform: boolean;
  assignExistingPilot: (pilotId: number | null) => void;
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
    sitePilots,
    availableDirectoryPilots,
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
  const [directorySearch, setDirectorySearch] = useState("");
  const [selectedPilotIds, setSelectedPilotIds] = useState<Set<number>>(new Set());
  const [confirmRemove, setConfirmRemove] = useState<PilotRecord[] | null>(null);
  const assignedPilotIds = useMemo(() => new Set(pilots.map((pilot) => pilot.id)), [pilots]);
  const normalizedDirectorySearch = directorySearch.trim().toLowerCase();
  const searchableDirectoryPilots = useMemo(() => {
    if (!sitePilots.length) return availableDirectoryPilots;
    return sitePilots;
  }, [availableDirectoryPilots, sitePilots]);
  const filteredDirectoryPilots = useMemo(() => {
    if (!normalizedDirectorySearch) return searchableDirectoryPilots;
    if (normalizedDirectorySearch.includes("*")) return searchableDirectoryPilots;
    return searchableDirectoryPilots.filter((pilot) => {
      const haystack = [
        pilot.first_name,
        pilot.last_name,
        pilot.email ?? "",
        pilot.portal_username ?? "",
        pilot.competition_number ?? "",
        pilot.civl_id ?? "",
        pilot.nation ?? "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(normalizedDirectorySearch);
    });
  }, [normalizedDirectorySearch, searchableDirectoryPilots]);

  if (!selectedEventId) {
    return (
      <SectionCard title="Participants" description="Create or select an event first.">
        <p className="hint">An event must be selected before participants can be managed.</p>
      </SectionCard>
    );
  }
  return (
    <div className="participant-workspace">
      <SectionCard title="Participant intake">
        {canManagePlatform ? (
          <div className="participant-intake-stack">
            <div className="participant-intake-split">
              <div className="record-card stack compact participant-directory-card">
                <strong>Add existing person</strong>
                <span>Select from the global people directory, including pilots who created their own accounts.</span>
                <div className="task-search-panel">
                  <label className="stack compact">
                    <span>Search registered users</span>
                    <input
                      type="search"
                      placeholder="Search by name, email, username, comp #, CIVL ID, nation, or * for all"
                      value={directorySearch}
                      onChange={(event) => setDirectorySearch(event.target.value)}
                    />
                  </label>
                  {directorySearch.trim() ? (
                    filteredDirectoryPilots.length ? (
                      <div className="task-search-results">
                        {filteredDirectoryPilots.map((pilot) => {
                          const alreadyAssigned = assignedPilotIds.has(pilot.id);
                          return (
                            <div key={pilot.id} className="task-search-row participant-search-row">
                              <div>
                                <strong>{pilot.first_name} {pilot.last_name}</strong>
                                <span>
                                  {pilot.portal_username ? `@${pilot.portal_username}` : "No portal username"}
                                  {pilot.email ? ` - ${pilot.email}` : ""}
                                  {pilot.competition_number ? ` - #${pilot.competition_number}` : ""}
                                  {pilot.civl_id ? ` - CIVL ${pilot.civl_id}` : ""}
                                  {pilot.nation ? ` - ${pilot.nation}` : ""}
                                  {alreadyAssigned ? " - already in event" : ""}
                                </span>
                              </div>
                              <button type="button" className="ghost-button" onClick={() => void assignExistingPilot(pilot.id)} disabled={alreadyAssigned}>
                                {alreadyAssigned ? "Added" : "Add"}
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="hint">No registered site users match that search.</p>
                    )
                  ) : null}
                </div>
              </div>
              <form className="record-card stack compact participant-intake-form participant-intake-form-card" onSubmit={createPilot}>
                <strong>Create new pilot</strong>
                <span>Add a new pilot profile directly to the event and site directory.</span>
                <div className="participant-intake-grid participant-intake-grid--two">
                  <label className="stack compact">
                    <span>First name</span>
                    <input value={pilotForm.first_name} onChange={(event) => setPilotForm({ ...pilotForm, first_name: event.target.value })} placeholder="First name" />
                  </label>
                  <label className="stack compact">
                    <span>Last name</span>
                    <input value={pilotForm.last_name} onChange={(event) => setPilotForm({ ...pilotForm, last_name: event.target.value })} placeholder="Last name" />
                  </label>
                </div>
                <div className="participant-intake-grid participant-intake-grid--three">
                  <label className="stack compact">
                    <span>Email</span>
                    <input type="email" value={pilotForm.email} onChange={(event) => setPilotForm({ ...pilotForm, email: event.target.value })} placeholder="pilot@example.com" />
                  </label>
                  <label className="stack compact">
                    <span>Nation</span>
                    <input value={pilotForm.nation} onChange={(event) => setPilotForm({ ...pilotForm, nation: event.target.value })} placeholder="Nation" />
                  </label>
                  <label className="stack compact">
                    <span>Competition #</span>
                    <input value={pilotForm.competition_number} onChange={(event) => setPilotForm({ ...pilotForm, competition_number: event.target.value })} placeholder="Competition #" />
                  </label>
                  <label className="stack compact">
                    <span>CIVL ID</span>
                    <input value={pilotForm.civl_id} onChange={(event) => setPilotForm({ ...pilotForm, civl_id: event.target.value })} placeholder="CIVL ID" />
                  </label>
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
          </div>
        ) : (
          <p className="hint">Pilot management is available to organizers and admins. Pilots can still review the roster below.</p>
        )}
      </SectionCard>
      <SectionCard title="Current participants">
        {canManagePlatform && selectedPilotIds.size > 0 ? (
          <div className="participant-bulk-bar">
            <span>{selectedPilotIds.size} selected</span>
            <button
              type="button"
              className="ghost-button danger-button"
              onClick={() => {
                const selected = pilots.filter((p) => selectedPilotIds.has(p.id));
                if (selected.length) setConfirmRemove(selected);
              }}
            >
              Remove selected
            </button>
          </div>
        ) : null}
        <div className="participant-table-wrap">
          <table className="participant-table">
            <thead>
              <tr>
                {canManagePlatform ? (
                  <th className="participant-table-check">
                    <input
                      type="checkbox"
                      checked={pilots.length > 0 && selectedPilotIds.size === pilots.length}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedPilotIds(new Set(pilots.map((p) => p.id)));
                        } else {
                          setSelectedPilotIds(new Set());
                        }
                      }}
                    />
                  </th>
                ) : null}
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
                  <tr key={pilot.id} className={selectedPilotIds.has(pilot.id) ? "participant-row-selected" : ""}>
                    {canManagePlatform ? (
                      <td className="participant-table-check">
                        <input
                          type="checkbox"
                          checked={selectedPilotIds.has(pilot.id)}
                          onChange={(e) => {
                            const next = new Set(selectedPilotIds);
                            if (e.target.checked) next.add(pilot.id); else next.delete(pilot.id);
                            setSelectedPilotIds(next);
                          }}
                        />
                      </td>
                    ) : null}
                    <td>
                      <strong>{pilot.first_name} {pilot.last_name}</strong>
                    </td>
                    <td>{pilot.competition_number ?? "No comp #"}</td>
                    <td>{pilot.email ?? "No email"}</td>
                    <td>{pilot.portal_username ?? "No portal user"}</td>
                    {canManagePlatform ? (
                      <td className="participant-table-actions">
                        <button type="button" className="ghost-button danger-button" onClick={() => setConfirmRemove([pilot])}>Remove</button>
                      </td>
                    ) : null}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={canManagePlatform ? 6 : 4} className="participant-table-empty">No participants assigned to this event yet.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {confirmRemove ? (
          <div className="confirm-overlay" onClick={() => setConfirmRemove(null)}>
            <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
              <strong>Remove {confirmRemove.length === 1 ? confirmRemove[0].first_name + " " + confirmRemove[0].last_name : `${confirmRemove.length} participants`}?</strong>
              <p>
                {confirmRemove.length === 1
                  ? "This will remove the pilot from the event. They can be re-added later."
                  : `This will remove ${confirmRemove.length} pilots from the event. They can be re-added later.`}
              </p>
              <div className="confirm-actions">
                <button type="button" className="ghost-button" onClick={() => setConfirmRemove(null)}>Cancel</button>
                <button
                  type="button"
                  className="ghost-button danger-button"
                  onClick={() => {
                    for (const pilot of confirmRemove) removePilot(pilot);
                    setSelectedPilotIds((prev) => {
                      const next = new Set(prev);
                      for (const pilot of confirmRemove) next.delete(pilot.id);
                      return next;
                    });
                    setConfirmRemove(null);
                  }}
                >
                  Remove
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </SectionCard>
    </div>
  );
}
