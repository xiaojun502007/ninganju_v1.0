import type { RentContext } from "../services/commuteService";

export function calculateRentOverlapScore(context?: RentContext | null) {
  if (!context) return null;
  const { budgetMin, budgetMax, rentMin, rentMax } = context;
  if (rentMin == null || rentMax == null ||
      ![budgetMin, budgetMax, rentMin, rentMax].every(Number.isFinite) ||
      budgetMax <= budgetMin || rentMax < rentMin) return null;

  const overlap = Math.max(0, Math.min(budgetMax, rentMax) - Math.max(budgetMin, rentMin));
  const overlapRatio = rentMin === rentMax && rentMin >= budgetMin && rentMin <= budgetMax
    ? 1
    : overlap / (budgetMax - budgetMin);
  const score = overlapRatio <= 0.3 ? 60
    : overlapRatio <= 0.5 ? 70
    : overlapRatio <= 0.65 ? 80
    : overlapRatio <= 0.8 ? 90
    : 100;
  return { score, overlapRatio };
}

export function calculateRentFitScore(commuteScore?: number, facilityScore?: number | null, rentScore?: number | null) {
  if (commuteScore == null || facilityScore == null || rentScore == null) return null;
  return Math.round(commuteScore * 0.4 + facilityScore * 0.3 + rentScore * 0.3);
}
