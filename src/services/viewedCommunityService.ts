import type { CommuteLocation } from "./commuteService";

export type ViewedCommunityRecord = {
  username: string;
  preferenceId: string;
  areaName: string;
  areaLocation: CommuteLocation | null;
  viewedAt: string;
};

const STORAGE_PREFIX = "ninganju_last_viewed_community:";

function isValidRecord(value: unknown, username: string): value is ViewedCommunityRecord {
  if (!value || typeof value !== "object") return false;
  const record = value as Partial<ViewedCommunityRecord>;
  const location = record.areaLocation;
  return record.username === username &&
    typeof record.preferenceId === "string" && record.preferenceId.length > 0 &&
    typeof record.areaName === "string" && record.areaName.length > 0 &&
    (location === null || (!!location && Number.isFinite(location.lng) && Number.isFinite(location.lat) &&
    location.lng >= -180 && location.lng <= 180 && location.lat >= -90 && location.lat <= 90));
}

export function saveLastViewedCommunity(record: ViewedCommunityRecord): void {
  if (typeof window === "undefined" || !isValidRecord(record, record.username)) return;
  try {
    window.localStorage.setItem(`${STORAGE_PREFIX}${record.username}`, JSON.stringify(record));
  } catch {
    // The in-memory App state still supports returning to the last viewed page.
  }
}

export function readLastViewedCommunity(username: string): ViewedCommunityRecord | null {
  if (typeof window === "undefined" || !username) return null;
  try {
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${username}`);
    if (!raw) return null;
    const record: unknown = JSON.parse(raw);
    return isValidRecord(record, username) ? record : null;
  } catch {
    return null;
  }
}
