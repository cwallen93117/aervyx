"use client";

import { type FormEvent, useMemo, useState } from "react";
import { SectionCard } from "../SectionCard";
import { DEFAULT_PILOT_CLASS, HANDICAP_CLASSES, handicapClassLabel, type PilotClass } from "../../lib/handicap";
import type { EventRecord, PilotRecord } from "./types";

export type PilotEditForm = { first_name: string; last_name: string; email: string; nation: string; competition_number: string; civl_id: string };

export interface ParticipantCardsProps {
  selectedEventId: number | null;
  selectedEvent: EventRecord | null;
  pilots: PilotRecord[];
  sitePilots: PilotRecord[];
  availableDirectoryPilots: PilotRecord[];
  pilotForm: PilotEditForm;
  setPilotForm: (form: PilotEditForm) => void;
  canManagePlatform: boolean;
  isAdmin: boolean;
  assignExistingPilot: (pilotId: number | null) => void;
  createPilot: (event: FormEvent<HTMLFormElement>) => void;
  removePilot: (pilot: PilotRecord) => void;
  updatePilot: (pilotId: number, payload: PilotEditForm) => Promise<void>;
  updateEventPilotClass: (pilotId: number, pilotClass: PilotClass) => Promise<void>;
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
    isAdmin,
    assignExistingPilot,
    createPilot,
    removePilot,
    updatePilot,
    updateEventPilotClass,
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
  const [editingPilot, setEditingPilot] = useState<PilotRecord | null>(null);
  const [editForm, setEditForm] = useState<PilotEditForm>({ first_name: "", last_name: "", email: "", nation: "", competition_number: "", civl_id: "" });
  const [editSaving, setEditSaving] = useState(false);
  const assignedPilotIds = useMemo(() => new Set(pilots.map((pilot) => pilot.id)), [pilots]);
  const normalizedDirectorySearch = directorySearch.trim().toLowerCase();
  const pilotLoginLabel = (pilot: PilotRecord) => pilot.email || pilot.portal_username || "No login";
  const pilotLoginKind = (pilot: PilotRecord) => (pilot.email ? "Email login" : pilot.portal_username ? "Portal fallback" : "No login");
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
                      placeholder="Search by name, login, comp #, CIVL ID, nation, or * for all"
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
                                  {pilotLoginKind(pilot)}: {pilotLoginLabel(pilot)}
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
                    <span>Login email</span>
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
          <table className="participant-table participant-roster-table">
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
                <th>Class</th>
                <th>Login</th>
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
                    <td>
                      {canManagePlatform ? (
                        <select
                          aria-label={`Class for ${pilot.first_name} ${pilot.last_name}`}
                          value={pilot.pilot_class ?? DEFAULT_PILOT_CLASS}
                          onChange={(event) => void updateEventPilotClass(pilot.id, event.target.value as PilotClass)}
                        >
                          {HANDICAP_CLASSES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </select>
                      ) : (
                        handicapClassLabel(pilot.pilot_class)
                      )}
                    </td>
                    <td>
                      <span>{pilotLoginLabel(pilot)}</span>
                      {pilot.email || pilot.portal_username ? <span>{` - ${pilotLoginKind(pilot)}`}</span> : null}
                    </td>
                    {canManagePlatform ? (
                      <td className="participant-table-actions">
                        <div className="compact-slot-actions participant-row-actions">
                          <button
                            type="button"
                            className="ghost-button"
                            disabled={Boolean(pilot.is_claimed) && !isAdmin}
                            title={Boolean(pilot.is_claimed) && !isAdmin ? "Account claimed — contact admin to edit" : "Edit pilot"}
                            onClick={() => {
                              setEditingPilot(pilot);
                              setEditForm({
                                first_name: pilot.first_name ?? "",
                                last_name: pilot.last_name ?? "",
                                email: pilot.email ?? "",
                                nation: pilot.nation ?? "",
                                competition_number: pilot.competition_number ?? "",
                                civl_id: pilot.civl_id ?? "",
                              });
                            }}
                          >
                            {Boolean(pilot.is_claimed) && !isAdmin ? "🔒 Edit" : "Edit"}
                          </button>
                          <button type="button" className="ghost-button danger-button" onClick={() => setConfirmRemove([pilot])}>Remove</button>
                        </div>
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
        {editingPilot ? (
          <div className="confirm-overlay" onClick={() => { if (!editSaving) setEditingPilot(null); }}>
            <div className="confirm-dialog confirm-dialog-wide" onClick={(e) => e.stopPropagation()}>
              <strong>Edit {editingPilot.first_name} {editingPilot.last_name}</strong>
              <div className="participant-intake-grid participant-intake-grid--two">
                <label className="stack compact">
                  <span>First name</span>
                  <input value={editForm.first_name} onChange={(event) => setEditForm({ ...editForm, first_name: event.target.value })} />
                </label>
                <label className="stack compact">
                  <span>Last name</span>
                  <input value={editForm.last_name} onChange={(event) => setEditForm({ ...editForm, last_name: event.target.value })} />
                </label>
              </div>
              <div className="participant-intake-grid participant-intake-grid--two">
                <label className="stack compact">
                  <span>Login email</span>
                  <input type="email" value={editForm.email} onChange={(event) => setEditForm({ ...editForm, email: event.target.value })} />
                </label>
                <label className="stack compact">
                  <span>Nation</span>
                  <input value={editForm.nation} onChange={(event) => setEditForm({ ...editForm, nation: event.target.value })} />
                </label>
                <label className="stack compact">
                  <span>Competition #</span>
                  <input value={editForm.competition_number} onChange={(event) => setEditForm({ ...editForm, competition_number: event.target.value })} />
                </label>
                <label className="stack compact">
                  <span>CIVL ID</span>
                  <input value={editForm.civl_id} onChange={(event) => setEditForm({ ...editForm, civl_id: event.target.value })} />
                </label>
              </div>
              <div className="confirm-actions">
                <button type="button" className="ghost-button" disabled={editSaving} onClick={() => setEditingPilot(null)}>Cancel</button>
                <button
                  type="button"
                  disabled={editSaving}
                  onClick={async () => {
                    if (!editingPilot) return;
                    setEditSaving(true);
                    try {
                      await updatePilot(editingPilot.id, editForm);
                      setEditingPilot(null);
                    } catch (caught) {
                      setMessage(caught instanceof Error ? caught.message : "Could not update pilot.");
                    } finally {
                      setEditSaving(false);
                    }
                  }}
                >
                  {editSaving ? "Saving…" : "Save"}
                </button>
              </div>
            </div>
          </div>
        ) : null}
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
