export type AdminAutomationConnectionPendingAuth = {
  active: boolean;
  authUrl: string;
  redirectUri: string;
  startedAt: string;
  error?: string | null;
};

export type AdminAutomationConnection = {
  credentialsPresent: boolean;
  tokenPresent: boolean;
  connected: boolean;
  credentialsPath: string;
  tokenPath: string;
  detail: string;
  setupDocPath: string;
  pendingAuth?: AdminAutomationConnectionPendingAuth;
};

export type AdminAutomationInfo = {
  key: string;
  name: string;
  frequencyMinutes: number;
  isLong: boolean;
  launchCount: number;
  lastLaunch: string | null;
  attemptCount?: number;
  successCount?: number;
  failureCount?: number;
  skipCount?: number;
  lastStatus?: string | null;
  lastStartedAt?: string | null;
  lastFinishedAt?: string | null;
  lastDurationSeconds?: number | null;
  lastError?: string | null;
  lastSuccessAt?: string | null;
  enabled: boolean;
  authRequired: boolean;
  defaultEnabled: boolean;
  connection?: AdminAutomationConnection;
};

export type AdminAutomationsResponse = {
  automations: AdminAutomationInfo[];
  configPath?: string;
  error?: string;
};

export type AdminRunResult = {
  name: string;
  startedAt: string;
  finishedAt: string;
  durationSeconds: number;
  output: string;
  taskDelegations: unknown;
  status?: string;
  error?: string | null;
};

export type AdminRunAllResult = {
  results: AdminRunResult[];
  summary?: {
    completed: number;
    failed: number;
    skipped: number;
  };
};

export type AdminJob = {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "failed";
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  result: unknown;
  error: string | null;
};

export type AdminJobStartResponse = {
  jobId: string;
  status?: string;
  detail?: string | null;
};

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

export type AdminGmailAutomationStatus = AdminAutomationConnection & {
  authUrl?: string;
  redirectUri?: string;
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

export async function getAdminAutomations(): Promise<AdminAutomationsResponse> {
  return requestJson<AdminAutomationsResponse>("/api/admin/automations", undefined, "Failed to load automations");
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

export async function getAdminJob(jobId: string): Promise<AdminJob> {
  return requestJson<AdminJob>(`/api/admin/jobs/${encodeURIComponent(jobId)}`, undefined, "Job lookup failed");
}

export async function startAdminAutomation(name: string): Promise<AdminJobStartResponse> {
  const payload = await requestJson<AdminJobStartResponse>(
    `/api/admin/automations/run_async?name=${encodeURIComponent(name)}`,
    { method: "POST" },
    "Failed to start automation job"
  );
  if (!payload.jobId) {
    throw new Error(payload.detail ?? "Failed to start automation job");
  }
  return payload;
}

export async function startAllAdminAutomations(): Promise<AdminJobStartResponse> {
  const payload = await requestJson<AdminJobStartResponse>(
    "/api/admin/automations/run_all_async",
    { method: "POST" },
    "Failed to start automation job"
  );
  if (!payload.jobId) {
    throw new Error(payload.detail ?? "Failed to start automation job");
  }
  return payload;
}

export async function setAdminAutomationEnabled(key: string, enabled: boolean): Promise<AdminAutomationsResponse> {
  return requestJson<AdminAutomationsResponse>(
    `/api/admin/automations/${encodeURIComponent(key)}/enabled`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled })
    },
    "Failed to update automation"
  );
}

export async function connectAdminGmailAutomation(): Promise<AdminGmailAutomationStatus> {
  return requestJson<AdminGmailAutomationStatus>(
    "/api/admin/automations/gmail/connect",
    { method: "POST" },
    "Failed to connect Gmail"
  );
}

export async function disconnectAdminGmailAutomation(): Promise<AdminGmailAutomationStatus> {
  return requestJson<AdminGmailAutomationStatus>(
    "/api/admin/automations/gmail/connect",
    { method: "DELETE" },
    "Failed to disconnect Gmail"
  );
}
