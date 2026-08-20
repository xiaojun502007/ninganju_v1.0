function hasSupabaseEnv() {
  return Boolean(process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_ROLE_KEY);
}

async function postgrestInsert(tableName, row) {
  if (!hasSupabaseEnv()) {
    return null;
  }

  const response = await fetch(`${process.env.SUPABASE_URL}/rest/v1/${tableName}`, {
    method: "POST",
    headers: {
      apikey: process.env.SUPABASE_SERVICE_ROLE_KEY,
      Authorization: `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
      "Content-Type": "application/json",
      Prefer: "return=representation"
    },
    body: JSON.stringify(row)
  });

  if (!response.ok) {
    return null;
  }

  const data = await response.json();
  return Array.isArray(data) ? data[0] : data;
}

export async function savePreference(row) {
  return postgrestInsert("rent_preference", row);
}

export async function saveRecommendationResult(row) {
  return postgrestInsert("recommendation_result", row);
}
