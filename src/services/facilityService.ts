import type { CommuteLocation } from "./commuteService";

export type FacilitySummaryItem = {
  key: string;
  facilityName: string;
  count: number;
  score: number;
  nearestDistance: number | null;
  examples: string[];
};

export type FacilityData = {
  success: boolean;
  areaLocation: CommuteLocation | null;
  poiSummary: FacilitySummaryItem[];
  rawPoiCount: number;
  recommendationReason?: string;
  message?: string;
};

const LOCAL_API_BASE_URL = "http://127.0.0.1:8787";

function getApiBaseUrl() {
  if (typeof window === "undefined") {
    return "";
  }
  return new Set(["127.0.0.1", "localhost"]).has(window.location.hostname) ? LOCAL_API_BASE_URL : "";
}

export async function getFacilityData(
  preferenceId: string,
  areaName: string,
  areaLocation: CommuteLocation | null
) {
  const response = await fetch(`${getApiBaseUrl()}/api/facilities`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ preferenceId, areaName, areaLocation })
  });

  const data = (await response.json()) as FacilityData;
  if (!response.ok || !data.success) {
    throw new Error(data.message || "生活圈设施数据生成失败，请稍后重试");
  }
  return data;
}
