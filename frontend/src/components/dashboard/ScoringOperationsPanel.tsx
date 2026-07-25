"use client";

import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";

import { computeTaskOptimization } from "../../lib/taskOptimization";
import { formatPenaltyPoints, formatScorePoints } from "../../lib/scorePenalties";
import { SectionCard } from "../SectionCard";
import type {
  BulkUploadItemRecord,
  ScorePenaltyRecord,
  PilotSummaryRecord,
  ScoringLogbookCandidateRecord,
  ScoringLogbookSelectResponseRecord,
  ScoringOperationsResponseRecord,
  ScoringOperationsRowRecord,
  ScoringPresetRecord,
  TaskRecord,
} from "./types";

type FeedbackState = { type: "success" | "error" | "pending"; text: string } | null;
type ConfirmAction = "delete_all" | "delete_scored_task" | null;
type UploadedIgcRecord = { id: number; pilot_id: number; filename: string };
type LogbookPickerState = {
  row: ScoringOperationsRowRecord;
  candidates: ScoringLogbookCandidateRecord[];
  loading: boolean;
  error: string | null;
  selectingFlightId: number | null;
} | null;
const TOKEN_KEY = "flightcomp-platform-token";
const REFRESH_TOKEN_KEY = "flightcomp-platform-refresh-token";
let refreshPromise: Promise<string> | null = null;

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") return configured || "/backend";
  return configured ?? "/backend";
}

async function refreshAccessToken(): Promise<string> {
  if (typeof window === "undefined") return "";
  const refreshToken = window.localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return "";
  try {
    const response = await fetch(`${resolveApiBase()}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
    if (!response.ok) return "";
    const data = (await response.json()) as { access_token?: string; refresh_token?: string };
    if (!data.access_token) return "";
    window.localStorage.setItem(TOKEN_KEY, data.access_token);
    if (data.refresh_token) window.localStorage.setItem(REFRESH_TOKEN_KEY, data.refresh_token);
    return data.access_token;
  } catch {
    return "";
  }
}

async function responseError(response: Response): Promise<Error> {
  const text = await response.text();
  if (response.status === 401 && text.includes("Invalid token")) {
    return new Error("Session expired. Please sign in again, then retry the upload.");
  }
  return new Error(text || `Request failed (${response.status})`);
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  const buildInit = (activeToken: string): RequestInit => ({
    ...init,
    cache: "no-store",
    headers: {
      ...(activeToken ? { Authorization: `Bearer ${activeToken}` } : {}),
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
      ...init.headers,
    },
  });
  const response = await fetch(`${resolveApiBase()}${path}`, buildInit(token));
  if (response.status === 401) {
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().then((newToken) => {
        refreshPromise = null;
        return newToken;
      });
    }
    const newToken = await refreshPromise;
    if (newToken) {
      const retryResponse = await fetch(`${resolveApiBase()}${path}`, buildInit(newToken));
      if (!retryResponse.ok) throw await responseError(retryResponse);
      if (retryResponse.status === 204) return undefined as T;
      return retryResponse.json() as Promise<T>;
    }
  }
  if (!response.ok) {
    throw await responseError(response);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function formatElapsedSeconds(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  const totalSeconds = Math.max(0, Math.round(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatPoints(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  return value.toFixed(1);
}

function formatShortDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function formatDuration(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "-";
  const totalSeconds = Math.max(0, Math.round(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function sourceLabel(value: string): string {
  switch (value) {
    case "task_upload":
      return "Task";
    case "app_upload":
      return "Logbook";
    default:
      return value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
  }
}

function rowSelectionValue(row: ScoringOperationsRowRecord): string {
  if (row.selected_upload_id != null) return `file:${row.selected_upload_id}`;
  if (row.status_override) return `status:${row.status_override}`;
  return "";
}

function rowSelectClassName(row: ScoringOperationsRowRecord): string {
  if (row.selected_upload_id != null) return "scoring-ops-select has-file";
  if (row.status_override) return "scoring-ops-select has-status";
  return "scoring-ops-select";
}

function calculatePenaltyCascade(rawScore: number, penalties: ScorePenaltyRecord[]) {
  let running = Math.max(rawScore || 0, 0);
  const percentage = penalties.filter((item) => item.penalty_type === "percentage");
  const fixed = penalties.filter((item) => item.penalty_type === "fixed");
  const percentLines = percentage.map((penalty) => {
    const delta = running * (Math.max(penalty.value || 0, 0) / 100);
    running -= delta;
    return { label: penalty.reason || "Percentage penalty", delta, display: `-${penalty.value}%` };
  });
  const afterPercent = Math.max(running, 0);
  const fixedLines = fixed.map((penalty) => {
    const delta = Math.max(penalty.value || 0, 0);
    running -= delta;
    return { label: penalty.reason || "Fixed penalty", delta, display: `-${penalty.value} pts` };
  });
  return {
    afterPercent,
    afterFixed: Math.max(running, 0),
    final: Math.max(running, 0),
    percentLines,
    fixedLines,
  };
}

function rowSortKey(row: ScoringOperationsRowRecord, hasResults: boolean): [number, number, string] {
  if (!hasResults) return [0, 0, row.pilot_name.toLowerCase()];
  const order: Record<string, number> = { ranked: 0, minimum_distance: 1, did_not_fly: 2, absent: 3, unscored: 4 };
  return [order[row.row_classification] ?? 9, row.result?.rank ?? 999999, row.pilot_name.toLowerCase()];
}

function blankPreset(id: string): ScoringPresetRecord {
  return { id, label: "", penalty_type: "percentage", value: 0, reason: "" };
}

function openPenaltyEditor(
  row: ScoringOperationsRowRecord,
  setPanelPilotId: (value: number | null) => void,
  setDraftPenalties: (value: ScorePenaltyRecord[]) => void,
) {
  setPanelPilotId(row.pilot_id);
  setDraftPenalties(row.penalties.map((penalty, index) => ({ ...penalty, position: index })));
}

export interface ScoringOperationsPanelProps {
  selectedEventId: number | null;
  selectedTaskId: number | null;
  selectedTask: TaskRecord | null;
  tasks: TaskRecord[];
  token: string;
  activeSection: string;
  loadTask: (activeToken: string, taskId: number, loadedTask?: TaskRecord, includeScoringData?: boolean) => Promise<void>;
  refreshPilotSummary: (activeToken: string, eventId: number) => Promise<unknown>;
}

export default function ScoringOperationsPanel({
  selectedEventId,
  selectedTaskId,
  selectedTask,
  tasks,
  token,
  activeSection,
  loadTask,
  refreshPilotSummary,
}: ScoringOperationsPanelProps) {
  const [rows, setRows] = useState<ScoringOperationsRowRecord[]>([]);
  const [presets, setPresets] = useState<ScoringPresetRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<FeedbackState>(null);
  const [confirmAction, setConfirmAction] = useState<ConfirmAction>(null);
  const [panelPilotId, setPanelPilotId] = useState<number | null>(null);
  const [draftPenalties, setDraftPenalties] = useState<ScorePenaltyRecord[]>([]);
  const [savingPenalties, setSavingPenalties] = useState(false);
  const [logbookPicker, setLogbookPicker] = useState<LogbookPickerState>(null);
  const rowUploadRefs = useRef<Record<number, HTMLInputElement | null>>({});
  const bulkUploadRef = useRef<HTMLInputElement | null>(null);
  const publishedTasks = tasks.filter((task) => task.status === "published");
  const activePublishedTaskId = selectedTask?.status === "published" ? selectedTaskId : null;
  const scoringSelectedTaskId = activePublishedTaskId ?? "";

  const refreshRows = async () => {
    if (!token || !activePublishedTaskId) {
      setRows([]);
      return;
    }
    const payload = await apiFetch<ScoringOperationsResponseRecord>(`/api/tasks/${activePublishedTaskId}/scoring-operations`, token);
    setRows(payload.rows);
  };

  useEffect(() => {
    let cancelled = false;

    async function load() {
      if (!activePublishedTaskId || !token) {
        setRows([]);
        return;
      }
      setLoading(true);
      try {
        const [ops, presetData] = await Promise.all([
          apiFetch<ScoringOperationsResponseRecord>(`/api/tasks/${activePublishedTaskId}/scoring-operations`, token),
          selectedEventId
            ? apiFetch<ScoringPresetRecord[]>(`/api/events/${selectedEventId}/scoring-presets`, token)
            : Promise.resolve([]),
        ]);
        if (cancelled) return;
        setRows(ops.rows);
        setPresets(presetData);
      } catch (caught) {
        if (!cancelled) {
          setFeedback({
            type: "error",
            text: caught instanceof Error ? caught.message : "Could not load scoring operations.",
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [activePublishedTaskId, selectedEventId, token]);

  const hasResults = useMemo(() => rows.some((row) => row.result != null), [rows]);
  const taskResultsOfficial = useMemo(
    () => hasResults && rows.every((row) => row.result == null || row.result.result_state === "official"),
    [hasResults, rows],
  );
  const taskDistanceKm = useMemo(() => computeTaskOptimization(selectedTask?.points ?? []).totalDistanceKm, [selectedTask?.points]);
  const sortedRows = useMemo(
    () =>
      [...rows].sort((left, right) => {
        const leftKey = rowSortKey(left, hasResults);
        const rightKey = rowSortKey(right, hasResults);
        return leftKey[0] - rightKey[0] || leftKey[1] - rightKey[1] || leftKey[2].localeCompare(rightKey[2]);
      }),
    [rows, hasResults],
  );
  const activeRow = useMemo(() => sortedRows.find((row) => row.pilot_id === panelPilotId) ?? null, [panelPilotId, sortedRows]);
  const penaltyBaseScore = (activeRow?.result?.raw_score_points ?? activeRow?.result?.score_points ?? 0)
    + (activeRow?.result?.handicap_adjustment_points ?? 0);
  const penaltyCascade = useMemo(
    () => calculatePenaltyCascade(penaltyBaseScore, draftPenalties),
    [penaltyBaseScore, draftPenalties],
  );
  const automaticPenaltyLines = activeRow?.result?.penalty_calculation?.lines.filter((line) => line.kind === "engine") ?? [];
  const automaticPenaltyPoints = automaticPenaltyLines.reduce((total, line) => total + Number(line.amount_points || 0), 0);
  const manualPenaltyPoints = Math.max(penaltyBaseScore - penaltyCascade.final, 0);
  const prePenaltyTotalPoints = penaltyCascade.final + manualPenaltyPoints + automaticPenaltyPoints;

  const reloadTaskAndRows = async () => {
    if (!token || !activePublishedTaskId) return;
    await loadTask(token, activePublishedTaskId, undefined, activeSection === "scoring");
    await refreshRows();
  };

  const refreshEventSummary = async () => {
    if (!token || !selectedEventId) return;
    await refreshPilotSummary(token, selectedEventId);
  };

  const handleRescoreTask = async () => {
    if (!token || !activePublishedTaskId) return;
    try {
      const rowsToAutoSelect = rows
        .filter((row) => row.selected_upload_id == null && !row.status_override && row.uploads.length > 0)
        .map((row) => {
          const newestUpload = [...row.uploads].sort(
            (left, right) => Date.parse(right.uploaded_at || "") - Date.parse(left.uploaded_at || ""),
          )[0];
          return newestUpload ? { pilotId: row.pilot_id, uploadId: newestUpload.id } : null;
        })
        .filter((row): row is { pilotId: number; uploadId: number } => row != null);
      setFeedback({
        type: "pending",
        text: rowsToAutoSelect.length
          ? `Selecting ${rowsToAutoSelect.length} most recent file${rowsToAutoSelect.length === 1 ? "" : "s"} and scoring ${selectedTask?.name ?? "the selected task"}...`
          : `Scoring ${selectedTask?.name ?? "the selected task"}...`,
      });
      if (rowsToAutoSelect.length) {
        await Promise.all(rowsToAutoSelect.map((row) => saveSelectionAndRescore(row.pilotId, row.uploadId, null)));
      }
      await apiFetch(`/api/tasks/${activePublishedTaskId}/rescore`, token, { method: "POST" });
      await reloadTaskAndRows();
      await refreshEventSummary();
      setFeedback({
        type: "success",
        text: rowsToAutoSelect.length
          ? `Selected the most recent files and scored ${selectedTask?.name ?? "the selected task"}.`
          : `Scoring completed for ${selectedTask?.name ?? "the selected task"}.`,
      });
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Scoring failed." });
    }
  };

  const handleTaskChange = async (event: ChangeEvent<HTMLSelectElement>) => {
    if (!token) return;
    const nextTaskId = Number(event.target.value);
    const nextTask = publishedTasks.find((task) => task.id === nextTaskId);
    if (nextTask) await loadTask(token, nextTaskId, nextTask, activeSection === "scoring");
  };

  const handleSelectionChange = async (pilotId: number, rawValue: string) => {
    if (!token || !activePublishedTaskId) return;
    const payload =
      rawValue.startsWith("file:")
        ? { selected_upload_id: Number(rawValue.slice(5)), status_override: null }
        : rawValue.startsWith("status:")
          ? { selected_upload_id: null, status_override: rawValue.slice(7) }
          : { selected_upload_id: null, status_override: null };
    try {
      setFeedback({ type: "pending", text: "Updating scoring..." });
      await apiFetch(`/api/tasks/${activePublishedTaskId}/scoring-inputs/${pilotId}`, token, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      await apiFetch(`/api/tasks/${activePublishedTaskId}/rescore`, token, { method: "POST" });
      await reloadTaskAndRows();
      await refreshEventSummary();
      setFeedback({ type: "success", text: "Scoring updated." });
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not update scoring input." });
    }
  };

  const saveSelectionAndRescore = async (pilotId: number, selectedUploadId: number | null, statusOverride: string | null) => {
    if (!token || !activePublishedTaskId) return;
    await apiFetch(`/api/tasks/${activePublishedTaskId}/scoring-inputs/${pilotId}`, token, {
      method: "PATCH",
      body: JSON.stringify({
        selected_upload_id: selectedUploadId,
        status_override: statusOverride,
      }),
    });
  };

  const handleSingleUpload = async (pilotId: number, file: File) => {
    if (!token || !activePublishedTaskId) return;
    const formData = new FormData();
    formData.append("file", file);
    formData.append("pilot_id", String(pilotId));
    try {
      setFeedback({ type: "pending", text: `Uploading ${file.name}...` });
      const uploaded = await apiFetch<UploadedIgcRecord>(`/api/tasks/${activePublishedTaskId}/uploads`, token, { method: "POST", body: formData });
      await saveSelectionAndRescore(pilotId, uploaded.id, null);
      await apiFetch(`/api/tasks/${activePublishedTaskId}/rescore`, token, { method: "POST" });
      await reloadTaskAndRows();
      await refreshEventSummary();
      setFeedback({ type: "success", text: `Uploaded and scored ${file.name}.` });
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Upload failed." });
    }
  };

  const openLogbookPicker = async (row: ScoringOperationsRowRecord) => {
    if (!token || !activePublishedTaskId) return;
    setLogbookPicker({ row, candidates: [], loading: true, error: null, selectingFlightId: null });
    try {
      const candidates = await apiFetch<ScoringLogbookCandidateRecord[]>(
        `/api/tasks/${activePublishedTaskId}/pilots/${row.pilot_id}/logbook-igc-candidates`,
        token,
      );
      setLogbookPicker({ row, candidates, loading: false, error: null, selectingFlightId: null });
    } catch (caught) {
      setLogbookPicker({
        row,
        candidates: [],
        loading: false,
        error: caught instanceof Error ? caught.message : "Could not load logbook files.",
        selectingFlightId: null,
      });
    }
  };

  const selectLogbookCandidate = async (flightId: number) => {
    if (!token || !activePublishedTaskId || !logbookPicker) return;
    const row = logbookPicker.row;
    setLogbookPicker({ ...logbookPicker, selectingFlightId: flightId, error: null });
    try {
      const result = await apiFetch<ScoringLogbookSelectResponseRecord>(
        `/api/tasks/${activePublishedTaskId}/pilots/${row.pilot_id}/logbook-igc-candidates/${flightId}/select`,
        token,
        { method: "POST" },
      );
      await reloadTaskAndRows();
      await refreshEventSummary();
      setLogbookPicker(null);
      setFeedback({ type: "success", text: `Selected logbook IGC for ${row.pilot_name}. Upload ${result.selected_upload_id} is now scored.` });
    } catch (caught) {
      setLogbookPicker({
        ...logbookPicker,
        selectingFlightId: null,
        error: caught instanceof Error ? caught.message : "Could not select that logbook file.",
      });
    }
  };

  const handleBulkUpload = async (files: FileList | File[]) => {
    if (!token || !activePublishedTaskId) return;
    const formData = new FormData();
    Array.from(files).forEach((file) => formData.append("files", file));
    try {
      setFeedback({ type: "pending", text: `Uploading ${Array.from(files).length} IGC files...` });
      const batchResults = await apiFetch<BulkUploadItemRecord[]>(`/api/tasks/${activePublishedTaskId}/uploads/bulk`, token, { method: "POST", body: formData });
      const matchedCount = batchResults.filter((item) => item.matched).length;
      const duplicateCount = batchResults.filter((item) => item.message.toLowerCase().includes("already uploaded")).length;
      const unmatchedCount = batchResults.length - matchedCount;
      await reloadTaskAndRows();
      await refreshEventSummary();
      const details = [
        `${matchedCount} matched`,
        duplicateCount ? `${duplicateCount} already existed` : null,
        unmatchedCount ? `${unmatchedCount} need review` : null,
      ].filter(Boolean);
      setFeedback({ type: "success", text: `Bulk upload complete and task scored: ${details.join(", ")}.` });
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Bulk upload failed." });
    }
  };

  const handleDeleteSelectedUpload = async (row: ScoringOperationsRowRecord) => {
    if (!token || row.selected_upload_id == null) return;
    try {
      await apiFetch(`/api/uploads/${row.selected_upload_id}`, token, { method: "DELETE" });
      await reloadTaskAndRows();
      await refreshEventSummary();
      setFeedback({ type: "success", text: `Deleted the selected file for ${row.pilot_name}.` });
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Delete failed." });
    }
  };

  const savePenalties = async () => {
    if (!token || !activePublishedTaskId || activeRow == null) return;
    try {
      setSavingPenalties(true);
      await apiFetch(`/api/tasks/${activePublishedTaskId}/penalties/${activeRow.pilot_id}`, token, {
        method: "PUT",
        body: JSON.stringify({
          penalties: draftPenalties.map((penalty, index) => ({
            penalty_type: penalty.penalty_type,
            value: penalty.value,
            reason: penalty.reason,
            position: index,
          })),
        }),
      });
      await reloadTaskAndRows();
      await refreshEventSummary();
      setPanelPilotId(null);
      setFeedback({ type: "success", text: `Saved penalties for ${activeRow.pilot_name}.` });
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not save penalties." });
    } finally {
      setSavingPenalties(false);
    }
  };

  const executeConfirmAction = async () => {
    if (!token || !selectedTaskId || !confirmAction) return;
    try {
      if (confirmAction === "delete_all") {
        setFeedback({ type: "pending", text: "Deleting task uploads..." });
        await apiFetch(`/api/tasks/${selectedTaskId}/uploads`, token, { method: "DELETE" });
        await reloadTaskAndRows();
        await refreshEventSummary();
        setFeedback({ type: "success", text: "Deleted all uploaded files for the selected task." });
      } else {
        setFeedback({ type: "pending", text: "Deleting scored task results..." });
        await apiFetch(`/api/tasks/${selectedTaskId}/results`, token, { method: "DELETE" });
        await reloadTaskAndRows();
        await refreshEventSummary();
          setFeedback({ type: "success", text: `Deleted scoring results for ${selectedTask?.name ?? "the selected task"} and cleared all file/status selections.` });
      }
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Action failed." });
    } finally {
      setConfirmAction(null);
    }
  };

  const toggleTaskResultsState = async () => {
    if (!token || !activePublishedTaskId) return;
    try {
      setFeedback({ type: "pending", text: taskResultsOfficial ? "Marking task provisional..." : "Marking task official..." });
      const payload = await apiFetch<{ status: string; published_count?: number; unpublished_count?: number }>(`/api/tasks/${activePublishedTaskId}/${taskResultsOfficial ? "unpublish-results" : "publish-results"}`, token, {
        method: "POST",
      });
      await reloadTaskAndRows();
      await refreshEventSummary();
      setFeedback({
        type: "success",
        text: taskResultsOfficial
          ? payload.unpublished_count
            ? `Marked ${payload.unpublished_count} result${payload.unpublished_count === 1 ? "" : "s"} as provisional for ${selectedTask?.name ?? "the selected task"}.`
            : `All scored results for ${selectedTask?.name ?? "the selected task"} were already provisional.`
          : payload.published_count
            ? `Marked ${payload.published_count} result${payload.published_count === 1 ? "" : "s"} as official for ${selectedTask?.name ?? "the selected task"}.`
            : `All scored results for ${selectedTask?.name ?? "the selected task"} were already official.`,
      });
    } catch (caught) {
      setFeedback({ type: "error", text: caught instanceof Error ? caught.message : "Could not update task result state." });
    }
  };

  return (
    <>
      <SectionCard>
        <div className="stack form-block compact-clusters">
          <div className="scoring-nav">
            {publishedTasks.map((task) => (
              <button
                key={task.id}
                type="button"
                className={Number(scoringSelectedTaskId) === task.id ? "scoring-nav-btn active" : "scoring-nav-btn"}
                onClick={() => void handleTaskChange({ target: { value: String(task.id) } } as ChangeEvent<HTMLSelectElement>)}
              >
                {task.name}
              </button>
            ))}
            <div className="scoring-ops-task-actions">
              {feedback ? (
                <div className="scoring-ops-action-feedback" role="status" aria-live="polite">
                  <div className={`status-chip ${feedback.type}`}>{feedback.text}</div>
                </div>
              ) : null}
              <button
                type="button"
                className="scoring-ops-footer-btn secondary"
                onClick={() => bulkUploadRef.current?.click()}
                disabled={!activePublishedTaskId}
              >
                Upload all IGCs
              </button>
              <button
                type="button"
                className="scoring-ops-footer-btn destructive"
                onClick={() => setConfirmAction("delete_all")}
                disabled={!activePublishedTaskId}
              >
                Delete all IGCs
              </button>
              <button
                type="button"
                className="scoring-ops-footer-btn secondary"
                onClick={() => void handleRescoreTask()}
                disabled={!activePublishedTaskId}
              >
                Score task
              </button>
              <button
                type="button"
                className={`scoring-ops-footer-btn ${taskResultsOfficial ? "state-official" : "state-unofficial"}`}
                onClick={() => void toggleTaskResultsState()}
                disabled={!activePublishedTaskId || !hasResults}
              >
                {taskResultsOfficial ? "Official" : "Provisional"}
              </button>
              <button
                type="button"
                className="scoring-ops-footer-btn destructive"
                onClick={() => setConfirmAction("delete_scored_task")}
                disabled={!activePublishedTaskId}
              >
                Delete scored task
              </button>
            </div>
          </div>

          <div className="scoring-ops-legend">
            <span><i className="scoring-ops-swatch scored" /> Scored / status assigned</span>
            <span><i className="scoring-ops-swatch unscored" /> Unscored</span>
            <span><i className="scoring-ops-swatch penalty" /> Penalty applied</span>
          </div>

          <div className="scoring-ops-table-wrap">
            <table className="scoring-ops-table">
              <colgroup>
                <col className="rank-col" />
                <col className="name-col" />
                <col className="status-col" />
                <col className="actions-col" />
                <col className="penalty-col" />
                <col className="time-col" />
                <col className="points-col" />
              </colgroup>
              <thead>
                <tr>
                  <th className="center">Rank</th>
                  <th>Name</th>
                  <th>Status / File</th>
                  <th className="center">Actions</th>
                  <th className="center">Penalty</th>
                  <th className="right">Time / Distance</th>
                  <th className="right">Points</th>
                </tr>
              </thead>
              <tbody>
                {selectedTaskId == null ? (
                  <tr>
                    <td colSpan={7} className="scoring-ops-empty">Select a task to manage scoring operations.</td>
                  </tr>
                ) : loading ? (
                  <tr>
                    <td colSpan={7} className="scoring-ops-empty">Loading scoring operations...</td>
                  </tr>
                ) : sortedRows.length ? (
                  sortedRows.map((row) => {
                    const hasPenalty = Boolean(row.penalty_summary || row.result?.penalty_calculation?.lines?.length);
                    const penaltyEnabled = row.result != null && row.result.upload_id != null;
                    return (
                      <tr key={row.pilot_id} className={row.row_classification === "unscored" ? "unscored" : hasPenalty ? "has-penalty" : "scored"}>
                        <td className="center">
                          {row.result?.rank != null ? <span className="scoring-ops-rank-badge">{row.result.rank}</span> : <span className="scoring-ops-muted">-</span>}
                        </td>
                        <td>
                          <div className="scoring-ops-pilot-name">{row.pilot_name}</div>
                        </td>
                        <td>
                          <select
                            className={rowSelectClassName(row)}
                            value={rowSelectionValue(row)}
                            onChange={(event) => void handleSelectionChange(row.pilot_id, event.target.value)}
                          >
                            <option value="">- Select file or status -</option>
                            {row.uploads.map((upload) => (
                              <option key={upload.id} value={`file:${upload.id}`}>
                                {upload.label}{upload.late_start ? ' [LATE START]' : ''}
                              </option>
                            ))}
                            <option value="status:minimum_distance">Minimum Distance</option>
                            <option value="status:did_not_fly">Did Not Fly</option>
                            <option value="status:absent">Absent</option>
                          </select>
                        </td>
                        <td>
                          <div className="scoring-ops-actions">
                            <button
                              type="button"
                              className="scoring-ops-btn danger"
                              disabled={row.selected_upload_id == null}
                              onClick={() => void handleDeleteSelectedUpload(row)}
                            >
                              Delete
                            </button>
                            <button
                              type="button"
                              className="scoring-ops-btn upload"
                              onClick={() => rowUploadRefs.current[row.pilot_id]?.click()}
                            >
                              Upload
                            </button>
                            <button
                              type="button"
                              className="scoring-ops-btn logbook"
                              onClick={() => void openLogbookPicker(row)}
                              disabled={!selectedTask?.task_date}
                            >
                              Pick from Logbook
                            </button>
                            <input
                              ref={(node) => {
                                rowUploadRefs.current[row.pilot_id] = node;
                              }}
                              type="file"
                              accept=".igc"
                              className="hidden-file-input"
                              onChange={(event) => {
                                const file = event.target.files?.[0];
                                if (file) void handleSingleUpload(row.pilot_id, file);
                                event.currentTarget.value = "";
                              }}
                            />
                          </div>
                        </td>
                        <td className="center">
                          <div className="scoring-ops-penalty-wrap">
                            <input
                              type="checkbox"
                              checked={hasPenalty}
                              disabled={!penaltyEnabled}
                              onChange={() => {
                                if (!penaltyEnabled) return;
                                openPenaltyEditor(row, setPanelPilotId, setDraftPenalties);
                              }}
                            />
                            {hasPenalty ? (
                              <button
                                type="button"
                                className="scoring-ops-penalty-badge"
                                onClick={() => {
                                  if (!penaltyEnabled) return;
                                  openPenaltyEditor(row, setPanelPilotId, setDraftPenalties);
                                }}
                              >
                                {row.penalty_summary}
                              </button>
                            ) : null}
                          </div>
                        </td>
                        <td className="right">
                          {row.result ? (
                            row.result.status === "goal" && row.result.elapsed_seconds != null ? (
                              formatElapsedSeconds(row.result.elapsed_seconds)
                            ) : row.result.distance_flown_km > 0 && taskDistanceKm > 0 ? (
                              `${row.result.distance_flown_km.toFixed(1)} / ${taskDistanceKm.toFixed(1)} km`
                            ) : (
                              <span className="scoring-ops-muted">-</span>
                            )
                          ) : (
                            <span className="scoring-ops-muted">-</span>
                          )}
                        </td>
                        <td className={`right ${hasPenalty ? "scoring-ops-points-penalized" : "scoring-ops-points"}`}>
                          {row.result ? formatPoints(row.result.score_points) : <span className="scoring-ops-muted">-</span>}
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={7} className="scoring-ops-empty">No pilots are available for this task.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="scoring-ops-footer-actions">
            <div className="scoring-ops-footer-note">
              Scoring uses the <strong>currently selected item</strong> in each pilot&apos;s dropdown - file, status, or blank.
            </div>
            <input
              ref={bulkUploadRef}
              type="file"
              accept=".igc"
              multiple
              className="hidden-file-input"
              onChange={(event) => {
                const files = event.target.files;
                if (files?.length) void handleBulkUpload(files);
                event.currentTarget.value = "";
              }}
            />
          </div>
        </div>
      </SectionCard>

      <div className={`scoring-ops-modal-overlay${confirmAction ? " active" : ""}`} onClick={() => setConfirmAction(null)}>
        <div className="scoring-ops-modal" onClick={(event) => event.stopPropagation()}>
          <div className="scoring-ops-modal-title">
            {confirmAction === "delete_all" ? "Delete all IGCs?" : "Delete scored task?"}
          </div>
          <div className="scoring-ops-modal-body">
            {confirmAction === "delete_all"
              ? "Are you sure you want to delete all IGC files for this task? This cannot be undone."
                : "Are you sure you want to delete the scored task? All scoring results will be lost, and every Status / File selector will be reset to blank. This cannot be undone."}
          </div>
          <div className="scoring-ops-modal-actions">
            <button type="button" className="scoring-ops-footer-btn secondary" onClick={() => setConfirmAction(null)}>Cancel</button>
            <button type="button" className="scoring-ops-footer-btn destructive" onClick={() => void executeConfirmAction()}>
              {confirmAction === "delete_all" ? "Delete all IGCs" : "Delete scored task"}
            </button>
          </div>
        </div>
      </div>

      <div className={`scoring-ops-modal-overlay${logbookPicker ? " active" : ""}`} onClick={() => setLogbookPicker(null)}>
        <div className="scoring-ops-modal scoring-ops-logbook-modal" onClick={(event) => event.stopPropagation()}>
          <div className="scoring-ops-modal-title">
            Pick from Logbook
          </div>
          <div className="scoring-ops-modal-body">
            {logbookPicker ? (
              <>
                <div className="scoring-ops-logbook-heading">
                  <strong>{logbookPicker.row.pilot_name}</strong>
                  <span>{selectedTask?.name ?? "Task"} - {formatShortDate(selectedTask?.task_date)}</span>
                </div>
                {logbookPicker.loading ? (
                  <div className="scoring-ops-empty compact">Loading logbook IGC files...</div>
                ) : logbookPicker.error ? (
                  <div className="status-chip error">{logbookPicker.error}</div>
                ) : logbookPicker.candidates.length ? (
                  <div className="scoring-ops-logbook-list">
                    {logbookPicker.candidates.map((candidate) => {
                      const context = [candidate.event_name, candidate.task_name].filter(Boolean).join(" - ");
                      const selecting = logbookPicker.selectingFlightId === candidate.flight_id;
                      return (
                        <div key={candidate.flight_id} className="scoring-ops-logbook-row">
                          <div className="scoring-ops-logbook-main">
                            <div className="scoring-ops-logbook-title">{candidate.filename ?? `Flight ${candidate.flight_id}`}</div>
                            <div className="scoring-ops-logbook-meta">
                              <span>{formatShortDate(candidate.flight_date)}</span>
                              <span>{sourceLabel(candidate.source_kind)}</span>
                              {context ? <span>{context}</span> : null}
                              {candidate.already_linked_upload_id ? <span>Upload {candidate.already_linked_upload_id}</span> : null}
                            </div>
                            <div className="scoring-ops-logbook-stats">
                              <span>{formatDuration(candidate.duration_seconds)}</span>
                              <span>{candidate.highest_altitude_m != null ? `${Math.round(candidate.highest_altitude_m)} m max` : "- max"}</span>
                              <span>{candidate.best_climb_mps != null ? `${candidate.best_climb_mps.toFixed(1)} m/s climb` : "- climb"}</span>
                            </div>
                          </div>
                          <button
                            type="button"
                            className="scoring-ops-footer-btn secondary"
                            disabled={logbookPicker.selectingFlightId != null}
                            onClick={() => void selectLogbookCandidate(candidate.flight_id)}
                          >
                            {selecting ? "Selecting..." : "Select"}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                ) : (
                  <div className="scoring-ops-empty compact">No same-date IGC files were found in this pilot&apos;s logbook.</div>
                )}
              </>
            ) : null}
          </div>
          <div className="scoring-ops-modal-actions">
            <button type="button" className="scoring-ops-footer-btn secondary" onClick={() => setLogbookPicker(null)}>Close</button>
          </div>
        </div>
      </div>

      <div className={`scoring-ops-panel-overlay${panelPilotId != null ? " active" : ""}`} onClick={() => setPanelPilotId(null)} />
      <aside className={`scoring-ops-penalty-panel${panelPilotId != null ? " open" : ""}`}>
        <div className="scoring-ops-panel-header">
          <div className="scoring-ops-panel-header-top">
            <div>
              <div className="scoring-ops-panel-title">Penalty editor</div>
              <div className="scoring-ops-panel-pilot">{activeRow ? `${activeRow.pilot_name} - ${selectedTask?.name ?? "Task"}` : ""}</div>
            </div>
            <button type="button" className="scoring-ops-panel-close" onClick={() => setPanelPilotId(null)}>x</button>
          </div>
        </div>
        <div className="scoring-ops-panel-body">
          <div className="scoring-ops-score-strip">
            <div className="scoring-ops-score-strip-item">
              <div className="scoring-ops-strip-label">Total</div>
              <div className="scoring-ops-strip-value">{formatScorePoints(prePenaltyTotalPoints)}</div>
            </div>
            <div className="scoring-ops-score-strip-item">
              <div className="scoring-ops-strip-label">Automatic Penalties</div>
              <div className="scoring-ops-strip-value amber score-penalty-amount">{formatPenaltyPoints({ score_points: 0, penalty_calculation: { raw_score_points: 0, final_score_points: 0, manual_penalty_points: 0, engine_penalty_points: automaticPenaltyPoints, total_display_penalty_points: automaticPenaltyPoints, lines: [] } })}</div>
            </div>
            <div className="scoring-ops-score-strip-item">
              <div className="scoring-ops-strip-label">Manual Penalties</div>
              <div className="scoring-ops-strip-value amber score-penalty-amount">{formatPenaltyPoints({ score_points: 0, penalty_calculation: { raw_score_points: 0, final_score_points: 0, manual_penalty_points: manualPenaltyPoints, engine_penalty_points: 0, total_display_penalty_points: manualPenaltyPoints, lines: [] } })}</div>
            </div>
            <div className="scoring-ops-score-strip-item">
              <div className="scoring-ops-strip-label">Final score</div>
              <div className="scoring-ops-strip-value blue">{formatScorePoints(penaltyCascade.final)}</div>
            </div>
          </div>

          <div className="scoring-ops-section-label">Quick presets</div>
          <div className="scoring-ops-preset-grid">
            {presets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                className="scoring-ops-preset-btn"
                onClick={() =>
                  setDraftPenalties((current) => [
                    ...current,
                    { penalty_type: preset.penalty_type, value: preset.value, reason: preset.reason, position: current.length },
                  ])
                }
              >
                {preset.label}
              </button>
            ))}
          </div>

          <div className="scoring-ops-divider" />
          {automaticPenaltyLines.length ? (
            <>
              <div className="scoring-ops-section-label">Automatic penalties</div>
              <div className="score-penalty-lines scoring-ops-automatic-penalties">
                {automaticPenaltyLines.map((line, index) => (
                  <div key={`${line.kind}-${index}`} className="score-penalty-line">
                    <div>
                      <strong>{line.label}</strong>
                      {line.detail ? <span>{line.detail}</span> : null}
                    </div>
                    <div>
                      <strong className="score-penalty-amount">{formatPenaltyPoints({ score_points: 0, penalty_calculation: { raw_score_points: 0, final_score_points: 0, manual_penalty_points: 0, engine_penalty_points: line.amount_points, total_display_penalty_points: line.amount_points, lines: [] } })}</strong>
                    </div>
                  </div>
                ))}
              </div>
              <div className="scoring-ops-divider" />
            </>
          ) : null}
          <div className="scoring-ops-section-label">Applied penalties</div>
          {draftPenalties.length ? (
            draftPenalties.map((penalty, index) => (
              <div key={`${penalty.id ?? "new"}-${index}`} className="scoring-ops-penalty-row">
                <select
                  value={penalty.penalty_type}
                  onChange={(event) =>
                    setDraftPenalties((current) =>
                      current.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, penalty_type: event.target.value as "percentage" | "fixed" } : item,
                      ),
                    )
                  }
                >
                  <option value="percentage">% penalty</option>
                  <option value="fixed">Fixed pts</option>
                </select>
                <input
                  type="number"
                  value={penalty.value}
                  onChange={(event) =>
                    setDraftPenalties((current) =>
                      current.map((item, itemIndex) => (itemIndex === index ? { ...item, value: Number(event.target.value || 0) } : item)),
                    )
                  }
                />
                <input
                  value={penalty.reason}
                  onChange={(event) =>
                    setDraftPenalties((current) =>
                      current.map((item, itemIndex) => (itemIndex === index ? { ...item, reason: event.target.value } : item)),
                    )
                  }
                  placeholder="Reason / category"
                />
                <button
                  type="button"
                  className="scoring-ops-remove-btn"
                  onClick={() => setDraftPenalties((current) => current.filter((_, itemIndex) => itemIndex !== index))}
                >
                  x
                </button>
              </div>
            ))
          ) : (
            <div className="scoring-ops-empty-state">No penalties applied.</div>
          )}

          <button
            type="button"
            className="scoring-ops-add-penalty-btn"
            onClick={() => setDraftPenalties((current) => [...current, { penalty_type: "percentage", value: 0, reason: "", position: current.length }])}
          >
            Add penalty
          </button>

          <div className="scoring-ops-calc-box">
            <div className="scoring-ops-calc-row">
              <span>Total</span>
              <span>{formatScorePoints(prePenaltyTotalPoints)}</span>
            </div>
            {automaticPenaltyLines.map((line, index) => (
              <div key={`automatic-${index}`} className="scoring-ops-calc-row deduct">
                <span>{line.label}</span>
                <span>{formatPenaltyPoints({ score_points: 0, penalty_calculation: { raw_score_points: 0, final_score_points: 0, manual_penalty_points: 0, engine_penalty_points: line.amount_points, total_display_penalty_points: line.amount_points, lines: [] } })}</span>
              </div>
            ))}
            {penaltyCascade.percentLines.map((line, index) => (
              <div key={`percent-${index}`} className="scoring-ops-calc-row deduct">
                <span>{line.label} {line.display}</span>
                <span>-{formatPoints(line.delta)}</span>
              </div>
            ))}
            {penaltyCascade.fixedLines.map((line, index) => (
              <div key={`fixed-${index}`} className="scoring-ops-calc-row deduct">
                <span>{line.label}</span>
                <span>-{formatPoints(line.delta)}</span>
              </div>
            ))}
            <div className="scoring-ops-calc-row total">
              <span>Final score</span>
              <span>{formatPoints(penaltyCascade.final)}</span>
            </div>
          </div>

          <div className="scoring-ops-divider" />
          <div className="scoring-ops-section-label">Audit trail</div>
          {activeRow?.penalty_audit.length ? (
            activeRow.penalty_audit.map((entry, index) => (
              <div key={`${entry.timestamp}-${index}`} className="scoring-ops-audit-row">
                <span>{entry.actor_name} - {entry.summary}</span>
                <span>{new Date(entry.timestamp).toLocaleString()}</span>
              </div>
            ))
          ) : (
            <div className="scoring-ops-empty-state">No penalty edits recorded yet.</div>
          )}
        </div>
        <div className="scoring-ops-panel-footer">
          <button type="button" className="scoring-ops-footer-btn secondary" onClick={() => setPanelPilotId(null)}>Cancel</button>
          <button
            type="button"
            className="scoring-ops-footer-btn primary"
            disabled={!activeRow?.result || activeRow.result.upload_id == null || savingPenalties}
            onClick={() => void savePenalties()}
          >
            {savingPenalties ? "Saving..." : "Save penalties"}
          </button>
        </div>
      </aside>
    </>
  );
}
