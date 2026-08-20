import { useEffect, useRef, useState } from "react";
import type { FacilitySummaryItem } from "../services/facilityService";

type EChartsInstance = {
  setOption: (option: unknown) => void;
  resize: () => void;
  dispose: () => void;
};

declare global {
  interface Window {
    echarts?: {
      init: (element: HTMLElement) => EChartsInstance;
    };
  }
}

type FacilityRadarChartProps = {
  items: FacilitySummaryItem[];
  isLoading: boolean;
  errorMessage?: string;
};

let echartsLoadPromise: Promise<void> | null = null;

function loadEcharts() {
  if (window.echarts) {
    return Promise.resolve(undefined);
  }
  if (echartsLoadPromise) {
    return echartsLoadPromise;
  }

  echartsLoadPromise = new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js";
    script.async = true;
    script.onload = () => {
      if (window.echarts) {
        resolve();
      } else {
        reject(new Error("ECharts 初始化失败"));
      }
    };
    script.onerror = () => reject(new Error("ECharts 脚本加载失败"));
    document.head.appendChild(script);
  }).catch((error) => {
    echartsLoadPromise = null;
    throw error;
  });

  return echartsLoadPromise;
}

export function FacilityRadarChart({ items, isLoading, errorMessage = "" }: FacilityRadarChartProps) {
  const chartRef = useRef<HTMLDivElement | null>(null);
  const [chartError, setChartError] = useState("");

  useEffect(() => {
    if (!chartRef.current || isLoading || errorMessage || items.length === 0) {
      return;
    }

    let cancelled = false;
    let chart: EChartsInstance | null = null;
    let removeResizeListener: (() => void) | null = null;

    loadEcharts()
      .then(() => {
        if (cancelled || !chartRef.current || !window.echarts) return;
        setChartError("");
        const nextChart = window.echarts.init(chartRef.current);
        chart = nextChart;
        nextChart.setOption({
          color: ["#ff5a12"],
          radar: {
            radius: "70%",
            center: ["50%", "53%"],
            splitNumber: 4,
            indicator: items.map((item) => ({
              name: `${item.facilityName}\n${item.score}`,
              max: 100
            })),
            axisName: {
              color: "#111827",
              fontSize: 14,
              fontWeight: 700
            },
            splitArea: {
              areaStyle: {
                color: ["rgba(255, 246, 238, 0.65)", "rgba(255, 255, 255, 0.75)"]
              }
            },
            axisLine: {
              lineStyle: { color: "#eadfd7" }
            },
            splitLine: {
              lineStyle: { color: "#eadfd7" }
            }
          },
          series: [
            {
              type: "radar",
              data: [
                {
                  value: items.map((item) => item.score),
                  name: "本片区得分",
                  areaStyle: { color: "rgba(255, 90, 18, 0.18)" },
                  lineStyle: { color: "#ff5a12", width: 3 },
                  symbol: "circle",
                  symbolSize: 6
                }
              ]
            }
          ],
          tooltip: {
            trigger: "item"
          }
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
  }, [errorMessage, isLoading, items]);

  if (isLoading) {
    return <div className="radar-loading">正在查询周边生活圈设施...</div>;
  }
  if (errorMessage || chartError) {
    return <div className="radar-loading error">{errorMessage || chartError}</div>;
  }
  if (items.length === 0) {
    return <div className="radar-loading">暂无生活圈设施评分数据</div>;
  }

  return <div className="facility-radar-chart" ref={chartRef} />;
}
