"use client";

import { type ChangeEvent, type FormEvent, useMemo, useRef, useState } from "react";

import { TaskMap, type MapTelemetrySmoothing, type MapUnitPreferences } from "../TaskMap";
import { SectionCard } from "../SectionCard";
import type { LogbookFlightDetailRecord, LogbookFlightFormRecord, LogbookFlightSummaryRecord, TrackCollection, User } from "./types";

export interface LogbookSectionProps {
  user: User | null;
  flights: LogbookFlightSummaryRecord[];
  loading: boolean;
  feedback: { type: "success" | "error" | "pending"; text: string } | null;
  detailFlight: LogbookFlightDetailRecord | null;
  detailLoading: boolean;
  replayFlight: LogbookFlightSummaryRecord | null;
  replayTrack: TrackCollection | null;
  replayLoading: boolean;
  units: MapUnitPreferences;
  telemetrySmoothing: MapTelemetrySmoothing;
  createManualFlight: (form: LogbookFlightFormRecord) => Promise<void>;
  uploadFlightFile: (file: File) => Promise<void>;
  openFlightDetail: (flightId: number) => Promise<void>;
  closeFlightDetail: () => void;
  openFlightReplay: (flight: LogbookFlightSummaryRecord) => Promise<void>;
  closeFlightReplay: () => void;
  downloadFlight: (flightId: number) => Promise<void>;
}

function blankManualFlightForm(): LogbookFlightFormRecord {
  return {
    flight_date: new Date().toISOString().slice(0, 10),
    site_name: "",
    duration_seconds: "",
    highest_altitude_m: "",
    best_climb_mps: "",
    notes: "",
  };
}

function formatFlightDate(value: string) {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(new Date(parsed));
}

function formatDuration(seconds: number | null | undefined) {
  if (seconds == null || !Number.isFinite(seconds)) {
    return "--";
  }
  const totalSeconds = Math.max(0, Math.round(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return `${hours}:${String(minutes).padStart(2, "0")}`;
}

function formatAltitude(valueM: number | null | undefined, unit: MapUnitPreferences["altitude"]) {
  if (valueM == null || !Number.isFinite(valueM)) {
    return "--";
  }
  if (unit === "ft") {
    return `${Math.round(valueM * 3.28084).toLocaleString()} ft`;
  }
  return `${Math.round(valueM).toLocaleString()} m`;
}

function formatVario(valueMps: number | null | undefined, unit: MapUnitPreferences["vario"]) {
  if (valueMps == null || !Number.isFinite(valueMps)) {
    return "--";
  }
  if (unit === "fpm") {
    return `${Math.round(valueMps * 196.850394).toLocaleString()} fpm`;
  }
  return `${valueMps.toFixed(1)} m/s`;
}

function sourceLabel(kind: LogbookFlightSummaryRecord["source_kind"]) {
  switch (kind) {
    case "task_upload":
      return "Task upload";
    case "app_upload":
      return "App / IGC";
    case "manual":
      return "Manual";
    default:
      return kind.replace(/_/g, " ");
  }
}

export default function LogbookSection(props: LogbookSectionProps) {
  const {
    user,
    flights,
    loading,
    feedback,
    detailFlight,
    detailLoading,
    replayFlight,
    replayTrack,
    replayLoading,
    units,
    telemetrySmoothing,
    createManualFlight,
    uploadFlightFile,
    openFlightDetail,
    closeFlightDetail,
    openFlightReplay,
    closeFlightReplay,
    downloadFlight,
  } = props;

  const [manualForm, setManualForm] = useState<LogbookFlightFormRecord>(blankManualFlightForm());
  const [manualOpen, setManualOpen] = useState(false);
  const [manualSubmitting, setManualSubmitting] = useState(false);
  const uploadRef = useRef<HTMLInputElement | null>(null);
  const hasPilotProfile = Boolean(user?.pilot_id);

  async function submitManualFlight(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setManualSubmitting(true);
    try {
      await createManualFlight(manualForm);
      setManualForm(blankManualFlightForm());
      setManualOpen(false);
    } finally {
      setManualSubmitting(false);
    }
  }

  async function handleUploadSelection(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    await uploadFlightFile(file);
  }

  const replayTitle = useMemo(() => {
    if (!replayFlight) {
      return "Flight replay";
    }
    return `${formatFlightDate(replayFlight.flight_date)} - ${replayFlight.site_name || replayFlight.task_name || "Flight replay"}`;
  }, [replayFlight]);

  return (
    <div className="section-stack">
      <SectionCard
        title="Pilot logbook"
        description="Review every uploaded or manually recorded flight for the signed-in pilot."
        actions={
          hasPilotProfile ? (
            <div className="button-row compact">
              <input ref={uploadRef} type="file" accept=".igc" hidden onChange={handleUploadSelection} />
              <button type="button" className="ghost-button" onClick={() => uploadRef.current?.click()}>
                Upload IGC
              </button>
              <button type="button" onClick={() => setManualOpen(true)}>
                Add flight
              </button>
            </div>
          ) : null
        }
      >
        {!hasPilotProfile ? (
          <div className="stack form-block">
            <p className="hint">This account does not have a pilot profile yet, so there is no personal logbook to display.</p>
          </div>
        ) : (
          <div className="logbook-section-body">
            {feedback ? <div className={`status-chip ${feedback.type}`}>{feedback.text}</div> : null}
            <div className="results-table-wrap logbook-table-wrap">
              <table className="results-table logbook-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Site</th>
                    <th>Duration</th>
                    <th>Highest altitude</th>
                    <th>Best climb</th>
                    <th>Source</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={7} className="results-table-empty">Loading logbook flights...</td>
                    </tr>
                  ) : flights.length ? (
                    flights.map((flight) => (
                      <tr key={flight.id}>
                        <td>{formatFlightDate(flight.flight_date)}</td>
                        <td>
                          <strong>{flight.site_name || "—"}</strong>
                          {flight.task_name || flight.event_name ? (
                            <div className="hint">{[flight.task_name, flight.event_name].filter(Boolean).join(" - ")}</div>
                          ) : null}
                        </td>
                        <td>{formatDuration(flight.duration_seconds)}</td>
                        <td>{formatAltitude(flight.highest_altitude_m, units.altitude)}</td>
                        <td>{formatVario(flight.best_climb_mps, units.vario)}</td>
                        <td>
                          <span className="status-chip pending">{sourceLabel(flight.source_kind)}</span>
                        </td>
                        <td>
                          <div className="logbook-row-actions">
                            <button type="button" className="ghost-button" onClick={() => void openFlightDetail(flight.id)} disabled={!flight.has_statistics}>
                              Statistics
                            </button>
                            <button type="button" className="ghost-button" onClick={() => void openFlightReplay(flight)} disabled={!flight.can_replay}>
                              Replay
                            </button>
                            <button type="button" className="ghost-button" onClick={() => void downloadFlight(flight.id)} disabled={!flight.can_download}>
                              Download IGC
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} className="results-table-empty">No flights have been recorded yet.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </SectionCard>

      {manualOpen ? (
        <div className="logbook-modal-overlay active" role="presentation">
          <div className="logbook-modal">
            <div className="section-card-header">
              <div>
                <h3>Add manual flight</h3>
                <p className="hint">Create a logbook row without an IGC file. You can add replayable IGC flights with the upload button.</p>
              </div>
            </div>
            <form className="stack form-block" onSubmit={submitManualFlight}>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Date</span>
                  <input type="date" value={manualForm.flight_date} onChange={(event) => setManualForm((current) => ({ ...current, flight_date: event.target.value }))} required />
                </label>
                <label className="stack compact">
                  <span>Site</span>
                  <input value={manualForm.site_name} onChange={(event) => setManualForm((current) => ({ ...current, site_name: event.target.value }))} required />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Flight duration (seconds)</span>
                  <input type="number" min={0} value={manualForm.duration_seconds} onChange={(event) => setManualForm((current) => ({ ...current, duration_seconds: event.target.value }))} />
                </label>
                <label className="stack compact">
                  <span>Highest altitude (m)</span>
                  <input type="number" value={manualForm.highest_altitude_m} onChange={(event) => setManualForm((current) => ({ ...current, highest_altitude_m: event.target.value }))} />
                </label>
              </div>
              <div className="inline-grid">
                <label className="stack compact">
                  <span>Best climb (m/s)</span>
                  <input type="number" step="0.1" value={manualForm.best_climb_mps} onChange={(event) => setManualForm((current) => ({ ...current, best_climb_mps: event.target.value }))} />
                </label>
                <div />
              </div>
              <label className="stack compact">
                <span>Notes</span>
                <textarea rows={4} value={manualForm.notes} onChange={(event) => setManualForm((current) => ({ ...current, notes: event.target.value }))} />
              </label>
              <div className="button-row">
                <button type="button" className="ghost-button" onClick={() => setManualOpen(false)} disabled={manualSubmitting}>
                  Cancel
                </button>
                <button type="submit" disabled={manualSubmitting}>
                  {manualSubmitting ? "Saving..." : "Save flight"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {detailFlight || detailLoading ? (
        <div className="logbook-modal-overlay active" role="presentation">
          <div className="logbook-modal logbook-modal-wide">
            <div className="section-card-header">
              <div>
                <h3>{detailFlight ? `${formatFlightDate(detailFlight.flight_date)} - ${detailFlight.site_name || "Flight statistics"}` : "Loading statistics..."}</h3>
                <p className="hint">Derived flight metrics and summary details for this personal logbook entry.</p>
              </div>
              <div className="button-row compact">
                <button type="button" className="ghost-button" onClick={closeFlightDetail}>Close</button>
              </div>
            </div>
            {detailLoading || !detailFlight ? (
              <div className="stack form-block">
                <p className="hint">Loading flight statistics...</p>
              </div>
            ) : (
              <div className="logbook-stats-grid">
                <div className="logbook-stats-card">
                  <h4>Summary</h4>
                  <dl className="logbook-stats-list">
                    <div><dt>Source</dt><dd>{sourceLabel(detailFlight.source_kind)}</dd></div>
                    <div><dt>Duration</dt><dd>{formatDuration(detailFlight.stats.duration_seconds)}</dd></div>
                    <div><dt>Highest altitude</dt><dd>{formatAltitude(detailFlight.stats.highest_altitude_m, units.altitude)}</dd></div>
                    <div><dt>Best climb</dt><dd>{formatVario(detailFlight.stats.best_climb_mps, units.vario)}</dd></div>
                    <div><dt>Launch time</dt><dd>{detailFlight.stats.launch_time ? new Date(detailFlight.stats.launch_time).toLocaleString() : "--"}</dd></div>
                    <div><dt>Landing time</dt><dd>{detailFlight.stats.landing_time ? new Date(detailFlight.stats.landing_time).toLocaleString() : "--"}</dd></div>
                  </dl>
                </div>
                <div className="logbook-stats-card">
                  <h4>Derived statistics</h4>
                  <dl className="logbook-stats-list">
                    <div><dt>Launch altitude</dt><dd>{formatAltitude(detailFlight.stats.launch_altitude_m, units.altitude)}</dd></div>
                    <div><dt>Landing altitude</dt><dd>{formatAltitude(detailFlight.stats.landing_altitude_m, units.altitude)}</dd></div>
                    <div><dt>Fix count</dt><dd>{detailFlight.stats.fix_count || 0}</dd></div>
                    <div><dt>Total track distance</dt><dd>{detailFlight.stats.total_track_distance_km ? `${detailFlight.stats.total_track_distance_km.toFixed(1)} km` : "--"}</dd></div>
                    <div><dt>Max ground speed</dt><dd>{detailFlight.stats.max_ground_speed_kmh ? `${detailFlight.stats.max_ground_speed_kmh.toFixed(1)} km/h` : "--"}</dd></div>
                    <div><dt>IGC file</dt><dd>{detailFlight.filename || "--"}</dd></div>
                  </dl>
                </div>
                <div className="logbook-stats-card logbook-stats-notes">
                  <h4>Notes</h4>
                  <p>{detailFlight.notes?.trim() ? detailFlight.notes : "No notes saved for this flight yet."}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}

      {replayFlight ? (
        <div className="logbook-modal-overlay active" role="presentation">
          <div className="logbook-modal logbook-modal-map">
            <div className="section-card-header">
              <div>
                <h3>{replayTitle}</h3>
                <p className="hint">Replay this personal flight using the same controls as the task replay map.</p>
              </div>
              <div className="button-row compact">
                <button type="button" className="ghost-button" onClick={closeFlightReplay}>Close</button>
              </div>
            </div>
            {replayLoading || !replayTrack ? (
              <div className="stack form-block">
                <p className="hint">Loading replay track...</p>
              </div>
            ) : (
              <div className="logbook-replay-shell">
                <TaskMap
                  turnpoints={[]}
                  taskPoints={[]}
                  track={replayTrack}
                  editable={false}
                  units={units}
                  telemetrySmoothing={telemetrySmoothing}
                  mode="replay"
                />
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
