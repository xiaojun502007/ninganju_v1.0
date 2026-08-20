import { useEffect, useState } from "react";
import { AmapRouteMap } from "../components/AmapRouteMap";
import { CommuteInfoPanel } from "../components/CommuteInfoPanel";
import { FacilityRadarChart } from "../components/FacilityRadarChart";
import { getCommuteData, type CommuteData, type CommuteMode } from "../services/commuteService";
import {
  deleteEvaluationHistory,
  listEvaluationHistory,
  saveEvaluationHistory,
  type EvaluationHistoryRecord
} from "../services/evaluationHistoryService";
import { getFacilityData, type FacilityData } from "../services/facilityService";

type AnalysisPageProps = {
  areaName: string;
  preferenceId?: string;
  onBack: () => void;
  onOpenHistoryRecord: (preferenceId: string, areaName: string) => void;
  username: string;
};

export function AnalysisPage({
  areaName,
  preferenceId = "",
  onBack,
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
  const areaLocationForFacilities = commuteData?.areaLocation || null;
  const areaLocationKey = areaLocationForFacilities
    ? `${areaLocationForFacilities.lng.toFixed(6)},${areaLocationForFacilities.lat.toFixed(6)}`
    : "";
  const commuteScore = overviewCommuteScore;
  const commuteScoreText = commuteScore == null ? "--" : String(commuteScore);
  const commuteScoreDesc = commuteScore == null && commuteLoading ? "正在计算通勤得分" : getCommuteScoreDesc(commuteScore);
  const facilityScore = calculateFacilityTotalScore(facilityData?.poiSummary || []);
  const facilityScoreText = facilityScore == null ? "--" : String(facilityScore);
  const facilityScoreDesc = facilityLoading ? "正在计算设施得分" : getFacilityScoreDesc(facilityScore);
  const totalScore = calculateRentFitScore(commuteScore, facilityScore);
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
    getCommuteData(preferenceId, areaName, commuteMode)
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
  }, [areaName, commuteMode, preferenceId]);

  useEffect(() => {
    setOverviewCommuteScore(undefined);
    setFacilityData(null);
    setFacilityError("");
  }, [areaName, preferenceId]);

  useEffect(() => {
    if (!preferenceId || !areaLocationForFacilities) {
      setFacilityData(null);
      return;
    }

    setFacilityLoading(true);
    setFacilityError("");
    getFacilityData(preferenceId, areaName, areaLocationForFacilities)
      .then((data) => {
        setFacilityData(data);
        setFacilityError(data.message || "");
      })
      .catch((error: Error) => {
        setFacilityData(null);
        setFacilityError(error.message);
      })
      .finally(() => setFacilityLoading(false));
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
    if (totalScore == null || commuteScore == null || facilityScore == null) {
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
          areaLocation: commuteData?.areaLocation || null
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
    onOpenHistoryRecord(record.otherInfo?.preferenceId || preferenceId, record.regionName);
  };

  return (
    <section className="analysis-page evaluation-page">
      <button className="outline-orange restart-button" onClick={onBack} type="button">
        重新推荐
      </button>

      <SectionTitle index="I" title="片区总体得分" />
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
          <ScoreCard tone="orange" icon="train" title="租住适配总分" value={totalScoreText} desc={totalScoreDesc} />
          <ScoreCard tone="blue" icon="metro" title="通勤得分" value={commuteScoreText} desc={commuteScoreDesc} />
          <ScoreCard tone="green" icon="bag" title="生活圈设施得分" value={facilityScoreText} desc={facilityScoreDesc} />
        </div>
      </div>

      <SectionTitle index="II" title="职住通勤情况" />
      <div className="commute-section-grid">
        <AmapRouteMap
          areaLocation={commuteData?.areaLocation || null}
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

      <SectionTitle index="III" title="生活圈设施情况" />
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

      <button
        className="save-button evaluation-save"
        disabled={historyLoading || totalScore == null || commuteScore == null || facilityScore == null}
        onClick={handleSaveEvaluation}
        type="button"
      >
        {historyLoading ? "正在处理评估记录..." : "保存本次片区评估结果"}
      </button>

      <section className="history-record">
        <h2>我的评估记录</h2>
        {historyMessage && <p className="history-message">{historyMessage}</p>}
        <div className="record-table">
          <div className="record-head">
            <span>片区</span>
            <span>总分</span>
            <span>通勤分</span>
            <span>设施分</span>
            <span>保存时间</span>
            <span>操作</span>
          </div>
          {historyRecords.length === 0 && (
            <div className="record-row record-empty">
              <span>暂无评估记录</span>
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
          )}
          {historyRecords.map((record) => (
            <div className="record-row" key={record.id}>
              <span>{record.regionName}</span>
              <b className="orange-text">{record.totalScore}</b>
              <b className="blue-text">{record.commuteScore}</b>
              <b className="green-text">{record.facilityScore}</b>
              <span>{record.time}</span>
              <span>
                <button onClick={() => handleOpenHistoryRecord(record)} type="button">
                  查看详情
                </button>
                <button disabled={historyLoading} onClick={() => handleDeleteEvaluation(record.id)} type="button">
                  删除
                </button>
              </span>
            </div>
          ))}
        </div>
      </section>

      <p className="analysis-note">评分基于大数据与AI模型综合评估，仅供参考，请结合个人需求理性决策。</p>
    </section>
  );
}

function SectionTitle({ index, title }: { index: string; title: string }) {
  return (
    <div className="section-title">
      <strong>{index}</strong>
      <h2>{title}</h2>
      <i />
    </div>
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

function calculateRentFitScore(commuteScore?: number, facilityScore?: number | null) {
  if (commuteScore == null || facilityScore == null) return null;
  return Math.round(commuteScore * 0.5 + facilityScore * 0.5);
}

function getRentFitScoreDesc(score: number | null) {
  if (score == null) return "等待综合评估结果";
  if (score > 90) return "非常适合";
  if (score >= 75) return "较为适合";
  if (score >= 60) return "中等适合";
  return "不太适合";
}

function ScoreCard({
  tone,
  icon,
  title,
  value,
  desc
}: {
  tone: string;
  icon: string;
  title: string;
  value: string;
  desc: string;
}) {
  return (
    <article className="summary-card">
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
