import { useMemo, useState, type ReactNode } from "react";
import { AddressMapPicker } from "../components/AddressMapPicker";
import { RecommendationSidebar } from "../components/layout/RecommendationSidebar";
import { recommendAreas, saveRecommendationHistory } from "../services/recommendService";
import type {
  CommuteRangeValue,
  PriorityValue,
  RentDemandJson,
  RecommendedArea,
  RecommendationPlans,
  RecommendationPreference
} from "../types/recommendation";

type RecommendPageProps = {
  onOpenAnalysis: (preferenceId: string, community: RecommendedArea) => void;
  onOpenLastViewedDetail: () => boolean;
  onOpenProfile: () => void;
  username: string;
};

type ProgressStatus = "idle" | "saving" | "generating" | "done";
type PlanTone = "orange" | "blue" | "green";
type PlanCommunity = {
  id?: string;
  name: string;
  tags: string[];
  facilityMatch?: boolean;
  area: RecommendedArea;
};
type IconName =
  | "user"
  | "pin"
  | "history"
  | "clipboard"
  | "location"
  | "train"
  | "cart"
  | "bag"
  | "utensils"
  | "basket"
  | "tree"
  | "dumbbell"
  | "stadium"
  | "leisure"
  | "hospital"
  | "walk"
  | "bike"
  | "bus"
  | "car"
  | "note"
  | "balance"
  | "coins"
  | "arrow";

const BUDGET_MIN = 500;
const BUDGET_MAX = 4000;
const COMMUTE_MIN = 1;
const COMMUTE_MAX = 30;

const facilityOptions: Array<{ label: string; icon: IconName }> = [
  { label: "地铁站", icon: "train" },
  { label: "商场", icon: "bag" },
  { label: "公园", icon: "tree" },
  { label: "餐厅", icon: "utensils" },
  { label: "医院", icon: "hospital" },
  { label: "运动场", icon: "stadium" },
  { label: "休闲场所", icon: "leisure" }
];

const transportOptions: Array<{ label: string; icon: IconName }> = [
  { label: "步行", icon: "walk" },
  { label: "自行车/电动车", icon: "bike" },
  { label: "公交车", icon: "bus" },
  { label: "地铁", icon: "train" },
  { label: "自驾/打车", icon: "car" }
];

const housingOptions = ["单身公寓", "一居室普通住宅", "两居室普通住宅"];

const planDefaults: Array<{
  title: string;
  tone: PlanTone;
  icon: IconName;
}> = [
  {
    title: "通勤优先方案",
    tone: "orange",
    icon: "train"
  },
  {
    title: "均衡方案",
    tone: "blue",
    icon: "balance"
  },
  {
    title: "性价比优先方案",
    tone: "green",
    icon: "coins"
  }
];

export function RecommendPage({ onOpenAnalysis, onOpenLastViewedDetail, onOpenProfile, username }: RecommendPageProps) {
  const [workAddress, setWorkAddress] = useState("");
  const [budgetMin, setBudgetMin] = useState(1500);
  const [budgetMax, setBudgetMax] = useState(2800);
  const [commuteMin, setCommuteMin] = useState(5);
  const [commuteMax, setCommuteMax] = useState(15);
  const [selectedFacilities, setSelectedFacilities] = useState(["地铁站", "商场", "公园"]);
  const [transportMode, setTransportMode] = useState("地铁");
  const [housingType, setHousingType] = useState("");
  const [areas, setAreas] = useState<RecommendedArea[]>([]);
  const [recommendationPlans, setRecommendationPlans] = useState<RecommendationPlans | null>(null);
  const [progress, setProgress] = useState<ProgressStatus>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [resultMessage, setResultMessage] = useState("");
  const [currentPreferenceId, setCurrentPreferenceId] = useState("");
  const [incompleteMessage, setIncompleteMessage] = useState("");
  const [addressMapOpen, setAddressMapOpen] = useState(false);
  const [historyNotice, setHistoryNotice] = useState("");

  const isLoading = progress === "saving" || progress === "generating";
  const budgetMultiplier = housingType === "两居室普通住宅" ? 2 : 1;
  const commuteRange = useMemo<CommuteRangeValue>(() => {
    if (commuteMax <= 3) return "3km";
    if (commuteMax <= 5) return "5km";
    if (commuteMax <= 10) return "10km";
    if (commuteMax <= 15) return "15km";
    return "15km+";
  }, [commuteMax]);
  const priority: PriorityValue = "靠近工作地";

  const preference = useMemo<RecommendationPreference>(
    () => ({
      workAddress: workAddress.trim(),
      budgetMin: budgetMin * budgetMultiplier,
      budgetMax: budgetMax * budgetMultiplier,
      commuteRange,
      priority
    }),
    [budgetMax, budgetMin, budgetMultiplier, commuteRange, priority, workAddress]
  );

  const rentDemandJson = useMemo<RentDemandJson>(
    () => ({
      user_nickname: username || "xiaoning",
      work_address: workAddress.trim(),
      budget_max: budgetMax * budgetMultiplier,
      budget_min: budgetMin * budgetMultiplier,
      commute_distance_max: commuteMax,
      commute_distance_min: commuteMin,
      facility_preferences: selectedFacilities,
      transport_preference: transportMode,
      housing_type: housingType
    }),
    [budgetMax, budgetMin, budgetMultiplier, commuteMax, commuteMin, housingType, selectedFacilities, transportMode, username, workAddress]
  );

  const displayPlans = recommendationPlans
    ? planDefaults.map((plan, index) => {
        const dynamicCommunities = [
          recommendationPlans.commute,
          recommendationPlans.balanced,
          recommendationPlans.cost_effective
        ][index];
        return {
          ...plan,
          communities: dynamicCommunities.slice(0, 3).map((community) => ({
            id: community.community_id || community.id,
            name: community.community_name || community.name,
            tags: community.tags?.slice(0, 2) || [],
            facilityMatch: Boolean(community.facility_match),
            area: community
          }))
        };
      })
    : [];

  const handleSubmit = async () => {
    const requiredDemandComplete = Boolean(
      rentDemandJson.work_address &&
      rentDemandJson.budget_min >= BUDGET_MIN &&
      rentDemandJson.budget_max > rentDemandJson.budget_min &&
      rentDemandJson.commute_distance_min >= COMMUTE_MIN &&
      rentDemandJson.commute_distance_max > rentDemandJson.commute_distance_min &&
      rentDemandJson.facility_preferences.length > 0 &&
      rentDemandJson.transport_preference &&
      rentDemandJson.housing_type
    );

    if (!requiredDemandComplete) {
      setIncompleteMessage("您还有未填写的租房需求");
      setErrorMessage("");
      return;
    }

    setIncompleteMessage("");
    setHistoryNotice("");
    setErrorMessage("");
    setResultMessage("");
    setAreas([]);
    setRecommendationPlans(null);
    setProgress("saving");

    try {
      setProgress("generating");
      const result = await recommendAreas(rentDemandJson);
      const normalizedAreas = result.areas.map((area, index) => ({
        ...area,
        id: area.id || String(index + 1).padStart(2, "0")
      }));
      setAreas(normalizedAreas);
      setRecommendationPlans(result.plans || null);
      setResultMessage(result.message || "已根据你的需求更新右侧推荐方案");
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
      const message = error instanceof Error ? error.message : "推荐生成失败，请稍后重试";
      setErrorMessage(message);
      setRecommendationPlans(null);
    }
  };

  const handleOpenHistory = () => {
    setHistoryNotice("");
    if (!onOpenLastViewedDetail()) {
      setHistoryNotice("暂无查看过的微社区详情，请先在推荐结果中点击一次“查看方案”");
    }
  };

  const toggleFacility = (label: string) => {
    setSelectedFacilities((current) =>
      current.includes(label) ? current.filter((item) => item !== label) : [...current, label]
    );
  };

  const openPlan = (community: PlanCommunity) => {
    if (!currentPreferenceId) {
      setErrorMessage("请先完善需求并生成推荐片区");
      return;
    }
    const { gcj02_lng: lng, gcj02_lat: lat } = community.area;
    if (typeof lng !== "number" || typeof lat !== "number" ||
        !Number.isFinite(lng) || !Number.isFinite(lat) ||
        lng < -180 || lng > 180 || lat < -90 || lat > 90) {
      setErrorMessage("该微社区缺少有效坐标，暂时无法查看通勤与生活圈分析");
      return;
    }
    onOpenAnalysis(currentPreferenceId, community.area);
  };

  const budgetLeft = ((budgetMin - BUDGET_MIN) / (BUDGET_MAX - BUDGET_MIN)) * 100;
  const budgetWidth = ((budgetMax - budgetMin) / (BUDGET_MAX - BUDGET_MIN)) * 100;
  const commuteLeft = ((commuteMin - COMMUTE_MIN) / (COMMUTE_MAX - COMMUTE_MIN)) * 100;
  const commuteWidth = ((commuteMax - commuteMin) / (COMMUTE_MAX - COMMUTE_MIN)) * 100;

  return (
    <section className="recommend-page recommend-workspace">
      <RecommendationSidebar
        active="recommend"
        onOpenProfile={onOpenProfile}
        historyNotice={historyNotice}
        onOpenRecommendation={() => document.querySelector(".request-card")?.scrollIntoView({ behavior: "smooth" })}
        onOpenHistory={handleOpenHistory}
      />
      <div className={`recommend-content ${recommendationPlans ? "has-results" : "awaiting-results"}`}>
        <section className="request-card">
          <header className="request-heading">
            <div>
              <span className="request-heading-icon">
                <UiIcon name="clipboard" />
              </span>
              <h1>请告诉你的租房需求</h1>
            </div>
            <p>完善需求，获取更符合你期望的推荐结果</p>
          </header>

          <div className="request-form">
            <FormRow index="1" label="工作地址">
              <div className="address-field">
                <input
                  aria-label="工作地址"
                  onChange={(event) => setWorkAddress(event.target.value)}
                  placeholder="请输入工作地址，如：东南大学（四牌楼校区）"
                  value={workAddress}
                />
                <button
                  aria-label="在高德地图上定位工作地址"
                  className="address-location-button"
                  onClick={() => setAddressMapOpen(true)}
                  title="在地图上定位"
                  type="button"
                >
                  <UiIcon name="location" />
                </button>
              </div>
            </FormRow>

            <FormRow
              index="2"
              label={
                <>
                  月租金预算
                  <small className="budget-personal-note">（单人预算）</small>
                </>
              }
            >
              <RangeField
                ariaLabel="月租金预算"
                left={budgetLeft}
                max={BUDGET_MAX}
                min={BUDGET_MIN}
                onMaxChange={(value) => setBudgetMax(Math.max(value, budgetMin + 100))}
                onMinChange={(value) => setBudgetMin(Math.min(value, budgetMax - 100))}
                scaleLeft="500"
                scaleRight="4000"
                valueLabel={`${budgetMin} - ${budgetMax}`}
                valueSuffix="元/月"
                width={budgetWidth}
                valueMax={budgetMax}
                valueMin={budgetMin}
              />
            </FormRow>

            <FormRow index="3" label="接受的通勤距离">
              <RangeField
                ariaLabel="接受的通勤距离"
                left={commuteLeft}
                max={COMMUTE_MAX}
                min={COMMUTE_MIN}
                onMaxChange={(value) => setCommuteMax(Math.max(value, commuteMin + 1))}
                onMinChange={(value) => setCommuteMin(Math.min(value, commuteMax - 1))}
                scaleLeft="1km"
                scaleRight="30km"
                valueLabel={`${commuteMin}km - ${commuteMax}km`}
                width={commuteWidth}
                valueMax={commuteMax}
                valueMin={commuteMin}
              />
            </FormRow>

            <FormRow index="4" label={<>希望周边有什么<br />设施</>}>
              <div className="choice-grid facility-choice-grid">
                {facilityOptions.map((option) => {
                  const selected = selectedFacilities.includes(option.label);
                  return (
                    <button
                      aria-pressed={selected}
                      className={selected ? "selected" : ""}
                      key={option.label}
                      onClick={() => toggleFacility(option.label)}
                      type="button"
                    >
                      <UiIcon name={option.icon} />
                      <span>{option.label}</span>
                    </button>
                  );
                })}
              </div>
            </FormRow>

            <FormRow index="5" label="上下班的交通方式">
              <div className="choice-grid transport-choice-grid">
                {transportOptions.map((option) => (
                  <button
                    aria-pressed={transportMode === option.label}
                    className={transportMode === option.label ? "selected" : ""}
                    key={option.label}
                    onClick={() => setTransportMode(option.label)}
                    type="button"
                  >
                    <UiIcon name={option.icon} />
                    <span>{option.label}</span>
                  </button>
                ))}
              </div>
            </FormRow>

            <FormRow index="6" label="期望租住的房型">
              <div className="choice-grid housing-choice-grid">
                {housingOptions.map((option) => (
                  <button
                    aria-pressed={housingType === option}
                    className={housingType === option ? "selected" : ""}
                    key={option}
                    onClick={() => setHousingType(option)}
                    type="button"
                  >
                    <UiIcon name="note" />
                    <span>{option}</span>
                  </button>
                ))}
              </div>
            </FormRow>
          </div>

          {(errorMessage || resultMessage) && (
            <p className={`request-feedback ${errorMessage ? "error" : "success"}`}>
              {errorMessage || resultMessage}
            </p>
          )}

          <div className="request-submit-row">
            <button className="request-submit" disabled={isLoading} onClick={handleSubmit} type="button">
              {isLoading ? (
                <>
                  <span>正在为您推荐租住区域</span>
                  <span className="request-loading-spinner" aria-hidden="true" />
                </>
              ) : (
                <>
                  <span>生成推荐片区</span>
                  <UiIcon name="arrow" />
                </>
              )}
            </button>
            {incompleteMessage && <p className="request-submit-warning">{incompleteMessage}</p>}
          </div>
        </section>

        {recommendationPlans ? (
          <section className="plan-list" aria-label="片区推荐方案" id="recommend-results">
            {displayPlans.map((plan) => (
              <article className={`plan-card ${plan.tone}`} key={plan.title}>
                <div className="plan-watermark" />
                <header>
                  <span className="plan-symbol">
                    <UiIcon name={plan.icon} />
                  </span>
                  <h2>{plan.title}</h2>
                </header>
                <div className="plan-communities">
                  {plan.communities.map((community) => (
                    <section
                      className={`community-card${community.facilityMatch ? " facility-complete" : ""}`}
                      key={community.id || community.name}
                    >
                      {community.facilityMatch && (
                        <span className="facility-complete-badge">设施齐全</span>
                      )}
                      <div className="community-name">
                        <UiIcon name="pin" />
                        <strong>{community.name}</strong>
                      </div>
                      <div className="community-reasons">
                        <div className="plan-tags">
                          {community.tags.map((tag) => (
                            <span key={tag}>
                              <b>✓</b>
                              {tag}
                            </span>
                          ))}
                        </div>
                      </div>
                      <button onClick={() => openPlan(community)} type="button">
                        查看方案
                        <UiIcon name="arrow" />
                      </button>
                    </section>
                  ))}
                </div>
              </article>
            ))}
          </section>
        ) : (
          <section className={`recommend-empty-state${isLoading ? " is-loading" : ""}`} aria-live="polite">
            <div className="recommend-empty-copy">
              <span className="recommend-empty-kicker">为你发现更合适的南京生活圈</span>
              <h2>{isLoading ? "正在生成专属租住方案" : "从一处工作地点，找到三种生活可能"}</h2>
              <p>
                {isLoading
                  ? "正在综合通勤距离、租金预算与周边设施，请稍候。"
                  : "填写左侧需求后，这里将呈现通勤优先、均衡与性价比三类推荐。"}
              </p>
              {isLoading && <span className="recommend-empty-spinner" aria-hidden="true" />}
            </div>
          </section>
        )}
      </div>

      {addressMapOpen && (
        <AddressMapPicker
          initialAddress={workAddress}
          onClose={() => setAddressMapOpen(false)}
          onConfirm={(address) => {
            setWorkAddress(address);
            setAddressMapOpen(false);
          }}
        />
      )}
    </section>
  );
}

function FormRow({
  children,
  index,
  label
}: {
  children: ReactNode;
  index: string;
  label: ReactNode;
}) {
  return (
    <div className="request-row">
      <span className="request-index">{index}.</span>
      <strong className="request-label">{label}</strong>
      <div className="request-control">{children}</div>
    </div>
  );
}

function RangeField({
  ariaLabel,
  left,
  max,
  min,
  onMaxChange,
  onMinChange,
  scaleLeft,
  scaleRight,
  valueLabel,
  valueSuffix,
  width,
  valueMax,
  valueMin
}: {
  ariaLabel: string;
  left: number;
  max: number;
  min: number;
  onMaxChange: (value: number) => void;
  onMinChange: (value: number) => void;
  scaleLeft: string;
  scaleRight: string;
  valueLabel: string;
  valueSuffix?: string;
  width: number;
  valueMax: number;
  valueMin: number;
}) {
  return (
    <div className="request-range" aria-label={ariaLabel}>
      <div className="request-range-value">
        {valueLabel} {valueSuffix && <span>{valueSuffix}</span>}
      </div>
      <div className="request-range-track">
        <i style={{ left: `${left}%`, width: `${width}%` }} />
        <input
          aria-label={`${ariaLabel}最小值`}
          max={max}
          min={min}
          onChange={(event) => onMinChange(Number(event.target.value))}
          step={ariaLabel === "月租金预算" ? 100 : 1}
          type="range"
          value={valueMin}
        />
        <input
          aria-label={`${ariaLabel}最大值`}
          max={max}
          min={min}
          onChange={(event) => onMaxChange(Number(event.target.value))}
          step={ariaLabel === "月租金预算" ? 100 : 1}
          type="range"
          value={valueMax}
        />
      </div>
      <div className="request-range-scale">
        <span>{scaleLeft}</span>
        <span>{scaleRight}</span>
      </div>
    </div>
  );
}

function UiIcon({ name }: { name: IconName }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.9
  };

  const paths: Record<IconName, ReactNode> = {
    user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.5-4.3 2.8-6.5 7-6.5s6.5 2.2 7 6.5" /></>,
    pin: <><path d="M12 21s6-5.4 6-11a6 6 0 1 0-12 0c0 5.6 6 11 6 11Z" /><circle cx="12" cy="10" r="2" /></>,
    history: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M8.5 8h7M8.5 12h7M8.5 16h5" /></>,
    clipboard: <><rect x="5" y="4" width="14" height="17" rx="3" /><path d="M9 4V2.5h6V4M9 9h6M9 13h6" /></>,
    location: <><path d="M12 21s6-5.4 6-11a6 6 0 1 0-12 0c0 5.6 6 11 6 11Z" /><circle cx="12" cy="10" r="2" /></>,
    train: <><rect x="6" y="3" width="12" height="15" rx="3" /><path d="M9 7h6M8 12h8M9 18l-2 3M15 18l2 3" /><circle cx="9" cy="15" r=".7" fill="currentColor" /><circle cx="15" cy="15" r=".7" fill="currentColor" /></>,
    cart: <><path d="M4 5h2l2 10h9l2-7H7" /><circle cx="10" cy="19" r="1" /><circle cx="17" cy="19" r="1" /></>,
    bag: <><path d="M5 8h14l-1 13H6L5 8Z" /><path d="M9 8V6a3 3 0 0 1 6 0v2" /></>,
    utensils: <><path d="M7 3v7M4.5 3v5A2.5 2.5 0 0 0 7 10v11M9.5 3v5A2.5 2.5 0 0 1 7 10M16 3v18M16 3c3 2 3 7 0 9" /></>,
    basket: <><path d="M4 10h16l-2 10H6L4 10Z" /><path d="m8 10 4-6 4 6M9 14v3M12 14v3M15 14v3" /></>,
    tree: <><path d="M12 21v-5" /><path d="M12 3 7 10h3l-4 6h12l-4-6h3l-5-7Z" /></>,
    dumbbell: <><path d="M7 8v8M4 9v6M17 8v8M20 9v6M7 12h10" /></>,
    stadium: <><path d="M4 9c2.2-2 4.8-3 8-3s5.8 1 8 3v8c-2.2 1.5-4.8 2.2-8 2.2S6.2 18.5 4 17V9Z" /><path d="M4 10c2.4 1.5 5.1 2.2 8 2.2s5.6-.7 8-2.2M8 7v4M16 7v4M9 16h6" /></>,
    leisure: <><path d="M5 11h14M7 11l2 9M17 11l-2 9M8 7h8l1 4H7l1-4Z" /><path d="M12 7V3M9.5 3h5" /></>,
    hospital: <><rect x="5" y="5" width="14" height="16" rx="1" /><path d="M9 5V2h6v3M12 8v7M8.5 11.5h7M9 21v-3h6v3" /></>,
    walk: <><circle cx="13" cy="4" r="2" /><path d="m11 8-2 5 3 2 1 6M11 10l4 3 3-1M9 13l-4 5" /></>,
    bike: <><circle cx="6" cy="17" r="4" /><circle cx="18" cy="17" r="4" /><path d="m6 17 5-8 3 8H6l4-6h6M9 6h4" /></>,
    bus: <><rect x="5" y="3" width="14" height="17" rx="3" /><path d="M7 8h10M8 20v2M16 20v2" /><circle cx="8.5" cy="16" r="1" /><circle cx="15.5" cy="16" r="1" /></>,
    car: <><path d="m5 16 1-6 2-4h8l2 4 1 6v3h-2v-2H7v2H5v-3Z" /><path d="M7 10h10" /><circle cx="8" cy="14" r="1" /><circle cx="16" cy="14" r="1" /></>,
    note: <><path d="M6 3h9l3 3v15H6V3Z" /><path d="M15 3v4h4M9 11h6M9 15h6" /></>,
    balance: <><path d="M12 3v18M5 6h14M7 6l-4 8h8L7 6ZM17 6l-4 8h8l-4-8ZM8 21h8" /></>,
    coins: <><ellipse cx="12" cy="6" rx="7" ry="3" /><path d="M5 6v4c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 10v4c0 1.7 3.1 3 7 3s7-1.3 7-3v-4M5 14v4c0 1.7 3.1 3 7 3s7-1.3 7-3v-4" /></>,
    arrow: <><path d="M5 12h14M14 7l5 5-5 5" /></>
  };

  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" {...common}>
      {paths[name]}
    </svg>
  );
}
