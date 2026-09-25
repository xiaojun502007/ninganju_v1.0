const LOCAL_API_BASE_URL = "http://127.0.0.1:8787";

export type AdminMetricSummary = {
  siteVisits: number;
  newRegistrations: number;
  areaEvaluations: number;
  detailViews: number;
  workflowCalls: number;
  amapApiCalls: number;
};

export type RecentLoginItem = {
  id: number;
  username: string;
  recommendationCount: number;
  loginTime: string;
};

export type VisitTrendItem = {
  date: string;
  label: string;
  value: number;
};

export type TopAreaItem = {
  rank: number;
  name: string;
  count: number;
};

export type AdminDashboardData = {
  success: boolean;
  todayMetrics: AdminMetricSummary;
  recentLogins: RecentLoginItem[];
  visitTrend: VisitTrendItem[];
  topAreas: TopAreaItem[];
  updatedAt: string;
  topAreaResetAt?: string;
  message?: string;
};

function getApiBaseUrl() {
  if (typeof window === "undefined") {
    return "";
  }
  return new Set(["127.0.0.1", "localhost"]).has(window.location.hostname) ? LOCAL_API_BASE_URL : "";
}

export async function getAdminDashboardData() {
  const response = await fetch(`${getApiBaseUrl()}/api/admin-dashboard`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({})
  });

  const data = (await response.json()) as AdminDashboardData;
  if (!response.ok || !data.success) {
    throw new Error(data.message || "运营数据读取失败，请稍后重试");
  }
  return data;
}

export async function recalculateTopAreas() {
  const response = await fetch(`${getApiBaseUrl()}/api/admin-dashboard/recalculate-top-areas`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({})
  });

  const data = (await response.json()) as { success: boolean; message?: string; topAreaResetAt?: string };
  if (!response.ok || !data.success) {
    throw new Error(data.message || "片区推荐统计重置失败，请稍后重试");
  }
  return data;
}
