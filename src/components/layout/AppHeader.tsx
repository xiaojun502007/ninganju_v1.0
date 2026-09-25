import { useEffect, useRef, useState } from "react";

export type PageId = "login" | "recommend" | "analysis" | "profile" | "admin";

type AppHeaderProps = {
  activePage: PageId;
  onLogout: () => void;
  onNavigate: (page: PageId) => void;
  username: string;
};

export function AppHeader({ activePage, onLogout, onNavigate, username }: AppHeaderProps) {
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setUserMenuOpen(false);
  }, [activePage]);

  useEffect(() => {
    const closeUserMenu = (event: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setUserMenuOpen(false);
    };
    document.addEventListener("mousedown", closeUserMenu);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeUserMenu);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  return (
    <header className={`topbar ${activePage === "recommend" || activePage === "profile" ? "recommend-topbar" : ""}`}>
      <div className="brand" role="button" tabIndex={0} onClick={() => onNavigate("login")}>
        <span className="logo-mark" aria-hidden="true">
          <span />
        </span>
        <strong>宁安居</strong>
        <em>面向来宁青年的租房片区智能推荐平台</em>
      </div>

      {(activePage === "recommend" || activePage === "profile") && (
        <div className="recommend-header-slogan" aria-hidden="true">
          在南京 · 住进更好的生活
          <i />
        </div>
      )}

      <div className="topbar-actions">
        {activePage !== "login" && (
          <div className="user-status-menu" ref={userMenuRef}>
            <button
              aria-expanded={userMenuOpen}
              aria-haspopup="menu"
              className="user-status-trigger"
              onClick={() => setUserMenuOpen((current) => !current)}
              type="button"
            >
              <span className="user-status-avatar" aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <circle cx="12" cy="8" r="3.5" />
                  <path d="M5 20c.5-4.2 2.8-6.4 7-6.4s6.5 2.2 7 6.4" />
                </svg>
              </span>
              <span className="user-status-copy">
                <strong>{username || "xiaoning"}</strong>
                <em>欢迎您！</em>
              </span>
              <span className={`user-status-chevron ${userMenuOpen ? "open" : ""}`} aria-hidden="true">⌄</span>
            </button>
            {userMenuOpen && (
              <div className="user-status-dropdown" role="menu">
                <button
                  onClick={() => {
                    setUserMenuOpen(false);
                    onLogout();
                  }}
                  role="menuitem"
                  type="button"
                >
                  退出登录
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
