import { useRef, useState } from "react";
import { AppHeader, type PageId } from "./components/layout/AppHeader";
import { AdminDashboardPage } from "./pages/AdminDashboardPage";
import { AnalysisPage } from "./pages/AnalysisPage";
import { LoginPage } from "./pages/LoginPage";
import { ProfilePage } from "./pages/ProfilePage";
import { RecommendPage } from "./pages/RecommendPage";
import type { RecommendedArea } from "./types/recommendation";
import type { CommuteLocation } from "./services/commuteService";
import { readLastViewedCommunity, saveLastViewedCommunity, type ViewedCommunityRecord } from "./services/viewedCommunityService";
import { recordDetailView } from "./services/profileService";

function App() {
  const [activePage, setActivePage] = useState<PageId>("login");
  const [selectedArea, setSelectedArea] = useState("安德门片区");
  const [selectedPreferenceId, setSelectedPreferenceId] = useState("");
  const [selectedAreaLocation, setSelectedAreaLocation] = useState<CommuteLocation | null>(null);
  const [currentUsername, setCurrentUsername] = useState("xiaoning");
  const [sessionToken, setSessionToken] = useState("");
  const [lastViewedDetail, setLastViewedDetail] = useState<ViewedCommunityRecord | null>(null);
  const pendingDetailTracking = useRef<Promise<void>>(Promise.resolve());

  const navigate = (page: PageId) => {
    setActivePage(page);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleLogout = () => {
    setSelectedArea("安德门片区");
    setSelectedPreferenceId("");
    setSelectedAreaLocation(null);
    setCurrentUsername("xiaoning");
    setSessionToken("");
    setLastViewedDetail(null);
    pendingDetailTracking.current = Promise.resolve();
    navigate("login");
  };

  const openDetail = (preferenceId: string, areaName: string, areaLocation: CommuteLocation | null) => {
    const record: ViewedCommunityRecord = {
      username: currentUsername,
      preferenceId,
      areaName,
      areaLocation,
      viewedAt: new Date().toISOString()
    };
    setLastViewedDetail(record);
    saveLastViewedCommunity(record);
    if (sessionToken) {
      pendingDetailTracking.current = recordDetailView(sessionToken, preferenceId, areaName).catch(() => {});
    }
    setSelectedPreferenceId(preferenceId);
    setSelectedArea(areaName);
    setSelectedAreaLocation(areaLocation);
    navigate("analysis");
  };

  return (
    <div className="app">
      <AppHeader
        activePage={activePage}
        onLogout={handleLogout}
        onNavigate={navigate}
        username={currentUsername}
      />
      <main>
        {activePage === "login" && (
          <LoginPage
            onLogin={(username, role, token) => {
              setCurrentUsername(username || "xiaoning");
              setSessionToken(token);
              pendingDetailTracking.current = Promise.resolve();
              navigate(role === "admin" ? "admin" : "recommend");
            }}
          />
        )}
        {activePage === "admin" && <AdminDashboardPage />}
        {activePage === "recommend" && (
          <RecommendPage
            username={currentUsername}
            onOpenProfile={() => navigate("profile")}
            onOpenAnalysis={(preferenceId: string, community: RecommendedArea) => {
              const areaName = community.community_name || community.name;
              openDetail(preferenceId, areaName, {
                name: community.community_name || community.name,
                lng: community.gcj02_lng!,
                lat: community.gcj02_lat!
              });
            }}
            onOpenLastViewedDetail={() => {
              const last = lastViewedDetail?.username === currentUsername
                ? lastViewedDetail
                : readLastViewedCommunity(currentUsername);
              if (!last) return false;
              openDetail(last.preferenceId, last.areaName, last.areaLocation);
              return true;
            }}
          />
        )}
        {activePage === "profile" && (
          <ProfilePage
            username={currentUsername}
            sessionToken={sessionToken}
            waitForDetailTracking={() => pendingDetailTracking.current}
            onOpenRecommendation={() => navigate("recommend")}
            onOpenLastViewedDetail={() => {
              const last = lastViewedDetail?.username === currentUsername
                ? lastViewedDetail
                : readLastViewedCommunity(currentUsername);
              if (!last) return false;
              openDetail(last.preferenceId, last.areaName, last.areaLocation);
              return true;
            }}
            onOpenHistoryRecord={openDetail}
          />
        )}
        {activePage === "analysis" && (
          <AnalysisPage
            areaName={selectedArea}
            areaLocation={selectedAreaLocation}
            preferenceId={selectedPreferenceId}
            onBack={() => navigate("recommend")}
            onOpenProfile={() => navigate("profile")}
            onOpenHistoryRecord={(nextPreferenceId, nextAreaName, nextAreaLocation) => {
              openDetail(nextPreferenceId || selectedPreferenceId, nextAreaName || selectedArea, nextAreaLocation);
            }}
            username={currentUsername}
          />
        )}
      </main>
    </div>
  );
}

export default App;
