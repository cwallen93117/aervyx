"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { BuddyGroup, PilotSearchResult } from "./types";

function resolveApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined") {
    if (configured) {
      try {
        const parsed = new URL(configured);
        if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
          return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
        }
      } catch { return configured; }
      return configured;
    }
    return "/backend";
  }
  return configured ?? "/backend";
}

async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  headers.set("Authorization", `Bearer ${token}`);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${resolveApiBase()}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    let message = text || `Request failed: ${response.status}`;
    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (parsed.detail) message = typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail);
    } catch {}
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export interface BuddyGroupsManagerProps {
  token: string;
}

export default function BuddyGroupsManager({ token }: BuddyGroupsManagerProps) {
  const [groups, setGroups] = useState<BuddyGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [newGroupName, setNewGroupName] = useState("");
  const [editingGroupId, setEditingGroupId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  const [searchGroupId, setSearchGroupId] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<PilotSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadGroups = useCallback(async () => {
    try {
      const data = await apiFetch<BuddyGroup[]>("/api/buddies/groups", token);
      setGroups(data);
    } catch (err) {
      setFeedback({ type: "error", text: err instanceof Error ? `Failed to load buddy groups: ${err.message}` : "Failed to load buddy groups" });
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { loadGroups(); }, [loadGroups]);

  const showFeedback = useCallback((type: "success" | "error", text: string) => {
    setFeedback({ type, text });
    setTimeout(() => setFeedback(null), 3000);
  }, []);

  async function createGroup() {
    const name = newGroupName.trim();
    if (!name) return;
    try {
      await apiFetch<BuddyGroup>("/api/buddies/groups", token, {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      setNewGroupName("");
      showFeedback("success", `Created "${name}"`);
      loadGroups();
    } catch (err) {
      showFeedback("error", err instanceof Error ? err.message : "Failed to create group");
    }
  }

  async function updateGroupVisibility(groupId: number, visibility: string) {
    try {
      await apiFetch<BuddyGroup>(`/api/buddies/groups/${groupId}`, token, {
        method: "PATCH",
        body: JSON.stringify({ visibility }),
      });
      showFeedback("success", "Visibility updated");
      loadGroups();
    } catch (err) {
      showFeedback("error", err instanceof Error ? err.message : "Failed to update visibility");
    }
  }

  async function renameGroup(groupId: number) {
    const name = editingName.trim();
    if (!name) return;
    try {
      await apiFetch<BuddyGroup>(`/api/buddies/groups/${groupId}`, token, {
        method: "PATCH",
        body: JSON.stringify({ name }),
      });
      setEditingGroupId(null);
      setEditingName("");
      showFeedback("success", "Group renamed");
      loadGroups();
    } catch (err) {
      showFeedback("error", err instanceof Error ? err.message : "Failed to rename group");
    }
  }

  async function deleteGroup(groupId: number, groupName: string) {
    try {
      await apiFetch<void>(`/api/buddies/groups/${groupId}`, token, { method: "DELETE" });
      showFeedback("success", `Deleted "${groupName}"`);
      loadGroups();
    } catch (err) {
      showFeedback("error", err instanceof Error ? err.message : "Failed to delete group");
    }
  }

  async function addMember(groupId: number, pilotId: number) {
    try {
      await apiFetch<BuddyGroup>(`/api/buddies/groups/${groupId}/members`, token, {
        method: "POST",
        body: JSON.stringify({ pilot_id: pilotId }),
      });
      setSearchQuery("");
      setSearchResults([]);
      setSearchGroupId(null);
      showFeedback("success", "Pilot added");
      loadGroups();
    } catch (err) {
      showFeedback("error", err instanceof Error ? err.message : "Failed to add pilot");
    }
  }

  async function removeMember(groupId: number, pilotId: number) {
    try {
      await apiFetch<void>(`/api/buddies/groups/${groupId}/members/${pilotId}`, token, { method: "DELETE" });
      showFeedback("success", "Pilot removed");
      loadGroups();
    } catch (err) {
      showFeedback("error", err instanceof Error ? err.message : "Failed to remove pilot");
    }
  }

  function handleSearchInput(groupId: number, query: string) {
    setSearchQuery(query);
    setSearchGroupId(groupId);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    if (query.trim().length < 2) {
      setSearchResults([]);
      return;
    }
    setSearchLoading(true);
    searchTimer.current = setTimeout(async () => {
      try {
        const results = await apiFetch<PilotSearchResult[]>(
          `/api/buddies/search-pilots?q=${encodeURIComponent(query.trim())}`,
          token,
        );
        setSearchResults(results);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
  }

  if (loading) return <p className="muted">Loading buddy groups...</p>;

  return (
    <div className="stack">
      {feedback ? <div className={`status-chip ${feedback.type}`}>{feedback.text}</div> : null}

      <div className="buddy-create-row">
        <input
          className="buddy-create-input"
          value={newGroupName}
          onChange={(e) => setNewGroupName(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") createGroup(); }}
          placeholder="New group name"
          maxLength={160}
        />
        <button type="button" onClick={createGroup} disabled={!newGroupName.trim()}>
          Create group
        </button>
      </div>

      {groups.length === 0 ? (
        <p className="muted">No buddy groups yet. Create one above to start tracking pilots together.</p>
      ) : (
        <div className="buddy-groups-list">
          {groups.map((group) => (
            <div key={group.id} className="buddy-group-card">
              <div className="buddy-group-header">
                {editingGroupId === group.id ? (
                  <div className="buddy-rename-row">
                    <input
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") renameGroup(group.id); if (e.key === "Escape") setEditingGroupId(null); }}
                      autoFocus
                    />
                    <button type="button" onClick={() => renameGroup(group.id)}>Save</button>
                    <button type="button" className="ghost-button" onClick={() => setEditingGroupId(null)}>Cancel</button>
                  </div>
                ) : (
                  <>
                    <strong className="buddy-group-name">{group.name}</strong>
                    <span className="buddy-group-count">{group.members.length} pilot{group.members.length !== 1 ? "s" : ""}</span>
                    <select
                      className="buddy-visibility-select"
                      value={group.visibility ?? "private"}
                      onChange={(e) => updateGroupVisibility(group.id, e.target.value)}
                    >
                      <option value="public">Public</option>
                      <option value="users">All Aervyx users</option>
                      <option value="buddies">Buddies only</option>
                      <option value="private">Not viewable</option>
                    </select>
                    <div className="buddy-group-actions">
                      <button type="button" className="ghost-button" onClick={() => { setEditingGroupId(group.id); setEditingName(group.name); }}>Rename</button>
                      <button type="button" className="ghost-button danger-text" onClick={() => deleteGroup(group.id, group.name)}>Delete</button>
                    </div>
                  </>
                )}
              </div>

              {group.members.length > 0 ? (
                <ul className="buddy-member-list">
                  {group.members.map((member) => (
                    <li key={member.pilot_id} className="buddy-member-row">
                      <span className="buddy-member-name">
                        {member.first_name} {member.last_name}
                        {member.nation ? <span className="muted"> ({member.nation})</span> : null}
                        {member.competition_number ? <span className="muted"> #{member.competition_number}</span> : null}
                      </span>
                      <button type="button" className="ghost-button danger-text buddy-remove-btn" onClick={() => removeMember(group.id, member.pilot_id)}>
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}

              {searchGroupId === group.id ? (
                <div className="buddy-search-area">
                  <input
                    value={searchQuery}
                    onChange={(e) => handleSearchInput(group.id, e.target.value)}
                    placeholder="Search by name, email, or comp#"
                    autoFocus
                  />
                  {searchLoading ? <p className="muted">Searching...</p> : null}
                  {searchResults.length > 0 ? (
                    <ul className="buddy-search-results">
                      {searchResults.map((pilot) => {
                        const alreadyAdded = group.members.some((m) => m.pilot_id === pilot.pilot_id);
                        return (
                          <li key={pilot.pilot_id} className="buddy-search-row">
                            <span>
                              {pilot.first_name} {pilot.last_name}
                              {pilot.nation ? <span className="muted"> ({pilot.nation})</span> : null}
                              {pilot.competition_number ? <span className="muted"> #{pilot.competition_number}</span> : null}
                            </span>
                            {alreadyAdded ? (
                              <span className="muted">Already added</span>
                            ) : (
                              <button type="button" onClick={() => addMember(group.id, pilot.pilot_id)}>Add</button>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  ) : null}
                  <button type="button" className="ghost-button" onClick={() => { setSearchGroupId(null); setSearchQuery(""); setSearchResults([]); }}>
                    Close search
                  </button>
                </div>
              ) : (
                <button type="button" className="ghost-button buddy-add-btn" onClick={() => { setSearchGroupId(group.id); setSearchQuery(""); setSearchResults([]); }}>
                  + Add pilot
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
