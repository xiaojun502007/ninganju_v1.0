import type { CommuteMode, CommuteSummary } from "../services/commuteService";

type CommuteInfoPanelProps = {
  activeMode: CommuteMode;
  commute: CommuteSummary | null;
  isLoading: boolean;
  errorMessage?: string;
  onModeChange: (mode: CommuteMode) => void;
};

export function CommuteInfoPanel({
  activeMode,
  commute,
  isLoading,
  errorMessage = "",
  onModeChange
}: CommuteInfoPanelProps) {
  return (
    <section className="commute-card dynamic-commute-card">
      <h2>通勤信息</h2>
      <div className="mode-tabs">
        <button
          className={activeMode === "driving" ? "active" : "inactive"}
          disabled={isLoading}
          onClick={() => onModeChange("driving")}
          type="button"
        >
          驾车
        </button>
        <button
          className={activeMode === "transit" ? "active" : "inactive"}
          disabled={isLoading}
          onClick={() => onModeChange("transit")}
          type="button"
        >
          公交/地铁
        </button>
      </div>

      {isLoading ? (
        <p className="commute-status">正在生成通勤路线...</p>
      ) : errorMessage ? (
        <p className="commute-status error">{errorMessage}</p>
      ) : (
        <>
          <dl className="commute-list">
            <div>
              <dt>通勤方式</dt>
              <dd>{commute?.mode || "驾车"}</dd>
            </div>
            <div>
              <dt>预计时间</dt>
              <dd>{commute?.durationMinutes ? `约${commute.durationMinutes}分钟` : "暂未生成"}</dd>
            </div>
            <div>
              <dt>距离</dt>
              <dd>{commute?.distanceKm ? `约${commute.distanceKm}公里` : "暂未生成"}</dd>
            </div>
          </dl>
          <h3>路线摘要</h3>
          <p>{commute?.summary || "路线规划暂不可用，地图中已标注工作地与推荐片区。"}</p>
        </>
      )}
    </section>
  );
}
