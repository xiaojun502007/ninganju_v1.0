import { useEffect, useRef, useState } from "react";
import type { CommuteLocation, CommuteSummary } from "../services/commuteService";
import { recordAmapClientCall } from "../services/amapMetricService";

declare global {
  interface Window {
    AMap?: any;
    _AMapSecurityConfig?: {
      securityJsCode: string;
    };
    [key: string]: unknown;
  }
}

type AmapRouteMapProps = {
  workLocation: CommuteLocation | null;
  areaLocation: CommuteLocation | null;
  commute: CommuteSummary | null;
  isLoading: boolean;
};

let amapLoadPromise: Promise<any> | null = null;

function loadAmapScript(jsKey: string, securityCode?: string, attempt = 1): Promise<any> {
  return new Promise((resolve, reject) => {
    const callbackName = `__ninganjuAmapReady_${Date.now()}_${attempt}`;
    const timeoutId = window.setTimeout(() => {
      cleanup();
      reject(new Error("高德地图脚本加载超时"));
    }, 16000);

    const cleanup = () => {
      window.clearTimeout(timeoutId);
      delete window[callbackName];
      script.remove();
    };

    if (securityCode) {
      window._AMapSecurityConfig = { securityJsCode: securityCode };
    }

    window[callbackName] = () => {
      if (window.AMap) {
        cleanup();
        resolve(window.AMap);
      } else {
        cleanup();
        reject(new Error("高德地图初始化失败"));
      }
    };

    const script = document.createElement("script");
    const params = new URLSearchParams({
      v: "2.0",
      key: jsKey,
      plugin: "AMap.Scale,AMap.ToolBar",
      callback: callbackName,
      t: String(Date.now())
    });
    script.src = `https://webapi.amap.com/maps?${params.toString()}`;
    script.async = true;
    script.onerror = () => {
      cleanup();
      reject(new Error("高德地图脚本加载失败"));
    };
    document.head.appendChild(script);
  });
}

export async function loadAmap() {
  if (window.AMap) {
    return Promise.resolve(window.AMap);
  }
  if (amapLoadPromise) {
    return amapLoadPromise;
  }

  const jsKey = import.meta.env.VITE_AMAP_JS_KEY as string | undefined;
  const securityCode = import.meta.env.VITE_AMAP_SECURITY_CODE as string | undefined;
  if (!jsKey || jsKey === "VITE_AMAP_JS_KEY") {
    return Promise.reject(new Error("高德 JS API Key 未配置，请提供真实的 VITE_AMAP_JS_KEY"));
  }

  amapLoadPromise = loadAmapScript(jsKey, securityCode, 1)
    .catch(() => loadAmapScript(jsKey, securityCode, 2))
    .catch((error) => {
      amapLoadPromise = null;
      throw error;
    });
  return amapLoadPromise;
}

export function AmapRouteMap({ workLocation, areaLocation, commute, isLoading }: AmapRouteMapProps) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<any>(null);
  const [mapError, setMapError] = useState("");

  useEffect(() => {
    let cancelled = false;
    if (!mapRef.current || !workLocation || !areaLocation) {
      return;
    }

    loadAmap()
      .then((AMap) => {
        if (cancelled || !mapRef.current) return;
        setMapError("");
        if (mapInstanceRef.current) {
          mapInstanceRef.current.destroy();
        }

        const center = [(workLocation.lng + areaLocation.lng) / 2, (workLocation.lat + areaLocation.lat) / 2];
        const map = new AMap.Map(mapRef.current, {
          center,
          zoom: 12,
          viewMode: "2D"
        });
        recordAmapClientCall();
        mapInstanceRef.current = map;
        map.addControl(new AMap.Scale());
        map.addControl(new AMap.ToolBar({ position: { right: "16px", top: "16px" } }));

        const workIcon = new AMap.Icon({
          size: new AMap.Size(32, 42),
          image: "https://webapi.amap.com/theme/v1.3/markers/n/mark_b.png",
          imageSize: new AMap.Size(32, 42)
        });
        const areaIcon = new AMap.Icon({
          size: new AMap.Size(32, 42),
          image: "https://webapi.amap.com/theme/v1.3/markers/n/mark_r.png",
          imageSize: new AMap.Size(32, 42)
        });

        const workMarker = new AMap.Marker({
          position: [workLocation.lng, workLocation.lat],
          title: "工作地点",
          icon: workIcon,
          label: { content: `<div class="amap-label-chip work">工作地点</div>`, direction: "top" }
        });
        const areaMarker = new AMap.Marker({
          position: [areaLocation.lng, areaLocation.lat],
          title: areaLocation.name || "推荐片区",
          icon: areaIcon,
          label: { content: `<div class="amap-label-chip area">${areaLocation.name || "推荐片区"}</div>`, direction: "top" }
        });
        map.add([workMarker, areaMarker]);

        const routePoints = commute?.polyline || [];
        const routeColor = commute?.mode.includes("公交") || commute?.mode.includes("地铁") ? "#2578e8" : "#ff5a12";
        if (routePoints.length > 1) {
          const polyline = new AMap.Polyline({
            path: routePoints,
            strokeColor: routeColor,
            strokeWeight: 6,
            strokeOpacity: 0.92,
            lineJoin: "round",
            lineCap: "round"
          });
          map.add(polyline);
          map.setFitView([workMarker, areaMarker, polyline], false, [42, 42, 42, 42]);
        } else {
          const guideLine = new AMap.Polyline({
            path: [
              [areaLocation.lng, areaLocation.lat],
              [workLocation.lng, workLocation.lat]
            ],
            strokeColor: "#12a66a",
            strokeWeight: 4,
            strokeOpacity: 0.75,
            strokeStyle: "dashed"
          });
          map.add(guideLine);
          map.setFitView([workMarker, areaMarker, guideLine], false, [42, 42, 42, 42]);
        }
      })
      .catch((error: Error) => {
        if (!cancelled) {
          setMapError(`${error.message}，已显示本地通勤示意图`);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [areaLocation, commute, workLocation]);

  return (
    <section className="map-panel">
      <h2>通勤路线地图</h2>
      <div className="amap-route-box">
        {isLoading && <div className="map-placeholder">正在加载通勤地图...</div>}
        {!isLoading && (!workLocation || !areaLocation) && <div className="map-placeholder">暂无坐标信息</div>}
        {!isLoading && mapError && workLocation && areaLocation && (
          <LocalRouteFallback
            areaName={areaLocation.name || "推荐片区"}
            message={mapError}
            workName={workLocation.address || "工作地点"}
          />
        )}
        {!isLoading && mapError && (!workLocation || !areaLocation) && <div className="map-placeholder">{mapError}</div>}
        <div className={mapError ? "amap-container hidden" : "amap-container"} ref={mapRef} />
      </div>
    </section>
  );
}

function LocalRouteFallback({
  areaName,
  workName,
  message
}: {
  areaName: string;
  workName: string;
  message: string;
}) {
  return (
    <div className="local-route-fallback">
      <div className="local-map-message">{message}</div>
      <svg viewBox="0 0 760 390" role="img" aria-label="本地通勤路线示意图">
        <defs>
          <pattern id="local-grid" width="42" height="42" patternUnits="userSpaceOnUse">
            <path d="M 42 0 L 0 0 0 42" fill="none" stroke="#dce8df" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="760" height="390" fill="#f5faf5" />
        <rect width="760" height="390" fill="url(#local-grid)" />
        <path d="M120,270 C250,210 300,145 420,170 S575,214 642,105" fill="none" stroke="#ff5a12" strokeWidth="10" strokeLinecap="round" />
        <path d="M120,270 C250,210 300,145 420,170 S575,214 642,105" fill="none" stroke="#fff" strokeWidth="2" strokeDasharray="12 12" strokeLinecap="round" opacity="0.65" />
        <circle cx="120" cy="270" r="18" fill="#ff5a12" />
        <circle cx="642" cy="105" r="18" fill="#2578e8" />
        <foreignObject x="52" y="292" width="240" height="56">
          <div className="local-map-label area">{areaName}</div>
        </foreignObject>
        <foreignObject x="548" y="36" width="260" height="56">
          <div className="local-map-label work">{workName}</div>
        </foreignObject>
      </svg>
    </div>
  );
}
