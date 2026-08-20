export type CommuteRangeValue = "3km" | "5km" | "10km" | "15km" | "15km+";

export type PriorityValue = "靠近工作地" | "靠近地铁站" | "周边生活便利" | "居住品质高";

export type RecommendationPreference = {
  workAddress: string;
  budgetMin: number;
  budgetMax: number;
  commuteRange: CommuteRangeValue;
  priority: PriorityValue;
};

export type RecommendedArea = {
  id?: string;
  name: string;
  tagline: string;
  reason: string;
  risk: string;
  tags: string[];
  source?: "fallback" | "coze" | "local_sample";
};

export type RecommendAreasResponse = {
  success: boolean;
  preferenceId: string;
  areas: RecommendedArea[];
  message?: string;
  source?: "fallback" | "coze" | "local_sample";
};

export type RecommendationHistoryRecord = {
  id: string;
  createdAt: string;
  preference: RecommendationPreference;
  preferenceId: string;
  areas: RecommendedArea[];
};
