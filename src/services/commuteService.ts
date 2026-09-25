export type CommuteLocation = {
  address?: string;
  name?: string;
  lng: number;
  lat: number;
};

export type CommuteSummary = {
  mode: string;
  routeName: string;
  durationMinutes: number | null;
  distanceKm: number | null;
  transferCount: number;
  summary: string;
  polyline?: Array<[number, number]>;
};

export type CommuteScoreResult = {
  commuteScore: number;
  commuteLevel: string;
  commuteTags: string[];
  transitScore: number | null;
  drivingScore: number | null;
  detail: {
    transit?: {
      timeScore: number;
      distanceScore: number;
      transferScore: number;
    } | null;
    driving?: {
      timeScore: number;
      distanceScore: number;
    } | null;
  };
};

export type RecommendationAreaBrief = {
  name: string;
  tagline: string;
  reason: string;
  tags: string[];
};

export type RentContext = {
  budgetMin: number;
  budgetMax: number;
  housingType: string;
  rentMin: number | null;
  rentMax: number | null;
};

export type CommuteData = {
  success: boolean;
  workLocation: CommuteLocation | null;
  areaLocation: CommuteLocation | null;
  commute: CommuteSummary | null;
  commuteScoreResult?: CommuteScoreResult | null;
  recommendationArea?: RecommendationAreaBrief | null;
  rentContext?: RentContext | null;
  message?: string;
};

export type CommuteMode = "driving" | "transit";

const LOCAL_API_BASE_URL = "http://127.0.0.1:8787";

function getApiBaseUrl() {
  if (typeof window === "undefined") {
    return "";
  }
  return new Set(["127.0.0.1", "localhost"]).has(window.location.hostname) ? LOCAL_API_BASE_URL : "";
}

export async function getCommuteData(
  preferenceId: string,
  areaName: string,
  mode: CommuteMode = "driving",
  areaLocation: CommuteLocation | null = null
) {
  const response = await fetch(`${getApiBaseUrl()}/api/commute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ preferenceId, areaName, mode, areaLocation })
  });

  const data = (await response.json()) as CommuteData;
  if (!response.ok || !data.success) {
    throw new Error(data.message || "通勤信息生成失败，请稍后重试");
  }
  return data;
}
