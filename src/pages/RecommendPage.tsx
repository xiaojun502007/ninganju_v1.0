import { useMemo, useRef, useState } from "react";
import { recommendAreas, saveRecommendationHistory } from "../services/recommendService";
import type {
  CommuteRangeValue,
  PriorityValue,
  RecommendedArea,
  RecommendationPreference
} from "../types/recommendation";

type RecommendPageProps = {
  onOpenAnalysis: (preferenceId?: string, areaName?: string) => void;
};

type ProgressStatus = "idle" | "saving" | "generating" | "done";

const commuteOptions: Array<{ label: string; value: CommuteRangeValue }> = [
  { label: "3km以内", value: "3km" },
  { label: "5km以内", value: "5km" },
  { label: "10km以内", value: "10km" },
  { label: "15km以内", value: "15km" },
  { label: "15km以上", value: "15km+" }
];

const priorityOptions: Array<{ label: PriorityValue; icon: string }> = [
  { label: "靠近工作地", icon: "work" },
  { label: "靠近地铁站", icon: "subway" },
  { label: "周边生活便利", icon: "cart" },
  { label: "居住品质高", icon: "building" }
];

const badgeColors = ["orange", "green", "blue", "green"];

export function RecommendPage({ onOpenAnalysis }: RecommendPageProps) {
  const [workAddress, setWorkAddress] = useState("");
  const [budgetMin, setBudgetMin] = useState(1500);
  const [budgetMax, setBudgetMax] = useState(2800);
  const [commuteRange, setCommuteRange] = useState<CommuteRangeValue>("5km");
  const [priority, setPriority] = useState<PriorityValue>("靠近工作地");
  const [areas, setAreas] = useState<RecommendedArea[]>([]);
  const [progress, setProgress] = useState<ProgressStatus>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [resultMessage, setResultMessage] = useState("");
  const [resultSource, setResultSource] = useState<"local_sample" | "coze" | "fallback">("local_sample");
  const [currentPreferenceId, setCurrentPreferenceId] = useState("");
  const progressTimer = useRef<number | undefined>(undefined);

  const isLoading = progress === "saving" || progress === "generating";

  const preference = useMemo<RecommendationPreference>(
    () => ({
      workAddress: workAddress.trim(),
      budgetMin,
      budgetMax,
      commuteRange,
      priority
    }),
    [budgetMax, budgetMin, commuteRange, priority, workAddress]
  );

  const validatePreference = () => {
    if (!preference.workAddress) {
      return "请先输入工作地址";
    }
    if (preference.budgetMin < 0 || preference.budgetMax <= preference.budgetMin) {
      return "请确认月租预算区间有效";
    }
    return "";
  };

  const handleSubmit = async () => {
    const validationError = validatePreference();
    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    setErrorMessage("");
    setResultMessage("");
    setProgress("saving");
    window.clearTimeout(progressTimer.current);
    progressTimer.current = window.setTimeout(() => setProgress("generating"), 450);

    try {
      const result = await recommendAreas(preference);
      const normalizedAreas = result.areas.map((area, index) => ({
        ...area,
        id: area.id || String(index + 1).padStart(2, "0")
      }));
      setAreas(normalizedAreas);
      setResultSource(result.source || "fallback");
      setResultMessage(result.message || "");
      setCurrentPreferenceId(result.preferenceId);
      setProgress("done");
      saveRecommendationHistory({
        id: `${result.preferenceId}-${Date.now()}`,
        createdAt: new Date().toISOString(),
        preference,
        preferenceId: result.preferenceId,
        areas: normalizedAreas
      });
    } catch (error) {
      setProgress("idle");
      setErrorMessage(error instanceof Error ? error.message : "推荐生成失败，请稍后重试");
    } finally {
      window.clearTimeout(progressTimer.current);
    }
  };

  const updateBudgetMin = (value: number) => {
    setBudgetMin(Math.min(value, budgetMax - 100));
  };

  const updateBudgetMax = (value: number) => {
    setBudgetMax(Math.max(value, budgetMin + 100));
  };

  return (
    <section className="recommend-page">
      <div className="recommend-top">
        <section className="preference-card">
          <div className="card-heading">
            <span className="heading-icon clipboard" />
            <h1>填写租房偏好</h1>
          </div>

          <div className="form-line">
            <span className="num">1.</span>
            <span className="mini-icon location" />
            <strong>工作地址</strong>
            <label className="wide-input">
              <input
                onChange={(event) => setWorkAddress(event.target.value)}
                placeholder="请输入工作地址：如：东南大学（四牌楼校区）"
                value={workAddress}
              />
              <span className="input-icon map" />
            </label>
          </div>

          <div className="form-line budget-line">
            <span className="num">2.</span>
            <span className="mini-icon money" />
            <strong>月租金预算</strong>
            <div className="budget-content">
              <div className="budget-value">
                {budgetMin} - {budgetMax} <span>元/月</span>
              </div>
              <div className="range-control" aria-label="月租金预算">
                <div className="slider">
                  <span
                    className="slider-active"
                    style={{
                      left: `${(budgetMin / 4000) * 100}%`,
                      width: `${((budgetMax - budgetMin) / 4000) * 100}%`
                    }}
                  />
                </div>
                <input
                  aria-label="最低预算"
                  max={4000}
                  min={0}
                  onChange={(event) => updateBudgetMin(Number(event.target.value))}
                  step={100}
                  type="range"
                  value={budgetMin}
                />
                <input
                  aria-label="最高预算"
                  max={4000}
                  min={0}
                  onChange={(event) => updateBudgetMax(Number(event.target.value))}
                  step={100}
                  type="range"
                  value={budgetMax}
                />
              </div>
              <div className="slider-scale">
                <span>0</span>
                <span>1500</span>
                <span>2800</span>
                <span>4000</span>
              </div>
            </div>
          </div>

          <div className="form-line">
            <span className="num">3.</span>
            <span className="mini-icon transit" />
            <strong>接受的通勤距离</strong>
            <div className="pill-group">
              {commuteOptions.map((option) => (
                <button
                  className={commuteRange === option.value ? "selected" : ""}
                  key={option.value}
                  onClick={() => setCommuteRange(option.value)}
                  type="button"
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <div className="form-line priority-line">
            <span className="num">4.</span>
            <span className="mini-icon star" />
            <strong>租房最看重什么</strong>
            <div className="priority-options">
              {priorityOptions.map((option) => (
                <button
                  className={priority === option.label ? "selected" : ""}
                  key={option.label}
                  onClick={() => setPriority(option.label)}
                  type="button"
                >
                  <i className={`option-icon ${option.icon}`} />
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {errorMessage && <p className="auth-message error recommend-error">{errorMessage}</p>}

          <button className="generate-button" disabled={isLoading} onClick={handleSubmit} type="button">
            {progress === "saving" && "正在保存偏好..."}
            {progress === "generating" && "智能推荐生成中..."}
            {(progress === "idle" || progress === "done") && "生成推荐片区"}
          </button>
        </section>

        <section className="recommend-visual">
          <div className="scene-banner">
            <div className="city-water small" />
          </div>
          <div className="progress-panel">
            <h2>推荐进度</h2>
            <div className="progress-steps">
              <ProgressStep active={progress !== "idle"} icon="pin" label="正在解析工作地址" />
              <ProgressStep active={progress === "saving" || progress === "generating" || progress === "done"} icon="clipboard" label="正在保存租房偏好" />
              <ProgressStep active={progress === "generating" || progress === "done"} icon="spark" label="正在进行智能推荐" />
              <ProgressStep active={progress === "done"} icon="check" label="推荐完成" />
            </div>
          </div>
        </section>
      </div>

      <section className="results-panel">
        <div className="results-title">
          <span className="title-line" />
          <span className="thumb-icon" />
          <h2>推荐结果</h2>
        </div>

        {areas.length > 0 && (
          <>
            {resultSource !== "coze" && resultMessage && (
              <p className="auth-message error recommend-error">{resultMessage}</p>
            )}
            <div className="area-card-grid">
              {areas.map((area, index) => (
                <article className="result-card" key={`${area.name}-${index}`}>
                  <div className={`number-badge ${badgeColors[index] || "orange"}`}>{area.id || String(index + 1).padStart(2, "0")}</div>
                  <div className="result-title-row">
                    <span className={`pin-dot ${badgeColors[index] || "orange"}`} />
                    <div>
                      <h3>{area.name}</h3>
                      <p>{area.tagline}</p>
                    </div>
                  </div>
                  <p className="reason">
                    <strong>推荐理由：</strong>
                    {area.reason}
                  </p>
                  <p className="risk">
                    <strong>风险提示：</strong>
                    {area.risk}
                  </p>
                  <div className="tag-list">
                    {area.tags.map((tag) => (
                      <span key={tag}>{tag}</span>
                    ))}
                  </div>
                  <button
                    className="detail-button"
                    onClick={() => onOpenAnalysis(currentPreferenceId, area.name)}
                    type="button"
                  >
                    查看详情
                  </button>
                </article>
              ))}
            </div>

            <p className="result-note">
              {resultSource === "coze"
                ? "以上推荐由扣子工作流根据您的偏好生成，仅解释片区适配理由，不展示具体房源；建议结合实地考察综合选择。"
                : "以上推荐基于演示样本生成，仅解释片区适配理由，不展示具体房源；真实工作流不可用时会自动使用演示推荐结果。"}
            </p>
          </>
        )}
      </section>
    </section>
  );
}

function ProgressStep({ icon, label, active = false }: { icon: string; label: string; active?: boolean }) {
  return (
    <article className={active ? "active" : ""}>
      <span className={`progress-icon ${icon}`} />
      <p>{label}</p>
    </article>
  );
}
