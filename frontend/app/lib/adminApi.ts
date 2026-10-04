export type AdminApiTokenStatus = {
  configured: boolean;
  masked: string;
  envPath: string;
};

export type AdminApiTokenSaveResponse = AdminApiTokenStatus & {
  validated?: boolean;
  labelsCount?: number | null;
};

export type AdminTimezoneStatus = {
  configured: boolean;
  timezone: string;
  source: "system" | "env";
  override: string | null;
  overrideValid: boolean;
  system: string;
  envPath: string;
  invalidOverride?: string;
};

async function readJson<T>(res: Response): Promise<T> {
  const text = await res.text();
  if (!text) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    const snippet = text.trim();
    const summary = snippet.length > 200 ? `${snippet.slice(0, 200)}...` : snippet;
    throw new Error(summary ? `Invalid JSON response: ${summary}` : "Invalid JSON response");
  }
}

function errorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    const error = (payload as { error?: unknown }).error;
    if (typeof error === "string" && error.trim()) return error;
  }
  return fallback;
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit, fallbackError = "Request failed"): Promise<T> {
  const res = await fetch(input, init);
  const payload = await readJson<T>(res);
  if (!res.ok) {
    throw new Error(errorMessage(payload, `${fallbackError} (${res.status})`));
  }
  return payload;
}

export async function getAdminApiTokenStatus(): Promise<AdminApiTokenStatus> {
  return requestJson<AdminApiTokenStatus>("/api/admin/api_token", undefined, "Failed to load API token status");
}

export async function saveAdminApiToken(token: string): Promise<AdminApiTokenSaveResponse> {
  const payload = await requestJson<AdminApiTokenSaveResponse>(
    "/api/admin/api_token",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token, validate: true })
    },
    "Failed to save token"
  );
  return payload;
}

export async function clearAdminApiToken(): Promise<AdminApiTokenStatus> {
  return requestJson<AdminApiTokenStatus>("/api/admin/api_token", { method: "DELETE" }, "Failed to clear token");
}

export async function getAdminTimezoneStatus(): Promise<AdminTimezoneStatus> {
  return requestJson<AdminTimezoneStatus>("/api/admin/timezone", undefined, "Failed to load timezone");
}

export async function saveAdminTimezone(timezone: string): Promise<AdminTimezoneStatus> {
  return requestJson<AdminTimezoneStatus>(
    "/api/admin/timezone",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ timezone })
    },
    "Failed to save timezone"
  );
}

export async function clearAdminTimezone(): Promise<AdminTimezoneStatus> {
  return requestJson<AdminTimezoneStatus>("/api/admin/timezone", { method: "DELETE" }, "Failed to clear timezone");
}
