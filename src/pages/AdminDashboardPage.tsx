import { useEffect, useRef, useState } from "react";
import {
  getAdminDashboardData,
  recalculateTopAreas,
  type AdminDashboardData,
  type VisitTrendItem
} from "../services/adminService";

type EChartsInstance = {
  setOption: (option: unknown) => void;
  resize: () => void;
  dispose: () => void;
};

let adminEchartsLoadPromise: Promise<void> | null = null;

function loadAdminEcharts() {
  const typedWindow = window as Window & {
    echarts?: {
      init: (element: HTMLElement) => EChartsInstance;
    };
  };
  if (typedWindow.echarts) {
    return Promise.resolve(undefined);
  }
  if (adminEchartsLoadPromise) {
    return adminEchartsLoadPromise;
  }

  adminEchartsLoadPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js";
    script.async = true;
    script.onload = () => {
      if (typedWindow.echarts) {
        resolve();
      } else {
        reject(new Error("ECharts 初始化失败"));
      }
    };
    script.onerror = () => reject(new Error("ECharts 脚本加载失败"));
    document.head.appendChild(script);
  }).catch((error) => {
    adminEchartsLoadPromise = null;
    throw error;
  });

  return adminEchartsLoadPromise;
}

export function AdminDashboardPage() {
  const [dashboardData, setDashboardData] = useState<AdminDashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const refreshDashboard = async () => {
    setIsLoading(true);
    setErrorMessage("");
    try {
      const data = await getAdminDashboardData();
      setDashboardData(data);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "运营数据读取失败，请稍后重试");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refreshDashboard();
  }, []);

  const handleRecalculateTopAreas = async () => {
    setIsRecalculating(true);
    setErrorMessage("");
    try {
      await recalculateTopAreas();
      await refreshDashboard();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "片区推荐统计重置失败，请稍后重试");
    } finally {
      setIsRecalculating(false);
    }
  };

  const leftTopAreas = dashboardData?.topAreas.slice(0, 3) || [];
  const rightTopAreas = dashboardData?.topAreas.slice(3, 6) || [];

  return (
    <section className="admin-dashboard-page">
      <section className="admin-hero-card">
        <div>
          <span className="admin-badge">后台管理页面</span>
          <h1>宁安居运营数据看板</h1>
        </div>
        <button className="outline-orange admin-refresh" disabled={isLoading} onClick={refreshDashboard} type="button">
          {isLoading ? "刷新中..." : "刷新数据"}
        </button>
      </section>

      {errorMessage && <p className="auth-message error admin-error">{errorMessage}</p>}

      <div className="admin-metric-grid">
        <MetricCard
          accent="orange"
          label="当日网站访问量"
          value={dashboardData?.todayMetrics.siteVisits ?? 0}
          note="按登录点击事件统计"
        />
        <MetricCard
          accent="green"
          label="当日新增注册用户"
          value={dashboardData?.todayMetrics.newRegistrations ?? 0}
          note="普通用户注册成功后记录"
        />
        <MetricCard
          accent="blue"
          label="当日片区评价次数"
          value={dashboardData?.todayMetrics.areaEvaluations ?? 0}
          note="点击生成推荐片区后记录"
        />
      </div>

      <section className="admin-chart-card">
        <div className="admin-section-head">
          <h2>近一周网站访问趋势</h2>
        </div>
        <VisitTrendChart items={dashboardData?.visitTrend || []} />
      </section>

      <section className="admin-top-card">
        <div className="admin-section-head">
          <h2>用户评价结果</h2>
          <div className="admin-section-actions">
            <span>最近一周片区推荐 Top6</span>
            <button
              className="outline-orange admin-recalculate"
              disabled={isRecalculating}
              onClick={handleRecalculateTopAreas}
              type="button"
            >
              {isRecalculating ? "计算中..." : "重新计算"}
            </button>
          </div>
        </div>
        <div className="admin-top-grid">
          <TopAreaColumn items={leftTopAreas} />
          <TopAreaColumn items={rightTopAreas} />
        </div>
        {dashboardData?.topAreas.length === 0 && <p className="admin-empty">暂无片区推荐统计数据</p>}
      </section>
    </section>
  );
}

function MetricCard({
  accent,
  label,
  value,
  note
}: {
  accent: "orange" | "green" | "blue";
  label: string;
  value: number;
  note: string;
}) {
  return (
    <article className={`admin-metric-card ${accent}`}>
      <span className="admin-metric-icon" />
      <p>{label}</p>
      <strong>{value}</strong>
      <em>{note}</em>
    </article>
  );
}

function VisitTrendChart({ items }: { items: VisitTrendItem[] }) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [chartError, setChartError] = useState("");

  useEffect(() => {
    if (!chartRef.current || items.length === 0) {
      return;
    }

    let cancelled = false;
    let chart: EChartsInstance | null = null;
    let removeResizeListener: (() => void) | null = null;

    loadAdminEcharts()
      .then(() => {
        const typedWindow = window as Window & {
          echarts?: {
            init: (element: HTMLElement) => EChartsInstance;
          };
        };
        if (cancelled || !chartRef.current || !typedWindow.echarts) return;
        setChartError("");
        const nextChart = typedWindow.echarts.init(chartRef.current);
        chart = nextChart;
        nextChart.setOption({
          color: ["#ff5a12"],
          grid: {
            top: 28,
            right: 22,
            bottom: 34,
            left: 42
          },
          tooltip: {
            trigger: "axis",
            formatter: "{b}<br/>访问量：{c}"
          },
          xAxis: {
            type: "category",
            boundaryGap: false,
            data: items.map((item) => item.label),
            axisLine: { lineStyle: { color: "#eadfd7" } },
            axisLabel: { color: "#8a6a56", fontWeight: 700 }
          },
          yAxis: {
            type: "value",
            minInterval: 1,
            axisLabel: { color: "#8a6a56", fontWeight: 700 },
            splitLine: { lineStyle: { color: "#eadfd7", type: "dashed" } }
          },
          series: [
            {
              name: "访问量",
              type: "line",
              smooth: true,
              symbol: "circle",
              symbolSize: 8,
              lineStyle: { width: 4, color: "#ff5a12" },
              itemStyle: { color: "#ff5a12", borderColor: "#fff", borderWidth: 2 },
              areaStyle: { color: "rgba(255, 90, 18, 0.12)" },
              data: items.map((item) => item.value)
            }
          ]
        });

        const handleResize = () => nextChart.resize();
        window.addEventListener("resize", handleResize);
        removeResizeListener = () => window.removeEventListener("resize", handleResize);
      })
      .catch((error: Error) => {
        if (!cancelled) setChartError(error.message);
      });

    return () => {
      cancelled = true;
      removeResizeListener?.();
      chart?.dispose();
    };
  }, [items]);

  if (items.length === 0) {
    return <div className="admin-line-chart empty">正在读取近一周访问趋势...</div>;
  }
  if (chartError) {
    return <div className="admin-line-chart empty">{chartError}</div>;
  }

  return <div className="admin-line-chart" ref={chartRef} />;
}

function TopAreaColumn({ items }: { items: Array<{ rank: number; name: string; count: number }> }) {
  return (
    <div className="top-area-column">
      {items.map((item) => (
        <article className="top-area-row" key={`${item.rank}-${item.name}`}>
          <strong>{item.rank}</strong>
          <span>片区名称：{item.name}</span>
          <em>被推荐次数：{item.count}次</em>
        </article>
      ))}
    </div>
  );
}
