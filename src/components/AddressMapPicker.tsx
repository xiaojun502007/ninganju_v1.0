import { useEffect, useRef, useState } from "react";
import { loadAmap } from "./AmapRouteMap";
import { recordAmapClientCall } from "../services/amapMetricService";

type AddressMapPickerProps = {
  initialAddress: string;
  onClose: () => void;
  onConfirm: (address: string) => void;
};

type PickedLocation = {
  address: string;
  lng: number;
  lat: number;
};

type SearchCandidate = PickedLocation & { name: string; detail: string };

const NANJING_CENTER = [118.7969, 32.0603];

export function AddressMapPicker({ initialAddress, onClose, onConfirm }: AddressMapPickerProps) {
  const mapElementRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const markerRef = useRef<any>(null);
  const geocoderRef = useRef<any>(null);
  const geolocationRef = useRef<any>(null);
  const placeSearchRef = useRef<any>(null);
  const searchIdRef = useRef(0);
  const mountedRef = useRef(true);
  const [query, setQuery] = useState(initialAddress.trim());
  const [picked, setPicked] = useState<PickedLocation | null>(null);
  const [candidates, setCandidates] = useState<SearchCandidate[]>([]);
  const [isMapReady, setIsMapReady] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [isLocating, setIsLocating] = useState(false);
  const [message, setMessage] = useState("高德地图正在加载…");

  useEffect(() => {
    let cancelled = false;
    mountedRef.current = true;

    loadAmap()
      .then((AMap) => {
        if (cancelled || !mapElementRef.current) return;

        AMap.plugin(["AMap.Geocoder", "AMap.Geolocation", "AMap.PlaceSearch", "AMap.Scale", "AMap.ToolBar"], () => {
          if (cancelled || !mapElementRef.current) return;
          try {
          const map = new AMap.Map(mapElementRef.current, {
            center: NANJING_CENTER,
            zoom: 12,
            viewMode: "2D"
          });
          recordAmapClientCall();
          const geocoder = new AMap.Geocoder({ city: "南京", radius: 500 });
          const geolocation = new AMap.Geolocation({
            enableHighAccuracy: true,
            timeout: 10000,
            zoomToAccuracy: true,
            position: "RB"
          });
          const placeSearch = new AMap.PlaceSearch({ city: "南京", citylimit: true, pageSize: 5 });

          mapRef.current = map;
          geocoderRef.current = geocoder;
          geolocationRef.current = geolocation;
          placeSearchRef.current = placeSearch;
          setIsMapReady(true);
          map.addControl(new AMap.Scale());
          map.addControl(new AMap.ToolBar({ position: { right: "16px", top: "16px" } }));

          map.on("click", (event: any) => {
            choosePoint(AMap, event.lnglat.lng, event.lnglat.lat);
          });

          if (initialAddress.trim()) {
            searchAddress(AMap, initialAddress.trim());
          } else {
            setMessage("可搜索地点、使用当前位置，或直接点击地图选择工作地点");
          }
          } catch (error) {
            setMessage(error instanceof Error ? `地图初始化失败：${error.message}` : "地图初始化失败，请刷新页面重试");
          }
        });
      })
      .catch((error: Error) => { if (!cancelled) setMessage(error.message); });

    return () => {
      cancelled = true;
      mountedRef.current = false;
      searchIdRef.current += 1;
      mapRef.current?.destroy();
      mapRef.current = null;
    };
  }, []);

  const updateMarker = (AMap: any, lng: number, lat: number) => {
    if (!mapRef.current) return;
    if (!markerRef.current) {
      markerRef.current = new AMap.Marker({ position: [lng, lat], anchor: "bottom-center" });
      mapRef.current.add(markerRef.current);
    } else {
      markerRef.current.setPosition([lng, lat]);
    }
    mapRef.current.setZoomAndCenter(16, [lng, lat]);
  };

  const choosePoint = (AMap: any, lng: number, lat: number) => {
    const selectionId = ++searchIdRef.current;
    setCandidates([]);
    updateMarker(AMap, lng, lat);
    setMessage("正在获取该位置的地址…");
    if (geocoderRef.current) recordAmapClientCall();
    geocoderRef.current?.getAddress([lng, lat], (status: string, result: any) => {
      if (!mountedRef.current || selectionId !== searchIdRef.current) return;
      if (status === "complete" && result.info === "OK") {
        const address = result.regeocode?.formattedAddress || `${lng.toFixed(6)},${lat.toFixed(6)}`;
        setPicked({ address, lng, lat });
        setQuery(address);
        setMessage("已选择工作地点，确认后将自动回填地址");
      } else {
        setPicked({ address: `${lng.toFixed(6)},${lat.toFixed(6)}`, lng, lat });
        setMessage("未获得详细地址，将使用该坐标位置");
      }
    });
  };

  const selectCandidate = (AMap: any, candidate: SearchCandidate) => {
    searchIdRef.current += 1;
    setCandidates([]);
    setPicked(candidate);
    setQuery(candidate.address);
    updateMarker(AMap, candidate.lng, candidate.lat);
    setMessage("已选择工作地点，确认后将自动回填地址");
  };

  const searchAddress = (AMap: any, address = query.trim()) => {
    if (!address || !placeSearchRef.current) {
      setMessage("请输入需要搜索的工作地点");
      return;
    }
    const searchId = ++searchIdRef.current;
    setCandidates([]);
    setPicked(null);
    setIsSearching(true);
    setMessage("正在搜索地点…");
    recordAmapClientCall();
    placeSearchRef.current.search(address, (status: string, result: any) => {
      if (!mountedRef.current || searchId !== searchIdRef.current) return;
      const pois = status === "complete" ? result?.poiList?.pois : null;
      const matches: SearchCandidate[] = (Array.isArray(pois) ? pois : [])
        .filter((poi: any) => poi.location && Number.isFinite(Number(poi.location.lng)) && Number.isFinite(Number(poi.location.lat)))
        .map((poi: any) => ({
          name: String(poi.name || address),
          detail: String(poi.address || "南京市"),
          address: String(poi.name || address),
          lng: Number(poi.location.lng),
          lat: Number(poi.location.lat)
        }));
      if (matches.length) {
        setCandidates(matches);
        setIsSearching(false);
        setMessage("请选择与工作地点相符的搜索结果");
        return;
      }

      // 完整街道地址可能不是 POI，此时再用地理编码兜底。
      if (geocoderRef.current) recordAmapClientCall();
      geocoderRef.current?.getLocation(address, (geoStatus: string, geoResult: any) => {
        if (!mountedRef.current || searchId !== searchIdRef.current) return;
        setIsSearching(false);
        const geocodes = geoStatus === "complete" ? geoResult?.geocodes : null;
        const locations: SearchCandidate[] = (Array.isArray(geocodes) ? geocodes : [])
          .filter((item: any) => item.location && Number.isFinite(Number(item.location.lng)) && Number.isFinite(Number(item.location.lat)))
          .slice(0, 5)
          .map((item: any) => ({
            name: String(item.formattedAddress || address),
            detail: String(item.level || "地址"),
            address: String(item.formattedAddress || address),
            lng: Number(item.location.lng),
            lat: Number(item.location.lat)
          }));
        setCandidates(locations);
        setMessage(locations.length ? "请选择与工作地点相符的地址" : "没有找到该地点，请补充更具体的名称或在地图上点选");
      });
    });
  };

  const locateCurrentPosition = () => {
    if (!window.AMap || !geolocationRef.current) {
      setMessage("地图定位服务仍在加载，请稍后再试");
      return;
    }
    setIsLocating(true);
    setMessage("正在获取当前位置，请允许浏览器使用定位权限…");
    recordAmapClientCall();
    geolocationRef.current.getCurrentPosition((status: string, result: any) => {
      if (!mountedRef.current) return;
      setIsLocating(false);
      if (status === "complete" && result.position) {
        choosePoint(window.AMap, result.position.lng, result.position.lat);
      } else {
        setMessage("定位失败，请检查浏览器定位权限，或直接在地图上选择位置");
      }
    });
  };

  return (
    <div className="address-map-backdrop" onMouseDown={onClose} role="presentation">
      <section
        aria-labelledby="address-map-title"
        aria-modal="true"
        className="address-map-dialog"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header>
          <div>
            <h2 id="address-map-title">在地图上确定工作地点</h2>
            <p>定位结果仅用于计算通勤距离和推荐租住片区</p>
          </div>
          <button aria-label="关闭地图定位" onClick={onClose} type="button">×</button>
        </header>

        <div className="address-map-toolbar">
          <label>
            <span aria-hidden="true">⌖</span>
            <input
              aria-label="地图地点搜索"
              onChange={(event) => {
                searchIdRef.current += 1;
                setQuery(event.target.value);
                setCandidates([]);
                setPicked(null);
                setIsSearching(false);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && isMapReady && window.AMap) searchAddress(window.AMap);
              }}
              placeholder="搜索写字楼、园区、学校或地铁站"
              value={query}
            />
          </label>
          <button disabled={!isMapReady || isSearching} onClick={() => window.AMap && searchAddress(window.AMap)} type="button">{isSearching ? "搜索中…" : "搜索"}</button>
          <button className="current-location-action" disabled={!isMapReady || isLocating} onClick={locateCurrentPosition} type="button">
            {isLocating ? "定位中…" : "定位到当前位置"}
          </button>
        </div>

        {candidates.length > 0 && (
          <div className="address-map-candidates" role="listbox" aria-label="地点搜索结果">
            {candidates.map((candidate, index) => (
              <button
                key={`${candidate.lng}-${candidate.lat}-${index}`}
                onClick={() => window.AMap && selectCandidate(window.AMap, candidate)}
                type="button"
              >
                <strong>{candidate.name}</strong><small>{candidate.detail}</small>
              </button>
            ))}
          </div>
        )}

        <div className="address-picker-map" ref={mapElementRef} />
        <div className="address-map-result">
          <div>
            <strong>{picked ? "已选位置" : "定位提示"}</strong>
            <span>{picked?.address || message}</span>
            {picked && <small>{picked.lng.toFixed(6)}, {picked.lat.toFixed(6)}</small>}
          </div>
          <button
            disabled={!picked}
            onClick={() => picked && onConfirm(picked.address)}
            type="button"
          >
            确认并回填地址
          </button>
        </div>
      </section>
    </div>
  );
}
