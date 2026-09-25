import { useEffect, useState, type ReactNode } from "react";
import { EvaluationHistoryTable } from "../components/EvaluationHistoryTable";
import { RecommendationSidebar } from "../components/layout/RecommendationSidebar";
import {
  deleteEvaluationHistory,
  listEvaluationHistory,
  type EvaluationHistoryRecord
} from "../services/evaluationHistoryService";
import { getProfile, type ProfileData } from "../services/profileService";
import type { CommuteLocation } from "../services/commuteService";

type ProfilePageProps = {
  username: string;
  sessionToken: string;
  waitForDetailTracking: () => Promise<void>;
  onOpenRecommendation: () => void;
  onOpenLastViewedDetail: () => boolean;
  onOpenHistoryRecord: (preferenceId: string, areaName: string, areaLocation: CommuteLocation | null) => void;
};

export function ProfilePage({
  username,
  sessionToken,
  waitForDetailTracking,
  onOpenRecommendation,
  onOpenLastViewedDetail,
  onOpenHistoryRecord
}: ProfilePageProps) {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [records, setRecords] = useState<EvaluationHistoryRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [historyNotice, setHistoryNotice] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setMessage("");
    waitForDetailTracking()
      .then(() => Promise.allSettled([getProfile(sessionToken), listEvaluationHistory(username)]))
      .then(([profileResult, recordsResult]) => {
        if (cancelled) return;
        if (profileResult.status === "fulfilled") setProfile(profileResult.value);
        else setMessage(profileResult.reason instanceof Error ? profileResult.reason.message : "个人信息读取失败");
        if (recordsResult.status === "fulfilled") setRecords(recordsResult.value);
        else setMessage((current) => current || "评估记录读取失败，请稍后重试");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [username, sessionToken]);

  const handleDelete = async (id: string) => {
    setHistoryBusy(true);
    setMessage("");
    try {
      await deleteEvaluationHistory(username, id);
      const [nextRecords, nextProfile] = await Promise.all([
        listEvaluationHistory(username), getProfile(sessionToken)
      ]);
      setRecords(nextRecords);
      setProfile(nextProfile);
      setMessage("该条评估记录已删除。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "删除失败，请稍后重试");
    } finally {
      setHistoryBusy(false);
    }
  };

  const handleOpenRecord = (record: EvaluationHistoryRecord) => {
    const preferenceId = record.otherInfo?.preferenceId;
    if (!preferenceId) {
      setMessage("这条旧记录缺少租房需求编号，暂时无法重新加载详情。");
      return;
    }
    onOpenHistoryRecord(preferenceId, record.regionName, record.otherInfo?.areaLocation || null);
  };

  const preference = profile?.latestPreference;
  const personalBudgetFactor = preference?.housingType === "两居室普通住宅" ? 2 : 1;
  const budgetText = preference
    ? `${preference.budgetMin / personalBudgetFactor} - ${preference.budgetMax / personalBudgetFactor} 元/月（单人）`
    : "尚未填写";
  const commuteText = preference
    ? `${preference.commuteDistanceMin}km - ${preference.commuteDistanceMax}km`
    : "尚未填写";

  return (
    <div className="profile-workspace">
      <RecommendationSidebar
        active="profile"
        onOpenProfile={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        onOpenRecommendation={onOpenRecommendation}
        onOpenHistory={() => {
          setHistoryNotice("");
          if (!onOpenLastViewedDetail()) setHistoryNotice("暂无查看过的微社区详情，请先在推荐结果中点击一次“查看方案”");
        }}
        historyNotice={historyNotice}
      />

      <div className="profile-content">
        <section className="profile-hero">
          <div className="profile-avatar"><ProfileIcon name="user" /></div>
          <div>
            <div className="profile-hello"><h1>{profile?.username || username}</h1><span>欢迎回来！</span></div>
            <p>用智能推荐，发现更适合你的南京生活</p>
            <div className="profile-badges"><span>当前登录用户</span><span>南京租房探索者</span></div>
          </div>
        </section>

        <section className="profile-panel profile-info-panel">
          <div className="profile-panel-heading">
            <span className="profile-heading-icon"><ProfileIcon name="user" /></span>
            <h2>个人信息</h2>
            <button type="button" onClick={onOpenRecommendation}>更新租房偏好 <span aria-hidden="true">→</span></button>
          </div>
          <div className="profile-info-grid">
            <ProfileField label="用户名" value={profile?.username || username} />
            <ProfileField label="工作地点" value={preference?.workAddress || "尚未填写"} />
            <ProfileField label="设施偏好" value={preference?.facilityPreferences?.join("、") || ""} />
            <ProfileField label="常用通勤方式" value={preference?.transportPreference || "尚未填写"} />
            <ProfileField label="期望租住房型" value={preference?.housingType || "尚未填写"} />
            <ProfileField label="预算偏好" value={budgetText} />
            <ProfileField label="最近一次偏好提交" value={formatDate(preference?.createdAt || null)} />
            <ProfileField label="可接受通勤距离" value={commuteText} />
          </div>
        </section>

        <section className="profile-panel profile-stats-panel">
          <div className="profile-panel-heading"><span className="profile-heading-icon"><ProfileIcon name="chart" /></span><h2>我的使用数据</h2></div>
          <div className="profile-stats-grid">
            <ProfileStat tone="orange" icon="document" title="累计推荐次数" value={profile?.stats.recommendationCount ?? 0} unit="次" caption="每次提交租房需求" />
            <ProfileStat tone="blue" icon="eye" title="详情查看次数" value={profile?.stats.detailViewCount ?? 0} unit="次" caption="查看微社区详情" />
            <ProfileStat tone="red" icon="bookmark" title="收藏微社区数" value={profile?.stats.savedCommunityCount ?? 0} unit="个" caption="已保存的评估记录" />
            <ProfileStat tone="green" icon="calendar" title="最近一次使用时间" value={formatDate(profile?.stats.lastUsedAt || null)} caption="最近的账号操作" />
          </div>
        </section>

        <section className="profile-panel profile-history-panel">
          <div className="profile-panel-heading"><span className="profile-heading-icon"><ProfileIcon name="bookmark" /></span><h2>历史收藏租房微社区</h2></div>
          {message && <p className="profile-message" role="status">{message}</p>}
          {loading ? <p className="profile-loading">正在读取个人信息与评估记录...</p> : (
            <EvaluationHistoryTable records={records} loading={historyBusy} onOpen={handleOpenRecord} onDelete={handleDelete} />
          )}
        </section>
      </div>
      <aside className="profile-visual" aria-hidden="true" />
    </div>
  );
}

function ProfileField({ label, value }: { label: string; value: string }) {
  return <div className="profile-field"><span>{label}</span><strong>{value}</strong></div>;
}

function ProfileStat({ tone, icon, title, value, unit, caption }: {
  tone: string; icon: IconName; title: string; value: string | number; unit?: string; caption: string;
}) {
  return (
    <article className={`profile-stat profile-stat-${tone}`}>
      <span className="profile-stat-icon"><ProfileIcon name={icon} /></span>
      <div><h3>{title}</h3><p><strong>{value}</strong>{unit && <span>{unit}</span>}</p><small>{caption}</small></div>
    </article>
  );
}

type IconName = "user" | "chart" | "document" | "eye" | "bookmark" | "calendar";

function ProfileIcon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.5-4 2.8-6.2 7-6.2s6.5 2.2 7 6.2" /></>,
    chart: <><path d="M4 20V11m4 9V6m4 14V9m4 11V4m4 16v-7" /></>,
    document: <><path d="M6 3h9l4 4v14H6zM14 3v5h5M9 13h7M9 17h7" /></>,
    eye: <><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z" /><circle cx="12" cy="12" r="3" /></>,
    bookmark: <path d="M12 21 4 13.5C-1 8.5 6 2 12 7c6-5 13 1.5 8 6.5Z" />,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 2v6M17 2v6M3 10h18M7 14h3M14 14h3M7 18h3" /></>
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function formatDate(value: string | null) {
  if (!value) return "暂无记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: false
  }).format(date);
}
