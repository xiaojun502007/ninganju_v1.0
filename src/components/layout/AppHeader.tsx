export type PageId = "login" | "recommend" | "analysis" | "admin";

type AppHeaderProps = {
  activePage: PageId;
  onLogout: () => void;
  onNavigate: (page: PageId) => void;
};

export function AppHeader({ activePage, onLogout, onNavigate }: AppHeaderProps) {
  return (
    <header className="topbar">
      <div className="brand" role="button" tabIndex={0} onClick={() => onNavigate("login")}>
        <span className="logo-mark" aria-hidden="true">
          <span />
        </span>
        <strong>宁安居</strong>
        <em>面向来宁青年的租房片区智能推荐平台</em>
      </div>

      <div className="topbar-actions">
        {(activePage === "analysis" || activePage === "admin") && (
          <button className="logout-button" onClick={onLogout} type="button">
            退出登录
          </button>
        )}
      </div>
    </header>
  );
}
