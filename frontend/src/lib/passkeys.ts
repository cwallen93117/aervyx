export type PasskeyRecord = {
  id: number;
  name: string;
  transports: string[];
  created_at: string;
  last_used_at?: string | null;
};

type PasskeyOptions = {
  ceremony_id: string;
  public_key: Record<string, unknown>;
};

export function decodeBase64Url(value: string): ArrayBuffer {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0)).buffer;
}

export function encodeBase64Url(value: ArrayBuffer | null): string | null {
  if (value === null) return null;
  const bytes = new Uint8Array(value);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function resolvePasskeyApiBase() {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (configured?.startsWith("/")) return configured;
  if (typeof window !== "undefined" && configured) {
    try {
      const parsed = new URL(configured);
      if (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1") {
        return `${window.location.protocol}//${window.location.hostname}:${parsed.port || "8000"}`;
      }
    } catch {
      return configured;
    }
    return configured;
  }
  return configured ?? "/backend";
}

export function passkeysSupported() {
  return typeof window !== "undefined" && "PublicKeyCredential" in window && !!navigator.credentials;
}

export async function conditionalPasskeysSupported() {
  if (!passkeysSupported() || !PublicKeyCredential.isConditionalMediationAvailable) return false;
  return PublicKeyCredential.isConditionalMediationAvailable();
}

function creationOptions(payload: Record<string, unknown>): PublicKeyCredentialCreationOptions {
  const user = payload.user as { id: string };
  const excluded = payload.excludeCredentials as Array<{ id: string }> | undefined;
  return {
    ...payload,
    challenge: decodeBase64Url(payload.challenge as string),
    user: { ...user, id: decodeBase64Url(user.id) },
    excludeCredentials: excluded?.map((credential) => ({
      ...credential,
      id: decodeBase64Url(credential.id),
    })),
  } as PublicKeyCredentialCreationOptions;
}

function requestOptions(payload: Record<string, unknown>): PublicKeyCredentialRequestOptions {
  const allowed = payload.allowCredentials as Array<{ id: string }> | undefined;
  return {
    ...payload,
    challenge: decodeBase64Url(payload.challenge as string),
    allowCredentials: allowed?.map((credential) => ({
      ...credential,
      id: decodeBase64Url(credential.id),
    })),
  } as PublicKeyCredentialRequestOptions;
}

function credentialJson(credential: PublicKeyCredential): Record<string, unknown> {
  const nativeJson = (credential as PublicKeyCredential & { toJSON?: () => Record<string, unknown> }).toJSON;
  if (nativeJson) return nativeJson.call(credential);

  const response = credential.response;
  const base = {
    id: credential.id,
    rawId: encodeBase64Url(credential.rawId),
    type: credential.type,
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
  };
  if (response instanceof AuthenticatorAttestationResponse) {
    return {
      ...base,
      response: {
        clientDataJSON: encodeBase64Url(response.clientDataJSON),
        attestationObject: encodeBase64Url(response.attestationObject),
        transports: response.getTransports?.() ?? [],
      },
    };
  }
  const assertion = response as AuthenticatorAssertionResponse;
  return {
    ...base,
    response: {
      clientDataJSON: encodeBase64Url(assertion.clientDataJSON),
      authenticatorData: encodeBase64Url(assertion.authenticatorData),
      signature: encodeBase64Url(assertion.signature),
      userHandle: encodeBase64Url(assertion.userHandle),
    },
  };
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${resolvePasskeyApiBase()}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string };
    throw new Error(payload.detail || "Passkey request failed");
  }
  return response.json() as Promise<T>;
}

export async function authenticateWithPasskey(
  mediation: "conditional" | "optional" = "optional",
  signal?: AbortSignal,
) {
  const options = await apiJson<PasskeyOptions>("/api/auth/passkeys/login/options", { method: "POST" });
  const credential = await navigator.credentials.get({
    publicKey: requestOptions(options.public_key),
    mediation: mediation as CredentialMediationRequirement,
    signal,
  }) as PublicKeyCredential | null;
  if (!credential) throw new DOMException("Passkey selection was cancelled", "NotAllowedError");
  return apiJson<{ access_token: string; refresh_token?: string; user: { full_name: string } }>(
    "/api/auth/passkeys/login/verify",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ceremony_id: options.ceremony_id, credential: credentialJson(credential) }),
    },
  );
}

export async function createPasskey(token: string, name: string) {
  const options = await apiJson<PasskeyOptions>("/api/auth/passkeys/register/options", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  const credential = await navigator.credentials.create({
    publicKey: creationOptions(options.public_key),
  }) as PublicKeyCredential | null;
  if (!credential) throw new DOMException("Passkey creation was cancelled", "NotAllowedError");
  return apiJson<PasskeyRecord>("/api/auth/passkeys/register/verify", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ ceremony_id: options.ceremony_id, credential: credentialJson(credential), name }),
  });
}

export function listPasskeys(token: string) {
  return apiJson<PasskeyRecord[]>("/api/auth/passkeys", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function renamePasskey(token: string, id: number, name: string) {
  return apiJson<PasskeyRecord>(`/api/auth/passkeys/${id}`, {
    method: "PATCH",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

export async function removePasskey(token: string, id: number) {
  const response = await fetch(`${resolvePasskeyApiBase()}/api/auth/passkeys/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) throw new Error("Passkey could not be removed");
}
