"use client";

import type { FormEvent } from "react";
import { SectionCard } from "../SectionCard";
import type {
  AirspaceCategoryOption,
  AirspaceSourceRecord,
  EventFormState,
  EventRecord,
  EventTab,
  MapAirspaceRegion,
  PilotRecord,
  TurnpointRecord,
  TurnpointSourceRecord,
  TurnpointUploadResponse,
} from "./types";

const scoringFormulaOptions = [
  { value: "GAP2021", label: "GAP 2021" },
  { value: "GAP2020", label: "GAP 2020" },
  { value: "GAP2018", label: "GAP 2018" },
  { value: "GAP2016", label: "GAP 2016" },
  { value: "GAP2008", label: "GAP 2008" },
  { value: "OzGAP2005", label: "OzGAP 2005" },
  { value: "PWC2016", label: "PWC 2016" },
] as const;
const scoringAltitudeOptions = [
  { value: "GPS", label: "GPS altitude" },
  { value: "QNH", label: "QNH altitude" },
  { value: "pressure", label: "Pressure altitude" },
] as const;
const finalGlideDeceleratorOptions = [
  { value: "none", label: "None" },
  { value: "default", label: "Default decelerator" },
  { value: "stopped_task", label: "Stopped-task decelerator" },
] as const;
const eventTabItems = [
  { id: "details", label: "Event Details" },
  { id: "turnpoints", label: "Turnpoint Files" },
  { id: "airspace", label: "Airspace / Restricted Fields" },
  { id: "participants", label: "Participants" },
  { id: "scoring", label: "Scoring Parameters" },
] satisfies Array<{ id: EventTab; label: string }>;
const airspaceCategoryOptions = [
  { value: "B", label: "Class B" },
  { value: "C", label: "Class C" },
  { value: "D", label: "Class D" },
  { value: "P", label: "Prohibited" },
  { value: "Q", label: "Danger" },
  { value: "R", label: "Restricted" },
  { value: "TFR", label: "TFR" },
  { value: "OTHER", label: "Other / advisory" },
] satisfies Array<{ value: AirspaceCategoryOption; label: string }>;

export interface EventsSectionProps {
  events: EventRecord[];
  selectedEventId: number | null;
  selectedEvent: EventRecord | null;
  eventEditorId: number | null;
  eventTab: EventTab;
  setEventTab: (tab: EventTab) => void;
  eventForm: EventFormState;
  setEventForm: (form: EventFormState) => void;
  turnpoints: TurnpointRecord[];
  turnpointSources: TurnpointSourceRecord[];
  airspaces: MapAirspaceRegion[];
  airspaceSources: AirspaceSourceRecord[];
  visibleAirspaces: MapAirspaceRegion[];
  pilots: PilotRecord[];
  canManagePlatform: boolean;
  isAdmin: boolean;
  selectEvent: (event: EventRecord) => void;
  createEventDraft: () => void;
  duplicateSelectedEvent: () => void;
  deleteEvent: () => void;
  saveEvent: (event: FormEvent<HTMLFormElement>) => void;
  toggleTurnpointSource: (source: TurnpointSourceRecord, enabled: boolean) => void;
  deleteTurnpointSource: (source: TurnpointSourceRecord) => void;
  uploadAirspaceFile: (kind: "airspace" | "restricted_field", file: File) => void;
  deleteAirspaceSource: (source: AirspaceSourceRecord) => void;
  toggleAirspaceSource: (source: AirspaceSourceRecord, enabled: boolean) => void;
  toggleVisibleAirspaceClass: (category: AirspaceCategoryOption) => void;
  uploadFile: <T>(path: string, file: File) => Promise<T>;
  loadEvent: (activeToken: string, eventId: number) => Promise<void>;
  refreshPilotDirectory: (activeToken: string) => Promise<PilotRecord[]>;
  refreshEvents: (activeToken: string) => Promise<EventRecord[]>;
  token: string;
  setMessage: (msg: string) => void;
  setError: (msg: string) => void;
  renderParticipantCards: () => React.ReactNode;
}

export default function EventsSection(props: EventsSectionProps) {
  const {
    events,
    selectedEventId,
    selectedEvent,
    eventEditorId,
    eventTab,
    setEventTab,
    eventForm,
    setEventForm,
    turnpoints,
    turnpointSources,
    airspaceSources,
    visibleAirspaces,
    canManagePlatform,
    isAdmin,
    selectEvent,
    createEventDraft,
    duplicateSelectedEvent,
    deleteEvent,
    saveEvent,
    toggleTurnpointSource,
    deleteTurnpointSource,
    uploadAirspaceFile,
    deleteAirspaceSource,
    toggleAirspaceSource,
    toggleVisibleAirspaceClass,
    uploadFile,
    loadEvent,
    refreshPilotDirectory,
    refreshEvents,
    token,
    setMessage,
    setError,
    renderParticipantCards,
  } = props;

  return (
    <div className="section-stack">
      <SectionCard title="Event selection" description="Choose an event from the database or start a new one. Everything below follows the currently selected event.">
        <div className="event-selector-bar">
          <label className="stack compact event-selector-field">
            <span>Current event</span>
            <select value={selectedEventId ?? (events[0]?.id ?? "")} onChange={(event) => { const nextId = Number(event.target.value); const nextEvent = events.find((candidate) => candidate.id === nextId); if (nextEvent) void selectEvent(nextEvent); }}>
              {events.length === 0 ? <option value="">No events yet</option> : null}
              {events.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.location ? `${event.name} - ${event.location}` : event.name}
                </option>
              ))}
            </select>
          </label>
          {canManagePlatform ? (
            <button className="event-selector-link" type="button" onClick={() => void createEventDraft()}>Create a New Event</button>
          ) : null}
        </div>
        <div className="event-summary-strip">
          <div className="record-card compact-stat">
            <strong>{selectedEvent?.pilot_count ?? 0}</strong>
            <span>Pilots</span>
          </div>
          <div className="record-card compact-stat">
            <strong>{selectedEvent?.task_count ?? 0}</strong>
            <span>Tasks</span>
          </div>
          <div className="record-card compact-stat">
            <strong>{turnpoints.length}</strong>
            <span>Turnpoints</span>
          </div>
          <div className="record-card compact-stat">
            <strong>{selectedEvent ? `${selectedEvent.starts_on} to ${selectedEvent.ends_on}` : "--"}</strong>
            <span>Dates</span>
          </div>
        </div>
      </SectionCard>
      <div className="tab-row">
        {eventTabItems.map((tab) => (
          <button key={tab.id} type="button" className={eventTab === tab.id ? "tab-button active" : "tab-button"} onClick={() => setEventTab(tab.id)}>
            {tab.label}
          </button>
        ))}
      </div>
      <div className="event-workspace-grid event-three-up">
        {eventTab === "details" ? (
        <SectionCard title={eventEditorId ? "Event details" : "Create event"} description="Keep the active event compact and quick to edit.">
          <form className="stack form-block compact-event-form" onSubmit={saveEvent}>
            <label className="stack compact">
              <span>Event name</span>
              <input placeholder="Enter event name" value={eventForm.name} onChange={(event) => setEventForm({ ...eventForm, name: event.target.value })} />
            </label>
            <label className="stack compact">
              <span>Location</span>
              <input placeholder="Enter location" value={eventForm.location} onChange={(event) => setEventForm({ ...eventForm, location: event.target.value })} />
            </label>
            <div className="inline-grid">
              <label className="stack compact">
                <span>Starts on</span>
                <input type="date" value={eventForm.starts_on} onChange={(event) => setEventForm({ ...eventForm, starts_on: event.target.value })} />
              </label>
              <label className="stack compact">
                <span>Ends on</span>
                <input type="date" value={eventForm.ends_on} onChange={(event) => setEventForm({ ...eventForm, ends_on: event.target.value })} />
              </label>
            </div>
            <label className="stack compact">
              <span>Timezone</span>
              <input placeholder="Enter timezone" value={eventForm.timezone} onChange={(event) => setEventForm({ ...eventForm, timezone: event.target.value })} />
            </label>
            {canManagePlatform ? (
              <div className="button-row">
                <button type="submit">{eventEditorId ? "Save event" : "Create event"}</button>
                {eventEditorId ? <button type="button" className="ghost-button" onClick={() => void duplicateSelectedEvent()}>Duplicate event</button> : null}
                {isAdmin && eventEditorId ? <button type="button" className="ghost-button danger-button" onClick={() => void deleteEvent()}>Delete event</button> : null}
              </div>
            ) : null}
          </form>
        </SectionCard>
        ) : null}
        {eventTab === "scoring" ? (
        <SectionCard title="Scoring parameters" description="Event-level GAP defaults.">
          {eventEditorId ? (
            <form className="stack form-block compact-scoring-form" onSubmit={saveEvent}>
              <label className="stack compact">
                <span>Scoring formula</span>
                <select value={eventForm.scoring_formula} onChange={(event) => setEventForm({ ...eventForm, scoring_formula: event.target.value })}>
                  {scoringFormulaOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Nominal distance (km)</span>
                  <input type="number" value={eventForm.nominal_distance_km} onChange={(event) => setEventForm({ ...eventForm, nominal_distance_km: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <span>Nominal time (hours)</span>
                  <input type="number" step="0.1" value={eventForm.nominal_time_hours} onChange={(event) => setEventForm({ ...eventForm, nominal_time_hours: Number(event.target.value) })} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Nominal launch</span>
                  <input type="number" step="0.01" value={eventForm.nominal_launch} onChange={(event) => setEventForm({ ...eventForm, nominal_launch: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <span>Minimum distance (km)</span>
                  <input type="number" value={eventForm.minimum_distance_km} onChange={(event) => setEventForm({ ...eventForm, minimum_distance_km: Number(event.target.value) })} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Nominal goal (%)</span>
                  <input type="number" step="0.01" value={eventForm.nominal_goal_percent} onChange={(event) => setEventForm({ ...eventForm, nominal_goal_percent: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <span>Score-back time (minutes)</span>
                  <input type="number" value={eventForm.score_back_time_minutes} onChange={(event) => setEventForm({ ...eventForm, score_back_time_minutes: Number(event.target.value) })} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Goal / SS penalty</span>
                  <input type="number" step="0.1" value={eventForm.goal_ss_penalty} onChange={(event) => setEventForm({ ...eventForm, goal_ss_penalty: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <span>Stopped-task glide bonus</span>
                  <input type="number" step="0.1" value={eventForm.stopped_glide_bonus} onChange={(event) => setEventForm({ ...eventForm, stopped_glide_bonus: Number(event.target.value) })} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Jump-the-gun factor</span>
                  <input type="number" step="0.1" value={eventForm.jump_the_gun_factor} onChange={(event) => setEventForm({ ...eventForm, jump_the_gun_factor: Number(event.target.value) })} />
                </label>
                <label className="stack compact">
                  <span>Jump-the-gun max (seconds)</span>
                  <input type="number" value={eventForm.jump_the_gun_max_seconds} onChange={(event) => setEventForm({ ...eventForm, jump_the_gun_max_seconds: Number(event.target.value) })} />
                </label>
              </div>
              <div className="three-up compact-checkbox-grid">
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_distance_points} onChange={(event) => setEventForm({ ...eventForm, use_distance_points: event.target.checked })} />
                  <span>Distance points</span>
                </label>
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_time_points} onChange={(event) => setEventForm({ ...eventForm, use_time_points: event.target.checked })} />
                  <span>Time points</span>
                </label>
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_leading_points} onChange={(event) => setEventForm({ ...eventForm, use_leading_points: event.target.checked })} />
                  <span>Leading points</span>
                </label>
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_arrival_position_points} onChange={(event) => setEventForm({ ...eventForm, use_arrival_position_points: event.target.checked })} />
                  <span>Arrival position points</span>
                </label>
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_arrival_time_points} onChange={(event) => setEventForm({ ...eventForm, use_arrival_time_points: event.target.checked })} />
                  <span>Arrival time points</span>
                </label>
                <label className="record-card checkbox-card">
                  <input type="checkbox" checked={eventForm.use_departure_points} onChange={(event) => setEventForm({ ...eventForm, use_departure_points: event.target.checked })} />
                  <span>Departure points</span>
                </label>
              </div>
              <p className="hint">The FS scoring sheet also shows computed outputs like day validity and available points. Only the editable AirScore formula settings are exposed here.</p>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>Day quality override</span>
                    <input type="number" step="0.01" value={eventForm.day_quality_override} onChange={(event) => setEventForm({ ...eventForm, day_quality_override: Number(event.target.value) })} />
                  </label>
                  <label className="stack compact">
                    <span>Time points if not in goal</span>
                    <input type="number" step="0.01" value={eventForm.time_points_if_not_in_goal} onChange={(event) => setEventForm({ ...eventForm, time_points_if_not_in_goal: Number(event.target.value) })} />
                  </label>
                </div>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>Min time span for valid task (minutes)</span>
                    <input type="number" value={eventForm.min_time_span_for_valid_task_minutes} onChange={(event) => setEventForm({ ...eventForm, min_time_span_for_valid_task_minutes: Number(event.target.value) })} />
                  </label>
                  <label className="stack compact">
                    <span>Leading weight factor</span>
                    <input type="number" step="0.01" value={eventForm.leading_weight_factor} onChange={(event) => setEventForm({ ...eventForm, leading_weight_factor: Number(event.target.value) })} />
                  </label>
                </div>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>Turnpoint radius tolerance</span>
                    <input type="number" step="0.0001" value={eventForm.turnpoint_radius_tolerance} onChange={(event) => setEventForm({ ...eventForm, turnpoint_radius_tolerance: Number(event.target.value) })} />
                  </label>
                  <label className="stack compact">
                    <span>Turnpoint min absolute tolerance (m)</span>
                    <input type="number" step="0.1" value={eventForm.turnpoint_radius_minimum_absolute_tolerance_m} onChange={(event) => setEventForm({ ...eventForm, turnpoint_radius_minimum_absolute_tolerance_m: Number(event.target.value) })} />
                  </label>
                </div>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>Task results decimals</span>
                    <input type="number" min={0} max={6} value={eventForm.number_of_decimals_task_results} onChange={(event) => setEventForm({ ...eventForm, number_of_decimals_task_results: Number(event.target.value) })} />
                  </label>
                  <label className="stack compact">
                    <span>Competition results decimals</span>
                    <input type="number" min={0} max={6} value={eventForm.number_of_decimals_competition_results} onChange={(event) => setEventForm({ ...eventForm, number_of_decimals_competition_results: Number(event.target.value) })} />
                  </label>
                </div>
                <div className="inline-grid">
                  <label className="stack compact">
                    <span>Scoring altitude</span>
                    <select value={eventForm.scoring_altitude} onChange={(event) => setEventForm({ ...eventForm, scoring_altitude: event.target.value })}>
                      {scoringAltitudeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <label className="stack compact">
                    <span>Final glide decelerator</span>
                    <select value={eventForm.final_glide_decelerator} onChange={(event) => setEventForm({ ...eventForm, final_glide_decelerator: event.target.value })}>
                      {finalGlideDeceleratorOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                </div>
                <label className="stack compact">
                  <span>No final glide decelerator reason</span>
                  <input type="text" value={eventForm.no_final_glide_decelerator_reason} onChange={(event) => setEventForm({ ...eventForm, no_final_glide_decelerator_reason: event.target.value })} placeholder="Optional override note" />
                </label>
                <div className="three-up compact-checkbox-grid">
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_1000_points_for_max_day_quality} onChange={(event) => setEventForm({ ...eventForm, use_1000_points_for_max_day_quality: event.target.checked })} />
                    <span>Use 1000 points for max day quality</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.normalize_1000_before_day_quality} onChange={(event) => setEventForm({ ...eventForm, normalize_1000_before_day_quality: event.target.checked })} />
                    <span>Normalize 1000 before day quality</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_difficulty_for_distance_points} onChange={(event) => setEventForm({ ...eventForm, use_difficulty_for_distance_points: event.target.checked })} />
                    <span>Use difficulty for distance points</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_distance_squared_for_lc} onChange={(event) => setEventForm({ ...eventForm, use_distance_squared_for_lc: event.target.checked })} />
                    <span>Use distance squared for LC</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_semi_circle_control_zone_for_goal_line} onChange={(event) => setEventForm({ ...eventForm, use_semi_circle_control_zone_for_goal_line: event.target.checked })} />
                    <span>Use semi-circle goal line control zone</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_proportional_leading_weight_if_nobody_in_goal} onChange={(event) => setEventForm({ ...eventForm, use_proportional_leading_weight_if_nobody_in_goal: event.target.checked })} />
                    <span>Proportional leading weight if nobody in goal</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.redistribute_removed_time_points_as_distance_points} onChange={(event) => setEventForm({ ...eventForm, redistribute_removed_time_points_as_distance_points: event.target.checked })} />
                    <span>Redistribute removed time points as distance points</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_best_score_for_ftv_validity} onChange={(event) => setEventForm({ ...eventForm, use_best_score_for_ftv_validity: event.target.checked })} />
                    <span>Use best score for FTV validity</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_constant_leading_weight} onChange={(event) => setEventForm({ ...eventForm, use_constant_leading_weight: event.target.checked })} />
                    <span>Use constant leading weight</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_pwca2019_for_lc} onChange={(event) => setEventForm({ ...eventForm, use_pwca2019_for_lc: event.target.checked })} />
                    <span>Use PWCA 2019 for LC</span>
                  </label>
                  <label className="record-card checkbox-card">
                    <input type="checkbox" checked={eventForm.use_flat_decline_of_timepoints} onChange={(event) => setEventForm({ ...eventForm, use_flat_decline_of_timepoints: event.target.checked })} />
                    <span>Use flat decline of time points</span>
                  </label>
                </div>
              <label className="stack compact">
                <span>Penalty rules JSON</span>
                <textarea value={eventForm.penalties_text} onChange={(event) => setEventForm({ ...eventForm, penalties_text: event.target.value })} rows={3} placeholder='{"jump_the_gun": 0, "airspace": 0}' />
              </label>
              {canManagePlatform ? <button type="submit">Save scoring parameters</button> : null}
            </form>
          ) : (
            <p className="hint">Create or select an event to define its scoring defaults.</p>
          )}
        </SectionCard>
        ) : null}
        {eventTab === "turnpoints" ? (
        <SectionCard title="Turnpoint files" description="Upload as many waypoint files as you need for the event, then control which ones are visible on the map.">
          {eventEditorId ? (
            <div className="stack form-block">
              {canManagePlatform ? (
                <div className="participant-intake-row">
                  <div className="stack compact">
                    <span>Upload turnpoint file</span>
                    <p className="hint">CSV, GeoJSON, or GPX. Each upload is stored separately so you can mix multiple waypoint datasets on the same event.</p>
                  </div>
                  <label className="file-input">
                    Upload turnpoints
                    <input
                      type="file"
                      accept=".csv,.geojson,.json,.gpx"
                      onChange={async (event) => {
                        const file = event.target.files?.[0];
                        if (!file || !selectedEventId) return;
                        try {
                          setError("");
                          const response = await uploadFile<TurnpointUploadResponse>(`/api/events/${selectedEventId}/turnpoints/upload`, file);
                          setMessage(`Stored ${response.imported_count} turnpoints from ${file.name}.`);
                          await loadEvent(token, selectedEventId);
                          await refreshEvents(token);
                        } catch (caught) {
                          setError(caught instanceof Error ? caught.message : `Failed to import ${file.name}.`);
                        } finally {
                          event.currentTarget.value = "";
                        }
                      }}
                    />
                  </label>
                </div>
              ) : null}
              <div className="participant-table-wrap">
                <table className="participant-table">
                  <thead>
                    <tr>
                      <th>File name</th>
                      <th>Format</th>
                      <th>Turnpoints</th>
                      <th>Visible</th>
                      <th>Uploaded</th>
                      {canManagePlatform ? <th className="participant-table-actions">Actions</th> : null}
                    </tr>
                  </thead>
                  <tbody>
                    {turnpointSources.length ? (
                      turnpointSources.map((source) => (
                        <tr key={source.id}>
                          <td><strong>{source.filename}</strong></td>
                          <td>{source.file_format.toUpperCase()}</td>
                          <td>{source.turnpoint_count}</td>
                          <td>
                            <label className="task-advanced-toggle">
                              <input
                                type="checkbox"
                                checked={source.enabled}
                                disabled={!canManagePlatform}
                                onChange={(event) => void toggleTurnpointSource(source, event.target.checked)}
                              />
                              <span>{source.enabled ? "Visible" : "Hidden"}</span>
                            </label>
                          </td>
                          <td>{new Date(source.uploaded_at).toLocaleString()}</td>
                          {canManagePlatform ? (
                            <td className="participant-table-actions">
                              <button type="button" className="ghost-button danger-button" onClick={() => void deleteTurnpointSource(source)}>Delete</button>
                            </td>
                          ) : null}
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={canManagePlatform ? 6 : 5} className="participant-table-empty">No turnpoint files uploaded for this event yet.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="hint">Create or select an event before uploading turnpoint files.</p>
          )}
        </SectionCard>
        ) : null}
      </div>
      {eventTab === "airspace" ? (
        <div className="section-grid two-column">
          <SectionCard title="Overlay settings" description="Choose which airspace classes should appear on the task map for this event.">
            {eventEditorId ? (
              <form className="stack form-block" onSubmit={saveEvent}>
                <div className="three-up compact-checkbox-grid">
                  {airspaceCategoryOptions.map((option) => (
                    <label key={option.value} className="record-card checkbox-card">
                      <input
                        type="checkbox"
                        checked={eventForm.visible_airspace_classes_json.includes(option.value)}
                        onChange={() => toggleVisibleAirspaceClass(option.value)}
                      />
                      <span>{option.label}</span>
                    </label>
                  ))}
                  <label className="record-card checkbox-card">
                    <input
                      type="checkbox"
                      checked={eventForm.show_restricted_fields}
                      onChange={(event) => setEventForm({ ...eventForm, show_restricted_fields: event.target.checked })}
                    />
                    <span>Restricted fields</span>
                  </label>
                </div>
                <div className="record-card">
                  <strong>{visibleAirspaces.length} visible overlays</strong>
                  <span>{selectedEvent?.airspace_count ?? 0} airspace regions and {selectedEvent?.restricted_field_count ?? 0} restricted fields stored for this event.</span>
                </div>
                {canManagePlatform ? <button type="submit">Save overlay settings</button> : null}
              </form>
            ) : (
              <p className="hint">Create or select an event to configure airspace overlays.</p>
            )}
          </SectionCard>
          <SectionCard title="Upload datasets" description="Use OpenAir for airspace and restricted field polygons. GeoJSON is also accepted for general airspace overlays.">
            <div className="stack form-block">
              {canManagePlatform ? (
                <>
                  <div className="record-card">
                    <strong>Competition airspace</strong>
                    <span>Upload OpenAir or GeoJSON around the selected event.</span>
                    <label className="file-input">
                      Upload airspace
                      <input
                        type="file"
                        accept=".txt,.openair,.air,.geojson,.json"
                        onChange={async (event) => {
                          const file = event.target.files?.[0];
                          if (!file) return;
                          try {
                            setError("");
                            await uploadAirspaceFile("airspace", file);
                          } catch (caught) {
                            setError(caught instanceof Error ? caught.message : `Failed to import ${file.name}.`);
                          } finally {
                            event.currentTarget.value = "";
                          }
                        }}
                      />
                    </label>
                  </div>
                  <div className="record-card">
                    <strong>Restricted landing fields</strong>
                    <span>Upload OpenAir polygons for do-not-land or field exclusion zones.</span>
                    <label className="file-input">
                      Upload restricted fields
                      <input
                        type="file"
                        accept=".txt,.openair,.air"
                        onChange={async (event) => {
                          const file = event.target.files?.[0];
                          if (!file) return;
                          try {
                            setError("");
                            await uploadAirspaceFile("restricted_field", file);
                          } catch (caught) {
                            setError(caught instanceof Error ? caught.message : `Failed to import ${file.name}.`);
                          } finally {
                            event.currentTarget.value = "";
                          }
                        }}
                      />
                    </label>
                  </div>
                </>
              ) : (
                <p className="hint">Only organizers and admins can upload airspace files. Pilots still see the saved overlays on the task map.</p>
              )}
            </div>
          </SectionCard>
          <SectionCard title="Stored airspace files" description="Uploaded overlays attached to this event.">
            <div className="stack form-block">
              {airspaceSources.filter((source) => source.kind === "airspace").length ? (
                airspaceSources.filter((source) => source.kind === "airspace").map((source) => (
                  <div key={source.id} className="record-card roster-row">
                    <div>
                      <strong>{source.filename}</strong>
                      <span>{source.region_count} regions - {source.file_format} - uploaded {new Date(source.uploaded_at).toLocaleString()}</span>
                    </div>
                    <div className="compact-slot-actions">
                      <label className="task-advanced-toggle">
                        <input
                          type="checkbox"
                          checked={source.enabled ?? true}
                          disabled={!canManagePlatform}
                          onChange={(event) => void toggleAirspaceSource(source, event.target.checked)}
                        />
                        <span>{source.enabled ?? true ? "Visible" : "Hidden"}</span>
                      </label>
                      {canManagePlatform ? <button type="button" className="ghost-button danger-button" onClick={() => void deleteAirspaceSource(source)}>Delete</button> : null}
                    </div>
                  </div>
                ))
              ) : (
                <p className="hint">No airspace overlays uploaded yet.</p>
              )}
            </div>
          </SectionCard>
          <SectionCard title="Stored restricted fields" description="Do-not-land and restricted field polygons for this event.">
            <div className="stack form-block">
              {airspaceSources.filter((source) => source.kind === "restricted_field").length ? (
                airspaceSources.filter((source) => source.kind === "restricted_field").map((source) => (
                  <div key={source.id} className="record-card roster-row">
                    <div>
                      <strong>{source.filename}</strong>
                      <span>{source.region_count} fields - {source.file_format} - uploaded {new Date(source.uploaded_at).toLocaleString()}</span>
                    </div>
                    <div className="compact-slot-actions">
                      <label className="task-advanced-toggle">
                        <input
                          type="checkbox"
                          checked={source.enabled ?? true}
                          disabled={!canManagePlatform}
                          onChange={(event) => void toggleAirspaceSource(source, event.target.checked)}
                        />
                        <span>{source.enabled ?? true ? "Visible" : "Hidden"}</span>
                      </label>
                      {canManagePlatform ? <button type="button" className="ghost-button danger-button" onClick={() => void deleteAirspaceSource(source)}>Delete</button> : null}
                    </div>
                  </div>
                ))
              ) : (
                <p className="hint">No restricted field files uploaded yet.</p>
              )}
            </div>
          </SectionCard>
        </div>
      ) : null}
      {eventTab === "participants" ? renderParticipantCards() : null}
    </div>
  );
}
