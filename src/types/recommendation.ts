export type CommuteRangeValue = "3km" | "5km" | "10km" | "15km" | "15km+";

export type PriorityValue = "靠近工作地" | "靠近地铁站" | "周边生活便利" | "居住品质高";

export type RecommendationPreference = {
  workAddress: string;
  budgetMin: number;
  budgetMax: number;
  commuteRange: CommuteRangeValue;
  priority: PriorityValue;
};

export type RentDemandJson = {
  user_nickname: string;
  work_address: string;
  budget_max: number;
  budget_min: number;
  commute_distance_max: number;
  commute_distance_min: number;
  facility_preferences: string[];
  transport_preference: string;
  housing_type: string;
};

export type RecommendedArea = {
  id?: string;
  name: string;
  tagline: string;
  reason: string;
  risk: string;
  tags: string[];
  community_id?: string;
  community_name?: string;
  distance_km?: number | null;
  facility_checks?: unknown;
  facility_match?: boolean;
  facility_status?: string;
  facility_tag?: string;
  gcj02_lat?: number | null;
  gcj02_lng?: number | null;
  poi_score?: number | null;
  rank?: number | null;
  rent_max?: number | null;
  rent_median?: number | null;
  rent_min?: number | null;
  strategy?: string;
  tag_source?: string;
  source?: "fallback" | "coze" | "local_sample";
};

export type RecommendationPlans = {
  commute: RecommendedArea[];
  balanced: RecommendedArea[];
  cost_effective: RecommendedArea[];
};

export type RecommendAreasResponse = {
  success: boolean;
  preferenceId: string;
  preferenceJson?: RentDemandJson;
  areas: RecommendedArea[];
  plans?: RecommendationPlans;
  workflowSucceeded?: boolean;
  workflowOutput?: unknown;
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
