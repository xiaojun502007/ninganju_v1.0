import { useState } from "react";
import { AppHeader, type PageId } from "./components/layout/AppHeader";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { LoginPage } from "./pages/LoginPage";
import { RecommendPage } from "./pages/RecommendPage";

function App() {
  const [activePage, setActivePage] = useState<PageId>("login");
  const [selectedArea, setSelectedArea] = useState("安德门片区");
  const [selectedPreferenceId, setSelectedPreferenceId] = useState("");
  const [currentUsername, setCurrentUsername] = useState("xiaoning");

  const navigate = (page: PageId) => {
    setActivePage(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleLogout = () => {
    setSelectedArea("安德门片区");
    setSelectedPreferenceId("");
    setCurrentUsername("xiaoning");
    navigate("login");
  };

  return (
    <div className="app">
      <AppHeader activePage={activePage} onLogout={handleLogout} onNavigate={navigate} />
      <main>
        {activePage === "login" && (
          <LoginPage
            onLogin={(username, role) => {
              setCurrentUsername(username || "xiaoning");
              navigate(role === "admin" ? "admin" : "recommend");
            }}
          />
        )}
        {activePage === "admin" && <AdminDashboardPage />}
        {activePage === "recommend" && (
          <RecommendPage
            onOpenAnalysis={(preferenceId, areaName) => {
              if (preferenceId) {
                setSelectedPreferenceId(preferenceId);
              }
              if (areaName) {
                setSelectedArea(areaName);
              }
              navigate("analysis");
            }}
          />
        )}
        {activePage === "analysis" && (
          <AnalysisPage
            areaName={selectedArea}
            preferenceId={selectedPreferenceId}
            onBack={() => navigate("recommend")}
            onOpenHistoryRecord={(nextPreferenceId, nextAreaName) => {
              if (nextPreferenceId) {
                setSelectedPreferenceId(nextPreferenceId);
              }
              if (nextAreaName) {
                setSelectedArea(nextAreaName);
              }
              navigate("analysis");
            }}
            username={currentUsername}
          />
        )}
      </main>
    </div>
  );
}

export default App;
