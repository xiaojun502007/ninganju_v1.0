import type { CommuteLocation, RecommendationAreaBrief } from "./commuteService";

export type EvaluationHistoryOtherInfo = {
  preferenceId?: string;
  areaName?: string;
  recommendationArea?: RecommendationAreaBrief | null;
  areaLocation?: CommuteLocation | null;
  rentScore?: number;
};

export type EvaluationHistoryRecord = {
  id: string;
  username: string;
  regionName: string;
  totalScore: number;
  commuteScore: number;
  facilityScore: number;
  time: string;
  otherInfo: EvaluationHistoryOtherInfo;
};

export type SaveEvaluationHistoryPayload = {
  username: string;
  regionName: string;
  totalScore: number;
  commuteScore: number;
  facilityScore: number;
  otherInfo: EvaluationHistoryOtherInfo;
};

const LOCAL_API_BASE_URL = "http://127.0.0.1:8787";

function getApiBaseUrl() {
  if (typeof window === "undefined") {
    return "";
  }
  return new Set(["127.0.0.1", "localhost"]).has(window.location.hostname) ? LOCAL_API_BASE_URL : "";
}

async function postJson<T>(path: string, payload: unknown) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(payload)
  });

  const data = (await response.json()) as T & { success?: boolean; message?: string };
  if (!response.ok || data.success === false) {
    throw new Error(data.message || "评估历史记录操作失败，请稍后重试");
  }
  return data;
}

export async function saveEvaluationHistory(payload: SaveEvaluationHistoryPayload) {
  const data = await postJson<{ success: boolean; record: EvaluationHistoryRecord }>(
    "/api/evaluation-history/save",
    payload
  );
  return data.record;
}

export async function listEvaluationHistory(username: string) {
  const data = await postJson<{ success: boolean; records: EvaluationHistoryRecord[] }>(
    "/api/evaluation-history/list",
    { username }
  );
  return data.records;
}

export async function deleteEvaluationHistory(username: string, id: string) {
  await postJson<{ success: boolean }>("/api/evaluation-history/delete", { username, id });
}
