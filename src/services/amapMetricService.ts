const LOCAL_API_BASE_URL = "http://127.0.0.1:8787";

export function recordAmapClientCall() {
  if (!new Set(["127.0.0.1", "localhost"]).has(window.location.hostname)) return;
  void fetch(`${LOCAL_API_BASE_URL}/api/metrics/amap-client-call`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
    keepalive: true
  }).catch(() => {
    // A metric failure must not interrupt the map itself.
  });
}
