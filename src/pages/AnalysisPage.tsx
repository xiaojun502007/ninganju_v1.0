import { useEffect, useState } from "react";
import { AmapRouteMap } from "../components/AmapRouteMap";
import { EvaluationHistoryTable } from "../components/EvaluationHistoryTable";
import { RecommendationSidebar } from "../components/layout/RecommendationSidebar";
import { CommuteInfoPanel } from "../components/CommuteInfoPanel";
import { FacilityRadarChart } from "../components/FacilityRadarChart";
import { getCommuteData, type CommuteData, type CommuteLocation, type CommuteMode } from "../services/commuteService";
import {
  deleteEvaluationHistory,
  listEvaluationHistory,
  saveEvaluationHistory,
  type EvaluationHistoryRecord
} from "../services/evaluationHistoryService";
import { getFacilityData, type FacilityData } from "../services/facilityService";
import { calculateRentFitScore, calculateRentOverlapScore } from "../utils/rentScore";

type AnalysisPageProps = {
  areaName: string;
  areaLocation: CommuteLocation | null;
  preferenceId?: string;
  onBack: () => void;
  onOpenProfile: () => void;
  onOpenHistoryRecord: (preferenceId: string, areaName: string, areaLocation: CommuteLocation | null) => void;
  username: string;
};

export function AnalysisPage({
  areaName,
  areaLocation,
  preferenceId = "",
  onBack,
  onOpenProfile,
  onOpenHistoryRecord,
  username
}: AnalysisPageProps) {
  const [commuteData, setCommuteData] = useState<CommuteData | null>(null);
  const [commuteLoading, setCommuteLoading] = useState(false);
  const [commuteError, setCommuteError] = useState("");
  const [commuteMode, setCommuteMode] = useState<CommuteMode>("driving");
  const [facilityData, setFacilityData] = useState<FacilityData | null>(null);
  const [facilityLoading, setFacilityLoading] = useState(false);
  const [facilityError, setFacilityError] = useState("");
  const [historyRecords, setHistoryRecords] = useState<EvaluationHistoryRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyMessage, setHistoryMessage] = useState("");
  const [overviewCommuteScore, setOverviewCommuteScore] = useState<number | undefined>(undefined);
  const areaLocationForFacilities = areaLocation || commuteData?.areaLocation || null;
  const selectedLocationKey = areaLocation
    ? `${areaLocation.lng.toFixed(6)},${areaLocation.lat.toFixed(6)}`
    : "";
  const areaLocationKey = areaLocationForFacilities
    ? `${areaLocationForFacilities.lng.toFixed(6)},${areaLocationForFacilities.lat.toFixed(6)}`
    : "";
  const commuteScore = overviewCommuteScore;
  const commuteScoreText = commuteScore == null ? "--" : String(commuteScore);
  const commuteScoreDesc = commuteScore == null && commuteLoading ? "正在计算通勤得分" : getCommuteScoreDesc(commuteScore);
  const facilityScore = calculateFacilityTotalScore(facilityData?.poiSummary || []);
  const facilityScoreText = facilityScore == null ? "--" : String(facilityScore);
  const facilityScoreDesc = facilityLoading ? "正在计算设施得分" : getFacilityScoreDesc(facilityScore);
  const rentResult = calculateRentOverlapScore(commuteData?.rentContext);
  const rentScore = rentResult?.score ?? null;
  const rentScoreText = rentScore == null ? "--" : String(rentScore);
  const rentScoreDesc = rentResult
    ? `${commuteData?.rentContext?.housingType || "所选房型"}租金与预算重叠${Math.round(rentResult.overlapRatio * 100)}%`
    : "暂无可用的房型租金区间";
  const totalScore = calculateRentFitScore(commuteScore, facilityScore, rentScore);
  const totalScoreText = totalScore == null ? "--" : String(totalScore);
  const totalScoreDesc = totalScore == null && (commuteLoading || facilityLoading) ? "正在计算适配总分" : getRentFitScoreDesc(totalScore);
  const recommendationArea = commuteData?.recommendationArea;
  const areaTagline = recommendationArea?.tagline || "正在同步推荐页生成的片区描述";
  const areaTags = recommendationArea?.tags?.length ? recommendationArea.tags.slice(0, 3) : ["片区推荐", "生活圈评估", "通勤测算"];

  useEffect(() => {
    if (!preferenceId) {
      setCommuteData(null);
      setCommuteError("请先在推荐页生成推荐结果，再查看动态通勤路线。");
      return;
    }

    setCommuteLoading(true);
    setCommuteError("");
    getCommuteData(preferenceId, areaName, commuteMode, areaLocation)
      .then((data) => {
        setCommuteData(data);
        if (data.commuteScoreResult?.commuteScore != null) {
          setOverviewCommuteScore((currentScore) => currentScore ?? data.commuteScoreResult?.commuteScore);
        }
        setCommuteError(data.message || "");
      })
      .catch((error: Error) => {
        setCommuteData(null);
        setCommuteError(error.message);
      })
      .finally(() => setCommuteLoading(false));
  }, [areaName, commuteMode, preferenceId, selectedLocationKey]);

  useEffect(() => {
    setOverviewCommuteScore(undefined);
    setFacilityData(null);
    setFacilityError("");
  }, [areaName, preferenceId, selectedLocationKey]);

  useEffect(() => {
    if (!preferenceId || !areaLocationForFacilities) {
      setFacilityData(null);
      return;
    }

    let cancelled = false;
    setFacilityLoading(true);
    setFacilityError("");
    getFacilityData(preferenceId, areaName, areaLocationForFacilities)
      .then((data) => {
        if (cancelled) return;
        setFacilityData(data);
        setFacilityError("");
      })
      .catch((error: Error) => {
        if (cancelled) return;
        setFacilityData(null);
        setFacilityError(error.message);
      })
      .finally(() => {
        if (!cancelled) setFacilityLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [areaName, areaLocationKey, preferenceId]);

  useEffect(() => {
    refreshEvaluationHistory();
  }, [username]);

  const refreshEvaluationHistory = async () => {
    try {
      const records = await listEvaluationHistory(username || "xiaoning");
      setHistoryRecords(records);
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "评估记录读取失败，请稍后重试");
    }
  };

  const handleSaveEvaluation = async () => {
    if (totalScore == null || commuteScore == null || facilityScore == null || rentScore == null) {
      setHistoryMessage("当前片区评分还没有计算完成，请稍后再保存。");
      return;
    }

    setHistoryLoading(true);
    setHistoryMessage("");
    try {
      await saveEvaluationHistory({
        username: username || "xiaoning",
        regionName: areaName,
        totalScore,
        commuteScore,
        facilityScore,
        otherInfo: {
          preferenceId,
          areaName,
          recommendationArea: commuteData?.recommendationArea || null,
          areaLocation: areaLocationForFacilities,
          rentScore
        }
      });
      await refreshEvaluationHistory();
      setHistoryMessage("本次片区评估结果已保存。");
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "评估结果保存失败，请稍后重试");
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleDeleteEvaluation = async (recordId: string) => {
    setHistoryLoading(true);
    setHistoryMessage("");
    try {
      await deleteEvaluationHistory(username || "xiaoning", recordId);
      await refreshEvaluationHistory();
      setHistoryMessage("该条评估记录已删除。");
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "评估记录删除失败，请稍后重试");
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleOpenHistoryRecord = (record: EvaluationHistoryRecord) => {
    onOpenHistoryRecord(
      record.otherInfo?.preferenceId || preferenceId,
      record.regionName,
      record.otherInfo?.areaLocation || null
    );
  };

  return (
    <div className="analysis-workspace">
      <RecommendationSidebar
        active="history"
        onOpenProfile={onOpenProfile}
        onOpenRecommendation={onBack}
        onOpenHistory={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      />
    <section className="analysis-page evaluation-page">
      <SectionTitle title="片区总体得分" />
      <div className="evaluation-overview">
        <div className="area-intro">
          <h1>
            {areaName}
            <span className="hero-pin" />
          </h1>
          <p>{areaTagline}</p>
          <div className="analysis-tags">
            {areaTags.map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </div>
        </div>

        <div className="score-summary">
          <ScoreCard featured tone="orange" icon="train" title="租住适配总分" value={totalScoreText} desc={totalScoreDesc} />
          <ScoreCard tone="amber" icon="bag" title="租金适配得分" value={rentScoreText} desc={rentScoreDesc} />
          <ScoreCard tone="blue" icon="metro" title="通勤得分" value={commuteScoreText} desc={commuteScoreDesc} />
          <ScoreCard tone="green" icon="bag" title="生活圈设施得分" value={facilityScoreText} desc={facilityScoreDesc} />
        </div>
      </div>

      <SectionTitle title="职住通勤情况" />
      <div className="commute-section-grid">
        <AmapRouteMap
          areaLocation={commuteData?.areaLocation || areaLocation}
          commute={commuteData?.commute || null}
          isLoading={commuteLoading}
          workLocation={commuteData?.workLocation || null}
        />
        <CommuteInfoPanel
          activeMode={commuteMode}
          commute={commuteData?.commute || null}
          errorMessage={commuteError}
          isLoading={commuteLoading}
          onModeChange={setCommuteMode}
        />
      </div>

      <SectionTitle title="生活圈设施情况" />
      <div className="life-section-grid">
        <section className="radar-card">
          <h2>8维生活圈评分</h2>
          <FacilityRadarChart
            errorMessage={facilityError}
            isLoading={facilityLoading}
            items={facilityData?.poiSummary || []}
          />
          <div className="legend-line">
            <span>本片区得分</span>
            <span>总分</span>
          </div>
        </section>

        <section className="life-detail-card">
          <div className="facility-summary">
            <h2>周边设施分布</h2>
            <div className="facility-grid">
              {facilityLoading && <p className="facility-status">正在汇总1公里生活圈设施...</p>}
              {!facilityLoading && facilityError && <p className="facility-status error">{facilityError}</p>}
              {!facilityLoading && !facilityError &&
                (facilityData?.poiSummary || [])
                  .filter((item) => !["medical", "transport"].includes(item.key))
                  .map((item) => (
                    <article key={item.key}>
                      <span className={`facility-icon ${facilityTone(item.key)}`} />
                      <div>
                        <div className="facility-score-line">
                          <strong>{item.facilityName}</strong>
                          <b>{item.score}分</b>
                        </div>
                        <p>
                          {item.nearestDistance === null ? "暂无设施" : `最近约${item.nearestDistance}米`}
                          {item.examples.length > 0 ? `｜${item.examples.slice(0, 3).join("、")}` : ""}
                        </p>
                      </div>
                    </article>
                  ))}
            </div>
          </div>

          <section className="ai-summary">
            <h2>AI评估总结</h2>
            <p>
              {facilityData?.recommendationReason ||
                `${areaName}的推荐理由正在从历史推荐结果中读取。若当前为临时评估入口，请先在推荐页生成片区推荐后再查看。`}
            </p>
          </section>
        </section>
      </div>

      <div className="evaluation-actions">
        <button className="outline-orange restart-button" onClick={onBack} type="button">
          重新推荐
        </button>
        <button
          className="save-button evaluation-save"
          disabled={historyLoading || totalScore == null || commuteScore == null || facilityScore == null || rentScore == null}
          onClick={handleSaveEvaluation}
          type="button"
        >
          {historyLoading ? "正在处理评估记录..." : "保存本次片区评估结果"}
        </button>
      </div>

      <SectionTitle title="查看具体房源链接" />
      <div className="housing-platform-links">
        <a className="housing-platform-link beike" href="https://www.ke.com/" target="_blank" rel="noopener noreferrer" aria-label="前往贝壳找房官网首页">
          <PlatformIcon src="https://www.ke.com/favicon.ico" fallback="/images/platform-beike.svg" />
          <span className="housing-platform-name">贝壳找房</span>
          <span className="housing-platform-enter">点击进入 <span aria-hidden="true">↗</span></span>
        </a>
        <a className="housing-platform-link anjuke" href="https://www.anjuke.com/" target="_blank" rel="noopener noreferrer" aria-label="前往安居客官网首页">
          <PlatformIcon src="https://www.anjuke.com/favicon.ico" fallback="/images/platform-anjuke.svg" />
          <span className="housing-platform-name">安居客</span>
          <span className="housing-platform-enter">点击进入 <span aria-hidden="true">↗</span></span>
        </a>
        <a className="housing-platform-link ziroom" href="https://www.ziroom.com/" target="_blank" rel="noopener noreferrer" aria-label="前往自如官网首页">
          <PlatformIcon src="https://www.ziroom.com/favicon.ico" fallback="/images/platform-ziroom.svg" />
          <span className="housing-platform-name">自如</span>
          <span className="housing-platform-enter">点击进入 <span aria-hidden="true">↗</span></span>
        </a>
        <a className="housing-platform-link lianjia" href="https://www.lianjia.com/" target="_blank" rel="noopener noreferrer" aria-label="前往链家官网首页">
          <PlatformIcon src="https://www.lianjia.com/favicon.ico" fallback="/images/platform-lianjia.svg" />
          <span className="housing-platform-name">链家</span>
          <span className="housing-platform-enter">点击进入 <span aria-hidden="true">↗</span></span>
        </a>
      </div>

      <SectionTitle title="查看推荐微社区记录" />
      <section className="history-record" id="evaluation-history-record">
        {historyMessage && <p className="history-message">{historyMessage}</p>}
        <EvaluationHistoryTable
          records={historyRecords}
          loading={historyLoading}
          onOpen={handleOpenHistoryRecord}
          onDelete={handleDeleteEvaluation}
        />
      </section>

      <p className="analysis-note">评分基于大数据与AI模型综合评估，仅供参考，请结合个人需求理性决策。</p>
    </section>
    </div>
  );
}

function SectionTitle({ title }: { title: string }) {
  return (
    <div className="section-title">
      <h2>{title}</h2>
    </div>
  );
}

function PlatformIcon({ src, fallback }: { src: string; fallback: string }) {
  return (
    <img
      className="housing-platform-icon"
      src={src}
      alt=""
      aria-hidden="true"
      onError={(event) => {
        if (!event.currentTarget.src.endsWith(fallback)) event.currentTarget.src = fallback;
      }}
    />
  );
}

function facilityTone(key: string) {
  const toneMap: Record<string, string> = {
    shopping: "orange",
    food: "orange",
    transport: "blue",
    medical: "red",
    education: "orange",
    sports: "green",
    park: "green",
    life: "blue"
  };
  return toneMap[key] || "orange";
}

function getCommuteScoreDesc(score?: number) {
  if (score == null) return "等待路线规划结果";
  if (score > 90) return "通勤效率优秀";
  if (score >= 75) return "通勤效率良好";
  if (score >= 60) return "通勤效率中等";
  return "通勤效率不佳";
}

function calculateFacilityTotalScore(items: { score: number }[]) {
  if (items.length === 0) return null;
  return Math.round(items.reduce((sum, item) => sum + item.score * 0.125, 0));
}

function getFacilityScoreDesc(score: number | null) {
  if (score == null) return "等待设施评估结果";
  if (score > 90) return "设施配置完善";
  if (score >= 75) return "设施配置良好";
  if (score >= 60) return "设施配置一般";
  return "设施配置欠缺";
}

function getRentFitScoreDesc(score: number | null) {
  if (score == null) return "等待综合评估结果";
  if (score > 90) return "非常适合";
  if (score >= 75) return "较为适合";
  if (score >= 60) return "中等适合";
  return "不太适合";
}

function ScoreCard({
  featured = false,
  tone,
  icon,
  title,
  value,
  desc
}: {
  featured?: boolean;
  tone: string;
  icon: string;
  title: string;
  value: string;
  desc: string;
}) {
  return (
    <article className={`summary-card${featured ? " featured" : ""}`}>
      <span className={`summary-icon ${tone} ${icon}`} />
      <div>
        <h3>{title}</h3>
        <strong className={`${tone}-text`}>
          {value}
          <em>/100</em>
        </strong>
        <p>{desc}</p>
      </div>
    </article>
  );
}
