"use client";

import { useEffect, useState } from "react";
import {
  createPasskey,
  listPasskeys,
  passkeysSupported,
  removePasskey,
  renamePasskey,
  type PasskeyRecord,
} from "../../lib/passkeys";

export default function PasskeyManager({ token }: { token: string }) {
  const [passkeys, setPasskeys] = useState<PasskeyRecord[]>([]);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [supported, setSupported] = useState(false);

  const load = () => listPasskeys(token).then(setPasskeys).catch(() => {
    setFeedback({ type: "error", text: "Passkeys could not be loaded." });
  });
  useEffect(() => setSupported(passkeysSupported()), []);
  useEffect(() => { void load(); }, [token]);

  async function add() {
    const name = window.prompt("Name this passkey", "This device")?.trim();
    if (!name) return;
    setBusy(true);
    setFeedback(null);
    try {
      await createPasskey(token, name);
      await load();
      setFeedback({ type: "success", text: "Passkey added." });
    } catch (error) {
      if (error instanceof DOMException && error.name === "NotAllowedError") return;
      setFeedback({
        type: "error",
        text: error instanceof Error ? error.message : "Passkey could not be added.",
      });
    } finally {
      setBusy(false);
    }
  }

  async function rename(passkey: PasskeyRecord) {
    const name = window.prompt("Passkey name", passkey.name)?.trim();
    if (!name || name === passkey.name) return;
    try {
      await renamePasskey(token, passkey.id, name);
      await load();
      setFeedback({ type: "success", text: "Passkey renamed." });
    } catch (error) {
      setFeedback({
        type: "error",
        text: error instanceof Error ? error.message : "Passkey could not be renamed.",
      });
    }
  }

  async function remove(passkey: PasskeyRecord) {
    if (!window.confirm(`Remove “${passkey.name}” from Aervyx?`)) return;
    try {
      await removePasskey(token, passkey.id);
      await load();
      setFeedback({ type: "success", text: "Passkey removed." });
    } catch (error) {
      setFeedback({
        type: "error",
        text: error instanceof Error ? error.message : "Passkey could not be removed.",
      });
    }
  }

  return (
    <section className="stack form-block">
      <div>
        <h3>Passkeys</h3>
        <p className="settings-description">
          Sign in with Windows Hello, face, fingerprint, or your device PIN. Aervyx never receives your biometric data.
        </p>
      </div>
      {!supported ? <div className="status-chip pending">Passkeys are not supported by this browser or device.</div> : null}
      {passkeys.map((passkey) => (
        <div className="settings-summary-row" key={passkey.id}>
          <div>
            <strong>{passkey.name}</strong>
            <div className="settings-description">
              Added {new Date(passkey.created_at).toLocaleDateString()}
              {passkey.last_used_at ? ` · Last used ${new Date(passkey.last_used_at).toLocaleDateString()}` : ""}
            </div>
          </div>
          <div className="button-row">
            <button type="button" className="secondary" onClick={() => void rename(passkey)}>Rename</button>
            <button type="button" className="danger" onClick={() => void remove(passkey)}>Remove</button>
          </div>
        </div>
      ))}
      <div className="button-row">
        <button type="button" onClick={() => void add()} disabled={!supported || busy}>
          {busy ? "Opening device security..." : "Add passkey"}
        </button>
      </div>
      {feedback ? <div className={`status-chip ${feedback.type}`}>{feedback.text}</div> : null}
    </section>
  );
}
