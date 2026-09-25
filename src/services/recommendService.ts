import type {
  RentDemandJson,
  RecommendAreasResponse,
  RecommendationHistoryRecord,
  RecommendationPreference
} from "../types/recommendation";

const LOCAL_API_BASE_URL = "http://127.0.0.1:8787";
const HISTORY_STORAGE_KEY = "ninganju_recommendation_history";

function getApiBaseUrl() {
  if (typeof window === "undefined") {
    return "";
  }
  const localHosts = new Set(["127.0.0.1", "localhost"]);
  return localHosts.has(window.location.hostname) ? LOCAL_API_BASE_URL : "";
}

export async function recommendAreas(preference: RentDemandJson) {
  const response = await fetch(`${getApiBaseUrl()}/api/recommend-areas`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(preference)
  });

  const data = (await response.json()) as RecommendAreasResponse;
  if (!response.ok || !data.success) {
    throw new Error(data.message || "推荐生成失败，请稍后重试");
  }
  return data;
}

export function readRecommendationHistory(): RecommendationHistoryRecord[] {
  if (typeof window === "undefined") {
    return [];
  }
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const records = JSON.parse(raw) as RecommendationHistoryRecord[];
    return Array.isArray(records) ? records : [];
  } catch {
    return [];
  }
}

export function saveRecommendationHistory(record: RecommendationHistoryRecord) {
  if (typeof window === "undefined") {
    return;
  }
  const records = readRecommendationHistory();
  const nextRecords = [record, ...records.filter((item) => item.id !== record.id)].slice(0, 20);
  window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(nextRecords));
}
