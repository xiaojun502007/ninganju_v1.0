export type ProfilePreference = {
  workAddress: string;
  budgetMin: number;
  budgetMax: number;
  commuteDistanceMin: number;
  commuteDistanceMax: number;
  transportPreference: string;
  housingType: string;
  facilityPreferences: string[];
  createdAt: string;
};

export type ProfileData = {
  success: boolean;
  username: string;
  latestPreference: ProfilePreference | null;
  stats: {
    recommendationCount: number;
    detailViewCount: number;
    savedCommunityCount: number;
    lastUsedAt: string | null;
  };
  message?: string;
};

const LOCAL_API_BASE_URL = "http://127.0.0.1:8787";

function getApiBaseUrl() {
  if (typeof window === "undefined") return "";
  return new Set(["127.0.0.1", "localhost"]).has(window.location.hostname) ? LOCAL_API_BASE_URL : "";
}

async function postProfile<T extends { success: boolean; message?: string }>(path: string, token: string, body: unknown): Promise<T> {
  if (!token) throw new Error("登录状态已失效，请重新登录");
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: JSON.stringify(body)
  });
  const data = (await response.json()) as T;
  if (!response.ok || !data.success) throw new Error(data.message || "个人信息请求失败，请稍后重试");
  return data;
}

export function getProfile(token: string) {
  return postProfile<ProfileData>("/api/profile", token, {});
}

export async function recordDetailView(token: string, preferenceId: string, areaName: string) {
  await postProfile<{ success: boolean }>("/api/profile/detail-view", token, { preferenceId, areaName });
}
