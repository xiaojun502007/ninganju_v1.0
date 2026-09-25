type RecommendationSidebarProps = {
  active: "profile" | "recommend" | "history";
  onOpenProfile: () => void;
  onOpenRecommendation: () => void;
  onOpenHistory: () => void;
  historyNotice?: string;
};

export function RecommendationSidebar({ active, onOpenProfile, onOpenRecommendation, onOpenHistory, historyNotice = "" }: RecommendationSidebarProps) {
  return (
    <aside className="recommend-sidebar" aria-label="片区推荐导航">
      <nav>
        <button className={active === "profile" ? "active" : undefined} onClick={onOpenProfile} type="button">
          <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.5-4.3 2.8-6.5 7-6.5s6.5 2.2 7 6.5" /></svg>
          <span>个人信息</span>
        </button>
        <button className={active === "recommend" ? "active" : undefined} onClick={onOpenRecommendation} type="button">
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M12 21s6-5.4 6-11a6 6 0 1 0-12 0c0 5.6 6 11 6 11Z" /><circle cx="12" cy="10" r="2" /></svg>
          <span>片区推荐</span>
        </button>
        <button className={active === "history" ? "active" : undefined} onClick={onOpenHistory} type="button">
          <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M8.5 8h7M8.5 12h7M8.5 16h5" /></svg>
          <span>查看推荐记录</span>
        </button>
      </nav>
      {historyNotice && <p className="sidebar-history-notice" role="status">{historyNotice}</p>}
      <p className="sidebar-wish">让年轻人在南京<br />找到温暖的家</p>
    </aside>
  );
}
