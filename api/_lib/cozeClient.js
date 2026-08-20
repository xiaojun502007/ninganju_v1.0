function normalizeAreas(value) {
  if (!value || !Array.isArray(value.areas) || value.areas.length !== 4) {
    return null;
  }

  const areas = value.areas.map((area, index) => {
    const name = String(area.name || area.areaName || "").trim();
    const tagline = String(area.tagline || area.tagLine || area.subtitle || "片区适配度较高").trim();
    const reason = String(area.reason || "").trim();
    const risk = String(area.risk || "").trim();
    const tags = Array.isArray(area.tags) ? area.tags.map(String).slice(0, 4) : [];
    if (!name || !reason || !risk || tags.length === 0) {
      return null;
    }
    return {
      id: String(index + 1).padStart(2, "0"),
      name,
      tagline,
      reason,
      risk,
      tags,
      source: "coze"
    };
  });

  return areas.every(Boolean) ? areas : null;
}

function extractWorkflowJson(payload) {
  function parseCandidate(candidate, depth = 0) {
    if (depth > 4) return null;
    if (candidate && typeof candidate === "object" && Array.isArray(candidate.areas)) {
      return candidate;
    }
    if (candidate && typeof candidate === "object") {
      for (const key of ["data", "output", "content"]) {
        const nested = parseCandidate(candidate[key], depth + 1);
        if (nested) return nested;
      }
    }
    if (typeof candidate === "string") {
      try {
        const parsed = JSON.parse(candidate);
        return parseCandidate(parsed, depth + 1);
      } catch {
        return null;
      }
    }
    return null;
  }

  return parseCandidate(payload);
}

export async function runRecommendWorkflow(preference, markdownPrompt) {
  const token = process.env.COZE_API_TOKEN;
  const workflowId = process.env.COZE_RECOMMEND_WORKFLOW_ID || "7640105893560958985";
  if (!token) {
    return null;
  }

  const requestBody = {
    workflow_id: workflowId,
    parameters: {
      markdown_prompt: markdownPrompt
    }
  };
  if (process.env.COZE_APP_ID) {
    requestBody.app_id = process.env.COZE_APP_ID;
  }

  const baseUrl = (process.env.COZE_BASE_URL || "https://api.coze.cn").replace(/\/$/, "");
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);

  let response;
  try {
    response = await fetch(`${baseUrl}/v1/workflow/run`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(requestBody),
      signal: controller.signal
    });
  } finally {
    clearTimeout(timeoutId);
  }

  if (!response.ok) {
    return null;
  }

  const raw = await response.json();
  const workflowJson = extractWorkflowJson(raw);
  const areas = normalizeAreas(workflowJson);
  return areas ? { areas, raw } : null;
}
