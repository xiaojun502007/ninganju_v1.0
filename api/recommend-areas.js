import { runRecommendWorkflow } from "./_lib/cozeClient.js";
import { fallbackAreas } from "./_lib/fallbackAreas.js";
import { buildRecommendPrompt } from "./_lib/markdownPrompt.js";
import { savePreference, saveRecommendationResult } from "./_lib/supabaseAdmin.js";

function validatePreference(body) {
  const workAddress = String(body?.workAddress || "").trim();
  const budgetMin = Number(body?.budgetMin);
  const budgetMax = Number(body?.budgetMax);
  const commuteRange = String(body?.commuteRange || "").trim();
  const priority = String(body?.priority || "").trim();

  if (!workAddress) return [null, "请填写工作地址"];
  if (!Number.isFinite(budgetMin) || !Number.isFinite(budgetMax) || budgetMax <= budgetMin) {
    return [null, "请填写有效的月租预算区间"];
  }
  if (!["3km", "5km", "10km", "15km", "15km+"].includes(commuteRange)) {
    return [null, "请选择可接受通勤距离"];
  }
  if (!["靠近工作地", "靠近地铁站", "周边生活便利", "居住品质高"].includes(priority)) {
    return [null, "请选择租房最看重因素"];
  }

  return [{ workAddress, budgetMin, budgetMax, commuteRange, priority }, null];
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.status(405).json({ success: false, message: "Method Not Allowed" });
    return;
  }

  const [preference, error] = validatePreference(req.body);
  if (error) {
    res.status(400).json({ success: false, message: error });
    return;
  }

  const preferenceId = crypto.randomUUID();
  const markdownPrompt = buildRecommendPrompt(preference);
  const createdAt = new Date().toISOString();

  await savePreference({
    id: preferenceId,
    work_address: preference.workAddress,
    budget_min: preference.budgetMin,
    budget_max: preference.budgetMax,
    commute_range: preference.commuteRange,
    priority: preference.priority,
    markdown_prompt: markdownPrompt,
    created_at: createdAt
  });

  const cozeResult = await runRecommendWorkflow(preference, markdownPrompt);
  const areas = cozeResult?.areas || fallbackAreas;
  const source = cozeResult?.areas ? "coze" : "fallback";

  await saveRecommendationResult({
    id: crypto.randomUUID(),
    preference_id: preferenceId,
    areas_json: areas,
    raw_response: cozeResult?.raw || null,
    source,
    created_at: new Date().toISOString()
  });

  res.status(200).json({
    success: true,
    preferenceId,
    areas,
    source
  });
}
