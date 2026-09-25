from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib import error, parse, request


ROOT_DIR = Path(__file__).resolve().parent
DB_PATH = ROOT_DIR / "ninganju_auth.db"
HOST = "127.0.0.1"
PORT = 8787
COZE_DEFAULT_BASE_URL = "https://api.coze.cn"
COZE_DEFAULT_WORKFLOW_ID = "7684482984275542051"
COZE_DEFAULT_APP_ID = "7684185393868439603"
PROFILE_SESSION_SECONDS = 12 * 60 * 60
_profile_sessions: dict[str, tuple[str, float]] = {}
_profile_session_lock = threading.Lock()


FALLBACK_AREAS: list[dict[str, Any]] = [
    {
        "name": "安德门片区",
        "tagline": "通勤高效，生活便利",
        "reason": "靠近地铁1号线与软件大道方向，能兼顾通勤效率和日常生活便利，适合预算中等、希望减少换乘的来宁青年。",
        "risk": "部分老小区房龄较长，建议实地关注楼栋维护、采光和物业管理情况。",
        "tags": ["地铁1号线", "通勤友好", "生活便利", "租金适中"],
        "source": "fallback",
    },
    {
        "name": "天隆寺片区",
        "tagline": "环境宜居，性价比高",
        "reason": "片区兼具地铁可达性和相对舒适的居住环境，租金压力通常低于核心商圈，适合重视性价比的青年租客。",
        "risk": "大型商业和夜间消费配套相对有限，部分生活需求可能需要前往周边商圈。",
        "tags": ["地铁可达", "环境宜居", "性价比高", "成长区域"],
        "source": "fallback",
    },
    {
        "name": "张府园片区",
        "tagline": "中心区位，配套成熟",
        "reason": "位于主城核心生活圈，商业、医疗、餐饮和公共交通资源密集，适合看重城市便利度和生活丰富度的用户。",
        "risk": "租金水平相对较高，老旧小区比例较大，安静度和停车条件需要重点比较。",
        "tags": ["中心区位", "配套成熟", "地铁换乘", "生活繁华"],
        "source": "fallback",
    },
    {
        "name": "马群片区",
        "tagline": "交通灵活，预算友好",
        "reason": "靠近地铁2号线和多条公交线路，租金相对友好，适合预算有限但仍希望保持跨城通勤灵活性的青年。",
        "risk": "早晚高峰部分道路拥堵明显，实际通勤稳定性需要结合工作地点进一步核验。",
        "tags": ["地铁2号线", "租金友好", "交通便利", "青年优选"],
        "source": "fallback",
    },
]

FALLBACK_GEOLOCATIONS: dict[str, tuple[float, float]] = {
    "东南大学": (118.7956, 32.0568),
    "四牌楼": (118.7956, 32.0568),
    "南京师范大学": (118.9143, 32.1085),
    "仙林": (118.9143, 32.1085),
    "新街口": (118.7840, 32.0415),
    "安德门": (118.7680, 31.9954),
    "天隆寺": (118.7794, 31.9861),
    "张府园": (118.7824, 32.0328),
    "马群": (118.8942, 32.0496),
    "油坊桥": (118.7314, 31.9793),
    "天润城": (118.7238, 32.1457),
    "双龙大道": (118.8241, 31.9377),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def today_key() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def recent_day_keys(days: int = 7) -> list[str]:
    today = datetime.now().date()
    return [(today - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in reversed(range(days))]


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def increment_metric(metric_name: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            insert into operation_metrics (metric_name, metric_date, count)
            values (?, ?, 1)
            on conflict(metric_name, metric_date) do update set count = count + 1
            """,
            (metric_name, today_key()),
        )


def open_amap_url(url: str, timeout: int):
    """Count each outbound AMap Web Service request attempt, including retries."""
    increment_metric("amap_api_call")
    return request.urlopen(url, timeout=timeout)


def record_user_activity(
    username: str, event_type: str, preference_id: str | None = None, area_name: str | None = None
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            insert into user_activity (username, event_type, preference_id, area_name, created_at)
            values (?, ?, ?, ?, ?)
            """,
            (username, event_type, preference_id, area_name, utc_now()),
        )


def create_profile_session(username: str) -> str:
    token = secrets.token_urlsafe(32)
    with _profile_session_lock:
        _profile_sessions[token] = (username, time.time() + PROFILE_SESSION_SECONDS)
    return token


def profile_session_username(auth_header: str) -> str | None:
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header[7:].strip()
    with _profile_session_lock:
        session = _profile_sessions.get(token)
        if not session:
            return None
        username, expires_at = session
        if expires_at <= time.time():
            _profile_sessions.pop(token, None)
            return None
        return username


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            create table if not exists users (
                id integer primary key autoincrement,
                username text not null unique,
                password_hash text not null,
                salt text not null,
                role text not null default 'user',
                created_at text not null
            )
            """
        )
        conn.execute("create index if not exists idx_users_username on users(username)")
        conn.execute(
            """
            create table if not exists rent_preference (
                id text primary key,
                user_nickname text not null default '',
                work_address text not null,
                work_lng real,
                work_lat real,
                budget_min integer not null,
                budget_max integer not null,
                commute_distance_min integer not null default 1,
                commute_distance_max integer not null default 30,
                facility_preferences text not null default '[]',
                transport_preference text not null default '',
                housing_type text not null default '',
                other_demand text not null default '',
                preference_json text not null default '{}',
                commute_range text not null,
                priority text not null,
                markdown_prompt text not null,
                created_at text not null
            )
            """
        )
        columns = {row["name"] for row in conn.execute("pragma table_info(rent_preference)").fetchall()}
        if "work_lng" not in columns:
            conn.execute("alter table rent_preference add column work_lng real")
        if "work_lat" not in columns:
            conn.execute("alter table rent_preference add column work_lat real")
        rent_preference_columns = {
            "user_nickname": "text not null default ''",
            "commute_distance_min": "integer not null default 1",
            "commute_distance_max": "integer not null default 30",
            "facility_preferences": "text not null default '[]'",
            "transport_preference": "text not null default ''",
            "housing_type": "text not null default ''",
            "other_demand": "text not null default ''",
            "preference_json": "text not null default '{}'",
        }
        for column_name, column_definition in rent_preference_columns.items():
            if column_name not in columns:
                conn.execute(f"alter table rent_preference add column {column_name} {column_definition}")
        conn.execute(
            "create index if not exists idx_rent_preference_user_created on rent_preference(user_nickname, created_at)"
        )
        conn.execute(
            """
            create table if not exists recommendation_result (
                id text primary key,
                preference_id text not null,
                areas_json text not null,
                raw_response text,
                source text not null,
                created_at text not null,
                foreign key (preference_id) references rent_preference(id)
            )
            """
        )
        conn.execute(
            """
            create table if not exists facility_poi_raw (
                id text primary key,
                preference_id text,
                area_name text not null,
                area_lng real not null,
                area_lat real not null,
                raw_json text not null,
                created_at text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists facility_evaluation (
                id text primary key,
                preference_id text,
                area_name text not null,
                facility_name text not null,
                count integer not null,
                score integer not null,
                nearest_distance integer,
                examples_json text not null,
                created_at text not null
            )
            """
        )
        conn.execute(
            """
            create table if not exists evaluation_history (
                id text primary key,
                username text not null,
                region_name text not null,
                total_score integer not null,
                commute_score integer not null,
                facility_score integer not null,
                time text not null,
                other_info text not null
            )
            """
        )
        conn.execute("create index if not exists idx_evaluation_history_user_time on evaluation_history(username, time)")
        conn.execute(
            """
            create table if not exists user_activity (
                id integer primary key autoincrement,
                username text not null,
                event_type text not null,
                preference_id text,
                area_name text,
                created_at text not null
            )
            """
        )
        conn.execute(
            "create index if not exists idx_user_activity_user_type on user_activity(username, event_type, created_at)"
        )
        conn.execute(
            """
            create table if not exists user_login (
                id integer primary key autoincrement,
                username text not null,
                login_time text not null,
                unique(username, login_time)
            )
            """
        )
        conn.execute("create index if not exists idx_user_login_time on user_login(login_time desc, id desc)")
        conn.execute(
            """
            insert or ignore into user_login (username, login_time)
            select username, created_at from user_activity where event_type = 'login'
            """
        )
        conn.execute(
            """
            create table if not exists operation_metrics (
                id integer primary key autoincrement,
                metric_name text not null,
                metric_date text not null,
                count integer not null default 0,
                unique(metric_name, metric_date)
            )
            """
        )
        conn.execute("create index if not exists idx_operation_metrics_date on operation_metrics(metric_name, metric_date)")
        conn.execute(
            """
            create table if not exists admin_settings (
                key text primary key,
                value text not null
            )
            """
        )
        demo_salt = "ninganju-demo-user"
        conn.execute(
            """
            insert into users (username, password_hash, salt, role, created_at)
            values (?, ?, ?, 'user', ?)
            on conflict(username) do nothing
            """,
            ("xiaoning", hash_password("12345678", demo_salt), demo_salt, utc_now()),
        )
        admin_salt = "ninganju-admin-user"
        conn.execute(
            """
            insert into users (username, password_hash, salt, role, created_at)
            values (?, ?, ?, 'admin', ?)
            on conflict(username) do nothing
            """,
            ("administrator", hash_password("220250246@xj", admin_salt), admin_salt, utc_now()),
        )


def hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 260_000)
    return f"pbkdf2_sha256${digest.hex()}"


def verify_password(password: str, salt: str, stored_hash: str) -> bool:
    if stored_hash.startswith("pbkdf2_sha256$"):
        return hmac.compare_digest(hash_password(password, salt), stored_hash)
    legacy_hash = hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_hash, stored_hash)


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    origin = handler.headers.get("Origin", "http://127.0.0.1:5173")
    allowed_origin = origin if origin in {"http://127.0.0.1:5173", "http://localhost:5173"} else "http://127.0.0.1:5173"
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", allowed_origin)
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
    handler.end_headers()
    handler.wfile.write(body)


def parse_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length).decode("utf-8")
    return json.loads(raw)


def validate_username(username: str) -> str | None:
    if not username:
        return "请输入用户名"
    if len(username) > 16:
        return "用户名长度不得超过16位"
    return None


def validate_preference(data: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    user_nickname = str(data.get("user_nickname", data.get("userNickname", ""))).strip()
    work_address = str(data.get("work_address", data.get("workAddress", ""))).strip()
    facility_preferences = data.get("facility_preferences", [])
    transport_preference = str(data.get("transport_preference", "")).strip()
    housing_type = str(data.get("housing_type", "")).strip()
    try:
        budget_min = int(data.get("budget_min", data.get("budgetMin", 0)))
        budget_max = int(data.get("budget_max", data.get("budgetMax", 0)))
        commute_distance_min = int(data.get("commute_distance_min", 0))
        commute_distance_max = int(data.get("commute_distance_max", 0))
    except (TypeError, ValueError):
        return None, "租金预算和通勤距离必须是数字"

    if not user_nickname:
        return None, "缺少登录用户名"
    if not work_address:
        return None, "请填写工作地址"
    if budget_min < 500 or budget_max <= budget_min:
        return None, "请填写有效的月租预算区间"
    if commute_distance_min < 1 or commute_distance_max <= commute_distance_min:
        return None, "请填写有效的通勤距离区间"
    if not isinstance(facility_preferences, list) or not facility_preferences:
        return None, "请至少选择一项周边设施"
    facility_preferences = [str(item).strip() for item in facility_preferences if str(item).strip()]
    if not facility_preferences:
        return None, "请至少选择一项周边设施"
    if transport_preference not in {"步行", "自行车/电动车", "公交车", "地铁", "自驾/打车"}:
        return None, "请选择上下班交通方式"
    if housing_type not in {"单身公寓", "一居室普通住宅", "两居室普通住宅"}:
        return None, "请选择期望租住的房型"

    if commute_distance_max <= 3:
        commute_range = "3km"
    elif commute_distance_max <= 5:
        commute_range = "5km"
    elif commute_distance_max <= 10:
        commute_range = "10km"
    elif commute_distance_max <= 15:
        commute_range = "15km"
    else:
        commute_range = "15km+"

    return {
        "user_nickname": user_nickname,
        "work_address": work_address,
        "budget_max": budget_max,
        "budget_min": budget_min,
        "commute_distance_max": commute_distance_max,
        "commute_distance_min": commute_distance_min,
        "facility_preferences": facility_preferences,
        "transport_preference": transport_preference,
        "housing_type": housing_type,
        "commute_range": commute_range,
        "priority": "靠近工作地",
    }, None


def build_recommend_prompt(preference: dict[str, Any]) -> str:
    return f"""# 宁安居租住片区推荐任务

请基于来宁青年租房需求，推荐 3 个南京真实租住片区或生活圈，依次对应通勤优先、均衡、性价比优先方案。

## 用户偏好
- 用户名：{preference["user_nickname"]}
- 工作地址：{preference["work_address"]}
- 月租预算：{preference["budget_min"]}-{preference["budget_max"]} 元/月
- 可接受通勤距离：{preference["commute_distance_min"]}-{preference["commute_distance_max"]} km
- 周边设施偏好：{"、".join(preference["facility_preferences"])}
- 上下班交通方式：{preference["transport_preference"]}
- 期望租住的房型：{preference["housing_type"]}

## 输出约束
1. 不推荐具体房源、具体小区房号或中介信息。
2. 不编造精确租金，只描述片区适配性。
3. 必须返回严格 JSON，不要输出 Markdown 或解释文字。
4. JSON 格式为：{{"areas":[{{"name":"片区名称","tagline":"一句话推荐标签","reason":"推荐理由","risk":"风险提示","tags":["标签1","标签2","标签3"]}}]}}
5. areas 必须正好 3 条，顺序依次为通勤优先、均衡、性价比优先。
"""


def amap_key() -> str:
    return os.getenv("AMAP_WEB_SERVICE_KEY", "").strip()


def facility_amap_key() -> str:
    return os.getenv("AMAP_FACILITY_SEARCH_KEY", "").strip() or amap_key()


def geocode_address(address: str) -> dict[str, Any] | None:
    key = amap_key()
    fallback = fallback_geocode(address)
    if not key or not address:
        return fallback

    params = parse.urlencode({"key": key, "address": address, "city": "南京"})
    url = f"https://restapi.amap.com/v3/geocode/geo?{params}"
    try:
        with open_amap_url(url, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return fallback

    geocodes = payload.get("geocodes")
    if payload.get("status") != "1" or not isinstance(geocodes, list) or not geocodes:
        return fallback

    location = str(geocodes[0].get("location", ""))
    try:
        lng_text, lat_text = location.split(",", 1)
        return {"address": address, "lng": float(lng_text), "lat": float(lat_text)}
    except (ValueError, AttributeError):
        return fallback


def fallback_geocode(address: str) -> dict[str, Any] | None:
    if not address:
        return None
    for keyword, (lng, lat) in FALLBACK_GEOLOCATIONS.items():
        if keyword in address:
            return {"address": address, "lng": lng, "lat": lat}
    return None


def normalize_area_geocode_name(area_name: str) -> str:
    normalized = area_name.strip()
    suffixes = [
        "地铁站周边生活圈",
        "站周边生活圈",
        "周边生活圈",
        "地铁站周边",
        "站周边",
        "生活圈",
        "片区",
        "板块",
        "商圈",
        "周边",
    ]
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if normalized.endswith(suffix) and len(normalized) > len(suffix):
                normalized = normalized[: -len(suffix)].strip(" \t\n\r-—：:")
                changed = True
    return normalized or area_name.strip()



TRUSTED_NANJING_LOCATIONS: dict[str, tuple[float, float]] = {
    "\u4e1c\u5357\u5927\u5b66": (118.7956, 32.0568),
    "\u56db\u724c\u697c": (118.7956, 32.0568),
    "\u5357\u4eac\u5e08\u8303\u5927\u5b66": (118.9143, 32.1085),
    "\u4ed9\u6797": (118.9143, 32.1085),
    "\u4ed9\u6797\u5927\u5b66\u57ce": (118.9120, 32.1030),
    "\u65b0\u8857\u53e3": (118.7840, 32.0415),
    "\u5b89\u5fb7\u95e8": (118.7680, 31.9954),
    "\u5929\u9686\u5bfa": (118.7794, 31.9861),
    "\u5f20\u5e9c\u56ed": (118.7824, 32.0328),
    "\u9a6c\u7fa4": (118.8942, 32.0496),
    "\u6cb9\u574a\u6865": (118.7314, 31.9793),
    "\u5929\u6da6\u57ce": (118.7238, 32.1457),
    "\u53cc\u9f99\u5927\u9053": (118.8241, 31.9377),
    "\u9e21\u9e23\u5bfa": (118.8010, 32.0606),
    "\u73e0\u6c5f\u8def": (118.7850, 32.0570),
    "\u9f13\u697c": (118.7700, 32.0660),
    "\u592b\u5b50\u5e99": (118.7890, 32.0210),
    "\u660e\u6545\u5bab": (118.8120, 32.0400),
    "\u5357\u4eac\u5357\u7ad9": (118.7969, 31.9707),
    "\u8f6f\u4ef6\u8c37": (118.7480, 31.9790),
    "\u6cb3\u897f": (118.7360, 32.0130),
    "\u5965\u4f53": (118.7240, 32.0040),
    "\u5c0f\u884c": (118.7460, 31.9940),
    "\u96e8\u82b1\u53f0": (118.7790, 31.9950),
    "\u8fc8\u768b\u6865": (118.8080, 32.1020),
    "\u767e\u5bb6\u6e56": (118.8207, 31.9295),
    "\u6c5f\u5b81\u5927\u5b66\u57ce": (118.8760, 31.9090),
    "\u6c5f\u6d66": (118.6270, 32.0590),
    "\u6d66\u53e3": (118.6270, 32.0590),
    "\u6865\u5317": (118.7420, 32.1560),
    "\u5927\u5382": (118.7560, 32.2080),
    "\u9e92\u9e9f\u95e8": (118.9080, 32.0200),
    "\u671d\u5929\u5bab": (118.7757, 32.0345),
    "\u745e\u91d1\u8def": (118.8060, 32.0350),
    "\u5357\u6e56": (118.7590, 32.0260),
    "\u4e94\u8001\u6751": (118.7920, 32.0400),
    "\u7384\u6b66\u95e8": (118.7820, 32.0700),
    "\u5e38\u5e9c\u8857": (118.7930, 32.0340),
    "\u83ab\u6101\u6e56": (118.7580, 32.0350),
    "\u6c49\u4e2d\u95e8": (118.7640, 32.0460),
    "\u4e09\u5c71\u8857": (118.7830, 32.0220),
    "\u4e2d\u534e\u95e8": (118.7810, 32.0060),
    "\u5927\u884c\u5bab": (118.7920, 32.0450),
    "\u4e39\u51e4\u8857": (118.7860, 32.0630),
    "\u6885\u56ed\u65b0\u6751": (118.8060, 32.0460),
    "\u9501\u91d1\u6751": (118.8150, 32.0800),
    "\u82b1\u56ed\u8def": (118.8290, 32.0860),
    "\u6708\u82d1": (118.8290, 32.1020),
    "\u7ea2\u5c71": (118.8030, 32.1050),
    "\u65b0\u5e84": (118.8070, 32.0730),
    "\u5c97\u5b50\u6751": (118.8070, 32.0660),
    "\u79d1\u5df7": (118.7900, 32.0410),
    "\u4e0a\u5143\u95e8": (118.7580, 32.1160),
    "\u5b5d\u9675\u536b": (118.8490, 32.0430),
    "\u82dc\u84ff\u56ed": (118.7800, 32.0610),
    "\u5c27\u5316\u95e8": (118.8840, 32.1130),
    "\u71d5\u5b50\u77f6": (118.8050, 32.1470),
    "\u5e55\u5e9c\u5c71": (118.7810, 32.1210),
    "\u8349\u573a\u95e8": (118.7540, 32.0660),
    "\u9f99\u6c5f": (118.7440, 32.0640),
    "\u4e91\u9526\u8def": (118.7370, 32.0350),
    "\u6c5f\u5fc3\u6d32": (118.6970, 32.0200),
    "\u4e2d\u80dc": (118.7290, 31.9950),
    "\u5143\u901a": (118.7240, 31.9990),
    "\u6cb3\u5b9a\u6865": (118.8210, 31.9490),
    "\u7af9\u5c71\u8def": (118.8430, 31.9460),
    "\u4e1c\u5c71": (118.8500, 31.9520),
    "\u5c94\u8def\u53e3": (118.8070, 31.9700),
    "\u80dc\u592a\u8def": (118.8190, 31.9300),
    "\u8bda\u4fe1\u5927\u9053": (118.8570, 31.8990),
    "\u4e5d\u9f99\u6e56": (118.8210, 31.8870),
    "\u79e3\u5468\u4e1c\u8def": (118.8870, 31.8500),
    "\u67f3\u6d32\u4e1c\u8def": (118.7370, 32.1380),
    "\u6cf0\u5c71\u65b0\u6751": (118.7140, 32.1450),
    "\u845b\u5858": (118.7480, 32.2410),
    "\u5b66\u5219\u8def": (118.9230, 32.1040),
    "\u7f8a\u5c71\u516c\u56ed": (118.9340, 32.1100),
    "\u7ecf\u5929\u8def": (118.9600, 32.1160),
}


def fallback_geocode(address: str) -> dict[str, Any] | None:
    if not address:
        return None
    for keyword, (lng, lat) in TRUSTED_NANJING_LOCATIONS.items():
        if keyword in address:
            return {"address": address, "lng": lng, "lat": lat, "source": "trusted"}
    for keyword, (lng, lat) in FALLBACK_GEOLOCATIONS.items():
        if keyword in address:
            return {"address": address, "lng": lng, "lat": lat, "source": "fallback"}
    return None


def normalize_area_geocode_name(area_name: str) -> str:
    normalized = area_name.strip()
    bracket_tokens = [
        "\u3010\u7247\u533a\u3011",
        "\u3010\u677f\u5757\u3011",
        "\u3010\u5546\u5708\u3011",
        "\u3010\u751f\u6d3b\u5708\u3011",
        "\uff08\u7247\u533a\uff09",
        "\uff08\u677f\u5757\uff09",
        "\uff08\u5546\u5708\uff09",
        "\uff08\u751f\u6d3b\u5708\uff09",
        "(\u7247\u533a)",
        "(\u677f\u5757)",
        "(\u5546\u5708)",
        "(\u751f\u6d3b\u5708)",
        "[\u7247\u533a]",
        "[\u677f\u5757]",
        "[\u5546\u5708]",
        "[\u751f\u6d3b\u5708]",
    ]
    for token in bracket_tokens:
        normalized = normalized.replace(token, "")
    normalized = normalized.strip(" \t\n\r-\u2014\uff1a:\u3010\u3011[]()\uff08\uff09")
    if normalized.startswith("\u5357\u4eac\u5e02") and len(normalized) > 3:
        normalized = normalized[3:].strip()
    return normalized or area_name.strip()


def area_core_keyword(area_name: str) -> str:
    keyword = normalize_area_geocode_name(area_name)
    suffixes = [
        "\u5730\u94c1\u7ad9\u5468\u8fb9\u751f\u6d3b\u5708",
        "\u7ad9\u5468\u8fb9\u751f\u6d3b\u5708",
        "\u5468\u8fb9\u751f\u6d3b\u5708",
        "\u5730\u94c1\u7ad9\u5468\u8fb9",
        "\u7ad9\u5468\u8fb9",
        "\u751f\u6d3b\u5708",
        "\u7247\u533a",
        "\u677f\u5757",
        "\u5546\u5708",
        "\u5468\u8fb9",
    ]
    for suffix in suffixes:
        if keyword.endswith(suffix) and len(keyword) > len(suffix):
            return keyword[: -len(suffix)].strip(" \t\n\r-\u2014\uff1a:") or keyword
    return keyword


def is_in_nanjing_bounds(lng: float, lat: float) -> bool:
    return 118.25 <= lng <= 119.25 and 31.35 <= lat <= 32.65


def score_poi_candidate(keyword: str, poi: dict[str, Any]) -> int:
    core = area_core_keyword(keyword)
    name = str(poi.get("name", "")).strip()
    address = str(poi.get("address", "")).strip()
    adname = str(poi.get("adname", "")).strip()
    type_text = str(poi.get("type", "")).strip()
    score = 0

    if name == keyword:
        score += 120
    elif keyword and keyword in name:
        score += 88
    if core and core != keyword:
        if name == core:
            score += 105
        elif core in name:
            score += 78
        if core in address:
            score += 36
    if keyword and keyword in address:
        score += 42
    if adname:
        score += 8
    if any(token in type_text for token in ["\u5730\u540d\u5730\u5740", "\u4ea4\u901a\u8bbe\u65bd", "\u5546\u52a1\u4f4f\u5b85", "\u98ce\u666f\u540d\u80dc"]):
        score += 14
    if any(token in name + address + type_text for token in ["\u505c\u8f66\u573a", "\u516c\u53f8", "\u9152\u5e97", "ATM", "\u5395\u6240", "\u7ef4\u4fee", "\u5e7f\u544a"]):
        score -= 45
    return score


def search_poi_location(keyword: str) -> dict[str, Any] | None:
    key = amap_key()
    normalized = keyword.strip()
    if not key or not normalized:
        return None

    params = parse.urlencode(
        {
            "key": key,
            "keywords": normalized,
            "city": "\u5357\u4eac",
            "citylimit": "true",
            "offset": "20",
            "page": "1",
            "extensions": "base",
        }
    )
    url = f"https://restapi.amap.com/v3/place/text?{params}"
    try:
        with open_amap_url(url, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    pois = payload.get("pois")
    if payload.get("status") != "1" or not isinstance(pois, list):
        return None

    candidates: list[dict[str, Any]] = []
    for poi in pois:
        if not isinstance(poi, dict):
            continue
        location = str(poi.get("location", ""))
        city_name = str(poi.get("cityname", ""))
        province_name = str(poi.get("pname", ""))
        if "\u5357\u4eac" not in city_name and "\u6c5f\u82cf" not in province_name:
            continue
        try:
            lng_text, lat_text = location.split(",", 1)
            lng = float(lng_text)
            lat = float(lat_text)
            if not is_in_nanjing_bounds(lng, lat):
                continue
            score = score_poi_candidate(normalized, poi)
            if score < 30:
                continue
            candidates.append({
                "address": normalized,
                "lng": lng,
                "lat": lat,
                "source": "poi",
                "poiName": str(poi.get("name", "")),
                "score": score,
            })
        except (ValueError, AttributeError):
            continue
    if candidates:
        candidates.sort(key=lambda item: item["score"], reverse=True)
        return candidates[0]
    return None


def geocode_address(address: str) -> dict[str, Any] | None:
    key = amap_key()
    fallback = fallback_geocode(address)
    if not key or not address:
        return fallback

    params = parse.urlencode({"key": key, "address": address, "city": "\u5357\u4eac"})
    url = f"https://restapi.amap.com/v3/geocode/geo?{params}"
    try:
        with open_amap_url(url, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return search_poi_location(address) or fallback

    geocodes = payload.get("geocodes")
    if payload.get("status") != "1" or not isinstance(geocodes, list) or not geocodes:
        return search_poi_location(address) or fallback

    location = str(geocodes[0].get("location", ""))
    try:
        lng_text, lat_text = location.split(",", 1)
        return {"address": address, "lng": float(lng_text), "lat": float(lat_text), "source": "geocode"}
    except (ValueError, AttributeError):
        return search_poi_location(address) or fallback


def geocode_area_location(area_name: str) -> dict[str, Any] | None:
    query = normalize_area_geocode_name(area_name)
    trusted = fallback_geocode(query) or fallback_geocode(area_name)
    if trusted:
        return {
            "name": area_name,
            "lng": trusted["lng"],
            "lat": trusted["lat"],
            "source": trusted.get("source", "trusted"),
            "query": query,
        }

    poi = search_poi_location(query)
    if poi:
        return {
            "name": area_name,
            "lng": poi["lng"],
            "lat": poi["lat"],
            "source": "poi",
            "query": query,
            "matchedName": poi.get("poiName", ""),
        }

    core_query = area_core_keyword(query)
    if core_query != query:
        core_trusted = fallback_geocode(core_query)
        if core_trusted:
            return {
                "name": area_name,
                "lng": core_trusted["lng"],
                "lat": core_trusted["lat"],
                "source": core_trusted.get("source", "trusted"),
                "query": query,
                "matchedName": core_query,
            }
        core_poi = search_poi_location(core_query)
        if core_poi:
            return {
                "name": area_name,
                "lng": core_poi["lng"],
                "lat": core_poi["lat"],
                "source": "poi",
                "query": query,
                "matchedName": core_poi.get("poiName", core_query),
            }

    geocoded = geocode_address(f"\u5357\u4eac\u5e02{query}")
    if geocoded:
        return {
            "name": area_name,
            "lng": geocoded["lng"],
            "lat": geocoded["lat"],
            "source": geocoded.get("source", "geocode"),
            "query": query,
        }
    return None


def parse_polyline(polyline: str) -> list[list[float]]:
    points: list[list[float]] = []
    for item in polyline.split(";"):
        if not item:
            continue
        try:
            lng_text, lat_text = item.split(",", 1)
            points.append([float(lng_text), float(lat_text)])
        except ValueError:
            continue
    return points


def get_driving_route(origin: str, destination: str) -> dict[str, Any] | None:
    key = amap_key()
    if not key:
        return None

    params = parse.urlencode({"key": key, "origin": origin, "destination": destination, "extensions": "all"})
    url = f"https://restapi.amap.com/v3/direction/driving?{params}"
    try:
        with open_amap_url(url, timeout=16) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    paths = payload.get("route", {}).get("paths")
    if payload.get("status") != "1" or not isinstance(paths, list) or not paths:
        return None

    path = paths[0]
    try:
        duration_minutes = max(1, round(float(path.get("duration", 0)) / 60))
        distance_km = round(float(path.get("distance", 0)) / 1000, 1)
    except (TypeError, ValueError):
        duration_minutes = 0
        distance_km = 0

    steps = path.get("steps") if isinstance(path.get("steps"), list) else []
    first_roads = [
        str(step.get("road") or step.get("instruction") or "").strip()
        for step in steps[:3]
        if isinstance(step, dict) and str(step.get("road") or step.get("instruction") or "").strip()
    ]
    polyline: list[list[float]] = []
    for step in steps:
        if isinstance(step, dict):
            polyline.extend(parse_polyline(str(step.get("polyline") or "")))

    summary = "驾车路线已生成，具体路线可在地图中查看"
    if first_roads:
        summary = "途经：" + " → ".join(first_roads[:3])

    return {
        "mode": "驾车",
        "routeName": "驾车通勤",
        "durationMinutes": duration_minutes,
        "distanceKm": distance_km,
        "transferCount": 0,
        "summary": summary,
        "polyline": polyline,
    }


def get_transit_route(origin: str, destination: str) -> dict[str, Any] | None:
    key = amap_key()
    if not key:
        return None

    params = parse.urlencode(
        {
            "key": key,
            "origin": origin,
            "destination": destination,
            "city": "\u5357\u4eac",
            "cityd": "\u5357\u4eac",
            "strategy": "0",
            "extensions": "all",
        }
    )
    url = f"https://restapi.amap.com/v3/direction/transit/integrated?{params}"
    try:
        with open_amap_url(url, timeout=18) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    route = payload.get("route")
    transits = route.get("transits") if isinstance(route, dict) else None
    if payload.get("status") != "1" or not isinstance(transits, list) or not transits:
        return None

    transit = transits[0]
    if not isinstance(transit, dict):
        return None

    try:
        duration_minutes = max(1, round(float(transit.get("duration", 0)) / 60))
    except (TypeError, ValueError):
        duration_minutes = None
    try:
        distance_km = round(float(transit.get("distance") or route.get("distance") or 0) / 1000, 1)
    except (TypeError, ValueError, AttributeError):
        distance_km = None

    polyline: list[list[float]] = []
    line_names: list[str] = []
    busline_count = 0
    walking_distance = str(transit.get("walking_distance") or "").strip()
    segments = transit.get("segments") if isinstance(transit.get("segments"), list) else []

    for segment in segments:
        if not isinstance(segment, dict):
            continue

        walking = segment.get("walking")
        if isinstance(walking, dict):
            steps = walking.get("steps") if isinstance(walking.get("steps"), list) else []
            for step in steps:
                if isinstance(step, dict):
                    polyline.extend(parse_polyline(str(step.get("polyline") or "")))

        bus = segment.get("bus")
        buslines = bus.get("buslines") if isinstance(bus, dict) and isinstance(bus.get("buslines"), list) else []
        for busline in buslines:
            if not isinstance(busline, dict):
                continue
            busline_count += 1
            line_name = str(busline.get("name") or "").strip()
            if line_name:
                line_names.append(line_name.split("(", 1)[0])
            polyline.extend(parse_polyline(str(busline.get("polyline") or "")))

    transfer_count = max(0, busline_count - 1)
    if line_names:
        summary = "\u516c\u5171\u4ea4\u901a\u63a8\u8350\uff1a" + " \u2192 ".join(line_names[:4])
    elif walking_distance:
        summary = f"\u516c\u4ea4/\u5730\u94c1\u8def\u7ebf\u5df2\u751f\u6210\uff0c\u6b65\u884c\u8ddd\u79bb\u7ea6{walking_distance}\u7c73"
    else:
        summary = "\u516c\u4ea4/\u5730\u94c1\u8def\u7ebf\u5df2\u751f\u6210\uff0c\u5177\u4f53\u8def\u7ebf\u53ef\u5728\u5730\u56fe\u4e2d\u67e5\u770b"

    return {
        "mode": "\u516c\u4ea4/\u5730\u94c1",
        "routeName": "\u516c\u5171\u4ea4\u901a\u901a\u52e4",
        "durationMinutes": duration_minutes,
        "distanceKm": distance_km,
        "transferCount": transfer_count,
        "summary": summary,
        "polyline": polyline,
    }


def clamp_score(score: float) -> int:
    return max(0, min(100, round(score)))


def get_transit_time_score(minutes: int | float) -> int:
    if minutes <= 25:
        return 100
    if minutes <= 35:
        return 90
    if minutes <= 45:
        return 80
    if minutes <= 60:
        return 65
    if minutes <= 75:
        return 50
    if minutes <= 90:
        return 35
    return 20


def get_driving_time_score(minutes: int | float) -> int:
    if minutes <= 15:
        return 100
    if minutes <= 25:
        return 90
    if minutes <= 35:
        return 80
    if minutes <= 50:
        return 65
    if minutes <= 65:
        return 50
    if minutes <= 80:
        return 35
    return 20


def get_commute_distance_score(distance_km: int | float) -> int:
    if distance_km <= 3:
        return 100
    if distance_km <= 5:
        return 90
    if distance_km <= 8:
        return 80
    if distance_km <= 12:
        return 70
    if distance_km <= 16:
        return 55
    if distance_km <= 20:
        return 40
    return 25


def get_transfer_score(transfer_count: int) -> int:
    if transfer_count == 0:
        return 100
    if transfer_count == 1:
        return 85
    if transfer_count == 2:
        return 65
    if transfer_count == 3:
        return 45
    return 25


def valid_commute_metrics(commute: dict[str, Any] | None, needs_transfer: bool = False) -> bool:
    if not commute:
        return False
    if commute.get("durationMinutes") is None or commute.get("distanceKm") is None:
        return False
    if needs_transfer and commute.get("transferCount") is None:
        return False
    return True


def calculate_transit_score(transit: dict[str, Any] | None) -> dict[str, Any] | None:
    if not valid_commute_metrics(transit, needs_transfer=True):
        return None
    duration = float(transit["durationMinutes"])
    distance = float(transit["distanceKm"])
    transfer_count = int(transit.get("transferCount") or 0)
    time_score = get_transit_time_score(duration)
    distance_score = get_commute_distance_score(distance)
    transfer_score = get_transfer_score(transfer_count)
    score = time_score * 0.6 + distance_score * 0.2 + transfer_score * 0.2
    return {
        "score": clamp_score(score),
        "timeScore": time_score,
        "distanceScore": distance_score,
        "transferScore": transfer_score,
    }


def calculate_driving_score(driving: dict[str, Any] | None) -> dict[str, Any] | None:
    if not valid_commute_metrics(driving):
        return None
    duration = float(driving["durationMinutes"])
    distance = float(driving["distanceKm"])
    time_score = get_driving_time_score(duration)
    distance_score = get_commute_distance_score(distance)
    score = time_score * 0.7 + distance_score * 0.3
    return {
        "score": clamp_score(score),
        "timeScore": time_score,
        "distanceScore": distance_score,
    }


def get_commute_level(score: int) -> str:
    if score > 90:
        return "\u901a\u52e4\u6548\u7387\u4f18\u79c0"
    if score >= 75:
        return "\u901a\u52e4\u6548\u7387\u826f\u597d"
    if score >= 60:
        return "\u901a\u52e4\u6548\u7387\u4e2d\u7b49"
    return "\u901a\u52e4\u6548\u7387\u4e0d\u4f73"


def build_commute_tags(score: int, transit: dict[str, Any] | None, driving: dict[str, Any] | None) -> list[str]:
    tags: list[str] = []
    if score >= 80:
        tags.append("\u901a\u52e4\u53cb\u597d")
    elif score >= 60:
        tags.append("\u57fa\u672c\u53ef\u901a\u52e4")
    else:
        tags.append("\u901a\u52e4\u538b\u529b\u8f83\u5927")

    if transit and transit.get("durationMinutes") is not None and float(transit["durationMinutes"]) <= 45:
        tags.append("\u516c\u4ea4\u5730\u94c1\u53ef\u63a7")
    if transit and transit.get("transferCount") is not None and int(transit["transferCount"]) <= 1:
        tags.append("\u6362\u4e58\u8f83\u5c11")
    if driving and driving.get("durationMinutes") is not None and float(driving["durationMinutes"]) <= 30:
        tags.append("\u81ea\u9a7e\u8f83\u5feb")

    best_distance = None
    if transit and transit.get("distanceKm") is not None:
        best_distance = float(transit["distanceKm"])
    elif driving and driving.get("distanceKm") is not None:
        best_distance = float(driving["distanceKm"])
    if best_distance is not None and best_distance <= 10:
        tags.append("\u8ddd\u79bb\u9002\u4e2d")
    return list(dict.fromkeys(tags))[:4]


def calculate_commute_score(transit: dict[str, Any] | None, driving: dict[str, Any] | None) -> dict[str, Any]:
    transit_result = calculate_transit_score(transit)
    driving_result = calculate_driving_score(driving)

    if transit_result and driving_result:
        final_score = transit_result["score"] * 0.7 + driving_result["score"] * 0.3
    elif transit_result:
        final_score = transit_result["score"]
    elif driving_result:
        final_score = driving_result["score"] * 0.9
    else:
        final_score = 0

    commute_score = clamp_score(final_score)
    return {
        "commuteScore": commute_score,
        "commuteLevel": get_commute_level(commute_score),
        "commuteTags": build_commute_tags(commute_score, transit, driving),
        "transitScore": transit_result["score"] if transit_result else None,
        "drivingScore": driving_result["score"] if driving_result else None,
        "detail": {
            "transit": {
                "timeScore": transit_result["timeScore"],
                "distanceScore": transit_result["distanceScore"],
                "transferScore": transit_result["transferScore"],
            }
            if transit_result
            else None,
            "driving": {
                "timeScore": driving_result["timeScore"],
                "distanceScore": driving_result["distanceScore"],
            }
            if driving_result
            else None,
        },
    }


FACILITY_TYPES = "060000|050000|150000|090000|140000|080000|070000"
FACILITY_PARK_TYPES = "110100"
FACILITY_QUERY_VERSION = 2
FACILITY_REQUEST_INTERVAL = 0.4
_facility_request_lock = threading.Lock()
_facility_next_request_at = 0.0
FACILITY_DIMENSIONS: list[dict[str, str]] = [
    {"key": "shopping", "facilityName": "\u8d2d\u7269\u670d\u52a1", "typePrefix": "06"},
    {"key": "food", "facilityName": "\u9910\u996e\u670d\u52a1", "typePrefix": "05"},
    {"key": "transport", "facilityName": "\u4ea4\u901a\u8bbe\u65bd", "typePrefix": "15"},
    {"key": "medical", "facilityName": "\u533b\u7597\u8d44\u6e90", "typePrefix": "09"},
    {"key": "education", "facilityName": "\u79d1\u6559\u6587\u5316", "typePrefix": "14"},
    {"key": "sports", "facilityName": "\u4f53\u80b2\u4f11\u95f2", "typePrefix": "08"},
    {"key": "park", "facilityName": "\u516c\u56ed\u7eff\u5730", "typePrefix": "1101"},
    {"key": "life", "facilityName": "\u751f\u6d3b\u670d\u52a1", "typePrefix": "07"},
]


def get_count_score(count: int) -> int:
    if count >= 20:
        return 90
    if count >= 10:
        return 80
    if count >= 5:
        return 70
    if count >= 2:
        return 60
    return 30


def get_distance_score(distance: int | None) -> int:
    if distance is None:
        return 30
    if distance <= 200:
        return 90
    if distance <= 300:
        return 80
    if distance <= 500:
        return 70
    return 60


def get_coverage_score(examples: list[str]) -> int:
    if len(examples) >= 3:
        return 100
    if len(examples) == 2:
        return 80
    if len(examples) == 1:
        return 60
    return 20


def calculate_dimension_score(count: int, nearest_distance: int | None, examples: list[str]) -> int:
    return round(
        get_count_score(count) * 0.4
        + get_distance_score(nearest_distance) * 0.4
        + get_coverage_score(examples) * 0.2
    )


def simplify_poi(poi: dict[str, Any]) -> dict[str, Any] | None:
    location = str(poi.get("location", ""))
    try:
        lng_text, lat_text = location.split(",", 1)
        lng = float(lng_text)
        lat = float(lat_text)
    except (ValueError, AttributeError):
        return None

    try:
        distance = int(float(str(poi.get("distance") or "0")))
    except (TypeError, ValueError):
        distance = 0

    return {
        "id": str(poi.get("id") or ""),
        "name": str(poi.get("name") or ""),
        "type": str(poi.get("type") or ""),
        "typecode": str(poi.get("typecode") or ""),
        "address": str(poi.get("address") or ""),
        "lng": lng,
        "lat": lat,
        "distance": distance,
    }


def request_facility_page(url: str) -> dict[str, Any]:
    global _facility_next_request_at
    # The server is threaded; serialize all facility queries, not only pages of one area.
    with _facility_request_lock:
        delay = _facility_next_request_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        try:
            with open_amap_url(url, timeout=14) as response:
                payload = json.loads(response.read().decode("utf-8"))
        finally:
            _facility_next_request_at = time.monotonic() + FACILITY_REQUEST_INTERVAL
    if not isinstance(payload, dict):
        raise ValueError("高德返回内容无效")
    return payload


def fetch_around_pois(lng: float, lat: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    key = facility_amap_key()
    if not key:
        return [], [], "\u9ad8\u5fb7 Web \u670d\u52a1 Key \u672a\u914d\u7f6e"

    raw_pages: list[dict[str, Any]] = []
    simplified: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for types, max_pages in ((FACILITY_TYPES, 3), (FACILITY_PARK_TYPES, 2)):
        for page in range(1, max_pages + 1):
            params = parse.urlencode(
                {
                    "key": key,
                    "location": f"{lng:.6f},{lat:.6f}",
                    "types": types,
                    "city": "\u5357\u4eac",
                    "radius": "1000",
                    "offset": "20",
                    "page": str(page),
                    "sortrule": "distance",
                    "extensions": "base",
                    "output": "JSON",
                }
            )
            url = f"https://restapi.amap.com/v3/place/around?{params}"
            for attempt in range(2):
                try:
                    payload = request_facility_page(url)
                except (OSError, ValueError, json.JSONDecodeError):
                    if attempt == 0:
                        time.sleep(0.7)
                        continue
                    return [], raw_pages, "高德周边设施请求失败，请稍后重试"
                if str(payload.get("status")) == "1" and isinstance(payload.get("pois"), list):
                    break
                if str(payload.get("infocode")) == "10016" and attempt == 0:
                    time.sleep(0.7)
                    continue
                return [], raw_pages, f"高德周边设施查询失败：{payload.get('info') or '未知错误'}"

            raw_pages.append(payload)
            pois = payload["pois"]
            if not pois:
                break
            for poi in pois:
                if not isinstance(poi, dict):
                    continue
                item = simplify_poi(poi)
                if not item:
                    continue
                dedupe_key = item["id"] or f"{item['name']}@{item['lng']},{item['lat']}"
                if dedupe_key in seen_ids:
                    continue
                seen_ids.add(dedupe_key)
                simplified.append(item)
            if len(pois) < 20:
                break

    return simplified, raw_pages, ""


def build_poi_summary(pois: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary: list[dict[str, Any]] = []
    for dimension in FACILITY_DIMENSIONS:
        prefix = dimension["typePrefix"]
        items = [poi for poi in pois if str(poi.get("typecode", "")).startswith(prefix)]
        items.sort(key=lambda poi: int(poi.get("distance") or 0))
        examples = [str(poi.get("name") or "") for poi in items[:3] if str(poi.get("name") or "")]
        nearest_distance = int(items[0]["distance"]) if items else None
        score = calculate_dimension_score(len(items), nearest_distance, examples)
        summary.append(
            {
                "key": dimension["key"],
                "facilityName": dimension["facilityName"],
                "count": len(items),
                "score": score,
                "nearestDistance": nearest_distance,
                "examples": examples,
            }
        )
    return summary


def get_cached_facility_result(
    preference_id: str,
    area_name: str,
    area_location: dict[str, Any],
) -> dict[str, Any] | None:
    if not preference_id or not area_name:
        return None
    try:
        with get_connection() as conn:
            latest = conn.execute(
                """
                select raw.created_at
                from facility_poi_raw as raw
                where raw.preference_id = ? and raw.area_name = ?
                  and abs(raw.area_lng - ?) < 0.000001
                  and abs(raw.area_lat - ?) < 0.000001
                  and raw.raw_json like ?
                  and (
                    select count(*) from facility_evaluation as evaluation
                    where evaluation.preference_id = raw.preference_id
                      and evaluation.area_name = raw.area_name
                      and evaluation.created_at = raw.created_at
                  ) >= 8
                order by raw.created_at desc
                limit 1
                """,
                (preference_id, area_name, area_location["lng"], area_location["lat"],
                 f'{{"facility_query_version": {FACILITY_QUERY_VERSION},%'),
            ).fetchone()
            if not latest:
                return None
            rows = conn.execute(
                """
                select facility_name, count, score, nearest_distance, examples_json
                from facility_evaluation
                where preference_id = ? and area_name = ? and created_at = ?
                order by rowid asc
                """,
                (preference_id, area_name, latest["created_at"]),
            ).fetchall()
    except Exception:
        return None

    if len(rows) < 8:
        return None

    key_by_name = {item["facilityName"]: item["key"] for item in FACILITY_DIMENSIONS}
    poi_summary: list[dict[str, Any]] = []
    for row in rows:
        try:
            examples = json.loads(row["examples_json"])
        except Exception:
            examples = []
        facility_name = str(row["facility_name"])
        poi_summary.append(
            {
                "key": key_by_name.get(facility_name, facility_name),
                "facilityName": facility_name,
                "count": int(row["count"]),
                "score": int(row["score"]),
                "nearestDistance": row["nearest_distance"],
                "examples": examples if isinstance(examples, list) else [],
            }
        )

    return {
        "success": True,
        "areaLocation": {
            "name": area_name,
            "lng": float(area_location["lng"]),
            "lat": float(area_location["lat"]),
        },
        "poiSummary": poi_summary,
        "rawPoiCount": sum(int(item["count"]) for item in poi_summary),
        "message": "\u5df2\u4f7f\u7528\u672c\u5730\u7f13\u5b58\u7684\u751f\u6d3b\u5708\u8bbe\u65bd\u8bc4\u4f30\u7ed3\u679c",
    }


def normalize_area_match_name(name: str) -> str:
    return area_core_keyword(name).replace(" ", "").replace("\u3000", "")


def find_recommendation_area(preference_id: str, area_name: str) -> dict[str, Any] | None:
    if not preference_id or not area_name:
        return None
    target = normalize_area_match_name(area_name)
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                select areas_json
                from recommendation_result
                where preference_id = ?
                order by created_at desc
                limit 5
                """,
                (preference_id,),
            ).fetchall()
    except Exception:
        return None

    for row in rows:
        try:
            areas = json.loads(row["areas_json"])
        except Exception:
            continue
        if not isinstance(areas, list):
            continue
        for area in areas:
            if not isinstance(area, dict):
                continue
            candidate = normalize_area_match_name(str(area.get("name") or ""))
            if candidate == target or candidate in target or target in candidate:
                tags = area.get("tags")
                return {
                    "name": str(area.get("name") or area_name).strip(),
                    "tagline": str(area.get("tagline") or "").strip(),
                    "reason": str(area.get("reason") or "").strip(),
                    "tags": [str(tag) for tag in tags[:3]] if isinstance(tags, list) else [],
                    "rent_min": coze_number(area.get("rent_min")),
                    "rent_max": coze_number(area.get("rent_max")),
                }
    return None


def find_recommendation_reason(preference_id: str, area_name: str) -> str:
    area = find_recommendation_area(preference_id, area_name)
    return str(area.get("reason") or "").strip() if area else ""


def normalize_areas(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, dict):
        return None
    areas = value.get("areas")
    if not isinstance(areas, list) or len(areas) != 3:
        return None

    normalized: list[dict[str, Any]] = []
    for index, area in enumerate(areas):
        if not isinstance(area, dict):
            return None
        name = str(area.get("name") or area.get("areaName") or "").strip()
        tagline = str(area.get("tagline") or area.get("tagLine") or area.get("subtitle") or "").strip()
        reason = str(area.get("reason") or "").strip()
        risk = str(area.get("risk") or "").strip()
        tags = area.get("tags")
        if not name or not reason or not risk or not isinstance(tags, list):
            return None
        normalized.append(
            {
                "id": f"{index + 1:02d}",
                "name": name,
                "tagline": tagline or "片区适配度较高",
                "reason": reason,
                "risk": risk,
                "tags": [str(tag) for tag in tags[:4]],
                "source": "coze",
            }
        )
    return normalized


def coze_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def coze_number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def parse_area_location(value: Any, area_name: str) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    try:
        lng = float(value.get("lng"))
        lat = float(value.get("lat"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lng) or not math.isfinite(lat) or not (-180 <= lng <= 180) or not (-90 <= lat <= 90):
        return None
    return {"name": area_name, "lng": lng, "lat": lat}


def normalize_workflow_community(value: Any, strategy: str, index: int) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    community_id = str(value.get("community_id") or value.get("id") or "").strip()
    community_name = str(value.get("community_name") or value.get("name") or "").strip()
    if not community_name:
        return None

    raw_tags = value.get("tags")
    tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()] if isinstance(raw_tags, list) else []
    tags = tags[:2]
    facility_match = coze_boolean(value.get("facility_match"))
    facility_status = str(value.get("facility_status") or "").strip()
    facility_tag = str(value.get("facility_tag") or "").strip() if facility_match else ""
    tagline = " · ".join(tags) or "符合当前租住需求"

    return {
        "id": community_id or f"{strategy}-{index + 1}",
        "name": community_name,
        "tagline": tagline,
        "reason": "、".join(tags) if tags else "该微社区与当前租住需求具有较高匹配度。",
        "risk": "",
        "tags": tags,
        "community_id": community_id,
        "community_name": community_name,
        "distance_km": coze_number(value.get("distance_km")),
        "facility_checks": value.get("facility_checks"),
        "facility_match": facility_match,
        "facility_status": facility_status,
        "facility_tag": facility_tag,
        "gcj02_lat": coze_number(value.get("gcj02_lat")),
        "gcj02_lng": coze_number(value.get("gcj02_lng")),
        "poi_score": coze_number(value.get("poi_score")),
        "rank": coze_number(value.get("rank")),
        "rent_max": coze_number(value.get("rent_max")),
        "rent_median": coze_number(value.get("rent_median")),
        "rent_min": coze_number(value.get("rent_min")),
        "strategy": str(value.get("strategy") or strategy).strip(),
        "tag_source": str(value.get("tag_source") or "").strip(),
        "source": "coze",
    }


def normalize_workflow_plans(value: Any, depth: int = 0) -> dict[str, list[dict[str, Any]]] | None:
    if depth > 10:
        return None

    if isinstance(value, str):
        text = value.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        try:
            return normalize_workflow_plans(json.loads(text), depth + 1)
        except (json.JSONDecodeError, TypeError):
            # 返回文本模式可能把三组数组写成连续的 JSON 文档：
            # [commute]\n[balanced]\n[cost_effective]
            decoder = json.JSONDecoder()
            documents: list[Any] = []
            cursor = 0
            while cursor < len(text):
                while cursor < len(text) and text[cursor].isspace():
                    cursor += 1
                if cursor >= len(text):
                    break
                try:
                    document, cursor = decoder.raw_decode(text, cursor)
                except json.JSONDecodeError:
                    documents = []
                    break
                documents.append(document)

            if documents and all(isinstance(document, list) for document in documents):
                grouped: dict[str, list[Any]] = {
                    "commute": [],
                    "balanced": [],
                    "cost_effective": [],
                }
                strategy_mapping = {
                    "commute": "commute",
                    "commute_priority": "commute",
                    "balanced": "balanced",
                    "cost_effective": "cost_effective",
                }
                for document in documents:
                    for item in document:
                        if not isinstance(item, dict):
                            continue
                        target = strategy_mapping.get(str(item.get("strategy") or "").strip())
                        if target:
                            grouped[target].append(item)
                if all(grouped[key] for key in grouped):
                    return normalize_workflow_plans(grouped, depth + 1)
            return None

    if not isinstance(value, dict):
        return None

    plan_keys = ("commute", "balanced", "cost_effective")
    if all(isinstance(value.get(key), list) for key in plan_keys):
        plans: dict[str, list[dict[str, Any]]] = {}
        for strategy in plan_keys:
            normalized = [
                community
                for index, item in enumerate(value[strategy][:3])
                if (community := normalize_workflow_community(item, strategy, index)) is not None
            ]
            if not normalized:
                return None
            plans[strategy] = normalized
        return plans

    for key in ("data", "output", "result", "content", "answer", "message", "tag_results"):
        if key in value:
            nested = normalize_workflow_plans(value.get(key), depth + 1)
            if nested:
                return nested
    return None


def extract_json_from_coze(payload: dict[str, Any]) -> dict[str, Any] | None:
    def parse_json_string(value: str) -> Any:
        text = value.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                return json.loads(text[start : end + 1])
            raise

    def parse_candidate(candidate: Any, depth: int = 0) -> dict[str, Any] | None:
        if depth > 8:
            return None
        if isinstance(candidate, dict) and "areas" in candidate:
            return candidate
        if isinstance(candidate, dict):
            for key in ("data", "output", "content", "answer", "result", "message"):
                nested = parse_candidate(candidate.get(key), depth + 1)
                if nested:
                    return nested
        if isinstance(candidate, str):
            try:
                parsed = parse_json_string(candidate)
            except Exception:
                return None
            return parse_candidate(parsed, depth + 1)
        return None

    return parse_candidate(payload)


def coze_payload_has_success(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    code = payload.get("code")
    return code in (None, 0, "0")


def coze_payload_error_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    parts: list[str] = []
    for key in ("msg", "message", "error"):
        value = payload.get(key)
        if value:
            parts.append(str(value))
    body = payload.get("body")
    if isinstance(body, str):
        parts.append(body)
    data = payload.get("data")
    if isinstance(data, dict):
        parts.append(coze_payload_error_text(data))
    elif isinstance(data, str) and len(data) < 800:
        parts.append(data)
    return " ".join(part for part in parts if part).strip()


def should_retry_coze_error(status_code: int | None, payload: Any, error_text: str) -> bool:
    lowered = error_text.lower()
    transient_keywords = [
        "timeout",
        "timed out",
        "temporarily",
        "temporary",
        "busy",
        "retry",
        "too many",
        "rate",
        "qps",
        "limit",
        "quota",
        "credit",
        "额度",
        "限流",
        "繁忙",
    ]
    if status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
        return True
    if any(keyword in lowered for keyword in transient_keywords):
        return True
    if isinstance(payload, dict):
        code_text = str(payload.get("code") or "")
        if code_text in {"4028", "4000", "4001", "700012", "700014"}:
            return True
    return False


def build_coze_request_body(preference: dict[str, Any]) -> dict[str, Any]:
    request_body: dict[str, Any] = {
        "workflow_id": os.getenv("COZE_RECOMMEND_WORKFLOW_ID", COZE_DEFAULT_WORKFLOW_ID).strip()
        or COZE_DEFAULT_WORKFLOW_ID,
        "parameters": {
            "user_nickname": preference["user_nickname"],
            "work_address": preference["work_address"],
            "budget_max": preference["budget_max"],
            "budget_min": preference["budget_min"],
            "commute_distance_max": preference["commute_distance_max"],
            "commute_distance_min": preference["commute_distance_min"],
            "facility_preferences": preference["facility_preferences"],
            "transport_preference": preference["transport_preference"],
            "housing_type": preference["housing_type"],
        },
    }
    app_id = os.getenv("COZE_APP_ID", COZE_DEFAULT_APP_ID).strip() or COZE_DEFAULT_APP_ID
    if app_id:
        request_body["app_id"] = app_id
    return request_body


def decode_coze_output(value: Any, depth: int = 0) -> Any:
    if depth > 6:
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return decode_coze_output(json.loads(text), depth + 1)
        except (json.JSONDecodeError, TypeError):
            return value
    if isinstance(value, dict):
        return {key: decode_coze_output(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_coze_output(item, depth + 1) for item in value]
    return value


def extract_coze_workflow_output(payload: Any) -> Any | None:
    if not isinstance(payload, dict) or not coze_payload_has_success(payload):
        return None
    for key in ("data", "output", "result"):
        if key in payload and payload[key] is not None:
            return decode_coze_output(payload[key])
    return None


def run_coze_workflow(
    preference: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]] | None, Any | None, str | None]:
    token = os.getenv("COZE_API_TOKEN", "").strip()
    if not token:
        return None, None, json.dumps({"error": "missing_token", "message": "COZE_API_TOKEN is not configured"}, ensure_ascii=False)

    base_url = os.getenv("COZE_BASE_URL", COZE_DEFAULT_BASE_URL).strip().rstrip("/") or COZE_DEFAULT_BASE_URL
    request_body = build_coze_request_body(preference)
    endpoint = f"{base_url}/v1/workflow/run"
    attempts = int(os.getenv("COZE_RECOMMEND_MAX_RETRIES", "3") or "3")
    attempts = max(1, min(attempts, 5))
    timeout_seconds = int(os.getenv("COZE_RECOMMEND_TIMEOUT", "120") or "120")
    last_payload: dict[str, Any] | None = None

    for attempt in range(1, attempts + 1):
        req = request.Request(
            endpoint,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        status_code: int | None = None
        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                status_code = response.status
                raw = response.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
        except error.HTTPError as exc:
            status_code = exc.code
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body_payload = json.loads(raw)
            except Exception:
                body_payload = raw
            parsed = {"status": status_code, "body": body_payload}
        except Exception as exc:
            parsed = {"error": type(exc).__name__, "message": str(exc)}

        error_text = coze_payload_error_text(parsed)
        last_payload = {
            "attempt": attempt,
            "attempts": attempts,
            "status": status_code,
            "response": parsed,
            "errorText": error_text,
        }

        workflow_output = extract_coze_workflow_output(parsed)
        plans = normalize_workflow_plans(workflow_output)
        if workflow_output is not None:
            return plans, workflow_output, json.dumps(last_payload, ensure_ascii=False)

        if attempt < attempts and should_retry_coze_error(status_code, parsed, error_text):
            time.sleep(min(8, 1.6 * attempt))
            continue

        if attempt < attempts and coze_payload_has_success(parsed):
            time.sleep(min(6, 1.2 * attempt))
            continue

        break

    return None, None, json.dumps(last_payload or {"error": "unknown_coze_error"}, ensure_ascii=False)


def get_coze_fallback_message(raw_response: str | None) -> str:
    if not raw_response:
        return "扣子工作流暂不可用，当前已返回演示推荐结果。"
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError:
        return "扣子工作流返回格式异常，当前已返回演示推荐结果。"

    response_payload = payload.get("response") if isinstance(payload.get("response"), dict) else payload
    if isinstance(response_payload, dict) and isinstance(response_payload.get("body"), dict):
        response_payload = response_payload["body"]

    code = response_payload.get("code") if isinstance(response_payload, dict) else payload.get("code")
    msg = coze_payload_error_text(response_payload) or coze_payload_error_text(payload)
    lowered = msg.lower()
    if payload.get("error") == "missing_token":
        return "扣子工作流 Token 未配置，当前已返回演示推荐结果。"
    if "qps" in lowered or "rate" in lowered or "too many" in lowered or "限流" in msg:
        return "扣子工作流请求触发临时限流，系统已自动重试；当前仍未成功，已返回演示推荐结果。"
    if code == 4028 or "credits" in lowered or "balance" in lowered or "quota" in lowered or "额度" in msg:
        return "扣子工作流返回额度或限额相关提示，系统已自动重试；当前仍未成功，已返回演示推荐结果。"
    if msg:
        return f"扣子工作流调用暂时不稳定：{msg}。系统已自动重试，当前已返回演示推荐结果。"
    if isinstance(payload.get("error"), str):
        return f"扣子工作流调用失败：{payload['error']}。当前已返回演示推荐结果。"
    return "扣子工作流未返回有效片区结果，当前已返回演示推荐结果。"


class NinganjuHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:
        json_response(self, 200, {"ok": True, "message": "ok"})

    def do_GET(self) -> None:
        if self.path == "/api/health":
            json_response(
                self,
                200,
                {
                    "ok": True,
                    "message": "api is running",
                    "cozeReady": bool(os.getenv("COZE_API_TOKEN", "").strip()),
                    "workflowId": os.getenv("COZE_RECOMMEND_WORKFLOW_ID", COZE_DEFAULT_WORKFLOW_ID).strip()
                    or COZE_DEFAULT_WORKFLOW_ID,
                },
            )
            return
        json_response(self, 404, {"ok": False, "message": "接口不存在"})

    def do_POST(self) -> None:
        if self.path == "/api/register":
            self.handle_register()
            return
        if self.path == "/api/login":
            self.handle_login()
            return
        if self.path == "/api/change-password":
            self.handle_change_password()
            return
        if self.path == "/api/profile":
            self.handle_profile()
            return
        if self.path == "/api/profile/detail-view":
            self.handle_profile_detail_view()
            return
        if self.path == "/api/recommend-areas":
            self.handle_recommend_areas()
            return
        if self.path == "/api/commute":
            self.handle_commute()
            return
        if self.path == "/api/facilities":
            self.handle_facilities()
            return
        if self.path == "/api/metrics/amap-client-call":
            self.handle_amap_client_call()
            return
        if self.path == "/api/evaluation-history/save":
            self.handle_save_evaluation_history()
            return
        if self.path == "/api/evaluation-history/list":
            self.handle_list_evaluation_history()
            return
        if self.path == "/api/evaluation-history/delete":
            self.handle_delete_evaluation_history()
            return
        if self.path == "/api/admin-dashboard":
            self.handle_admin_dashboard()
            return
        if self.path == "/api/admin-dashboard/recalculate-top-areas":
            self.handle_recalculate_top_areas()
            return
        json_response(self, 404, {"ok": False, "message": "接口不存在"})

    def handle_register(self) -> None:
        try:
            data = parse_body(self)
            username = str(data.get("username", "")).strip()
            password = str(data.get("password", ""))

            username_error = validate_username(username)
            if username_error:
                json_response(self, 400, {"ok": False, "message": username_error})
                return
            if not password:
                json_response(self, 400, {"ok": False, "message": "请输入密码"})
                return

            salt = secrets.token_hex(16)
            password_hash = hash_password(password, salt)

            with get_connection() as conn:
                conn.execute(
                    """
                    insert into users (username, password_hash, salt, role, created_at)
                    values (?, ?, ?, 'user', ?)
                    """,
                    (username, password_hash, salt, utc_now()),
                )

            increment_metric("new_registration")
            json_response(self, 200, {"ok": True, "message": "注册成功"})
        except sqlite3.IntegrityError:
            json_response(self, 409, {"ok": False, "message": "该用户名已注册"})
        except Exception:
            json_response(self, 500, {"ok": False, "message": "注册失败，请稍后重试"})

    def handle_login(self) -> None:
        try:
            data = parse_body(self)
            username = str(data.get("username", "")).strip()
            password = str(data.get("password", ""))
            increment_metric("site_visit")

            if not username or not password:
                json_response(self, 400, {"ok": False, "message": "请输入用户名和密码"})
                return

            with get_connection() as conn:
                row = conn.execute("select * from users where username = ?", (username,)).fetchone()

            if row is None or not verify_password(password, row["salt"], row["password_hash"]):
                json_response(self, 401, {"ok": False, "message": "用户名或密码错误"})
                return

            session_token = create_profile_session(row["username"])
            login_time = utc_now()
            with get_connection() as conn:
                conn.execute(
                    "insert into user_activity (username, event_type, created_at) values (?, 'login', ?)",
                    (row["username"], login_time),
                )
                conn.execute(
                    "insert into user_login (username, login_time) values (?, ?)",
                    (row["username"], login_time),
                )
            json_response(
                self,
                200,
                {
                    "ok": True,
                    "message": "登录成功",
                    "user": {
                        "id": row["id"],
                        "username": row["username"],
                        "role": row["role"],
                    },
                    "sessionToken": session_token,
                },
            )
        except Exception:
            json_response(self, 500, {"ok": False, "message": "登录失败，请稍后重试"})

    def handle_change_password(self) -> None:
        try:
            data = parse_body(self)
            username = str(data.get("username", "")).strip()
            current_password = str(data.get("currentPassword", ""))
            new_password = str(data.get("newPassword", ""))
            confirm_password = str(data.get("confirmPassword", ""))

            if not username or not current_password or not new_password or not confirm_password:
                json_response(self, 400, {"ok": False, "message": "请填写用户名、当前密码和两次新密码"})
                return
            if new_password != confirm_password:
                json_response(self, 400, {"ok": False, "message": "两次输入的新密码不一致"})
                return
            if len(new_password) < 8:
                json_response(self, 400, {"ok": False, "message": "新密码至少需要8位"})
                return
            if new_password == current_password:
                json_response(self, 400, {"ok": False, "message": "新密码不能与当前密码相同"})
                return

            with get_connection() as conn:
                row = conn.execute(
                    "select password_hash, salt from users where username = ?", (username,)
                ).fetchone()
                if row is None or not verify_password(current_password, row["salt"], row["password_hash"]):
                    json_response(self, 401, {"ok": False, "message": "用户名或当前密码错误"})
                    return
                salt = secrets.token_hex(16)
                conn.execute(
                    "update users set password_hash = ?, salt = ? where username = ?",
                    (hash_password(new_password, salt), salt, username),
                )

            with _profile_session_lock:
                for token, (session_username, _) in list(_profile_sessions.items()):
                    if session_username == username:
                        _profile_sessions.pop(token, None)
            json_response(self, 200, {"ok": True, "message": "密码修改成功，请使用新密码登录"})
        except Exception:
            json_response(self, 500, {"ok": False, "message": "密码修改失败，请稍后重试"})

    def handle_amap_client_call(self) -> None:
        origin = self.headers.get("Origin", "")
        if origin and origin not in {"http://127.0.0.1:5173", "http://localhost:5173"}:
            json_response(self, 403, {"success": False, "message": "来源不被允许"})
            return
        try:
            increment_metric("amap_api_call")
            json_response(self, 200, {"success": True})
        except Exception:
            json_response(self, 500, {"success": False, "message": "地图调用次数记录失败"})

    def handle_profile(self) -> None:
        username = profile_session_username(self.headers.get("Authorization", ""))
        if not username:
            json_response(self, 401, {"success": False, "message": "登录状态已失效，请重新登录"})
            return
        try:
            with get_connection() as conn:
                latest = conn.execute(
                    """
                    select work_address, budget_min, budget_max, commute_distance_min,
                           commute_distance_max, transport_preference, housing_type,
                           facility_preferences, created_at
                    from rent_preference
                    where user_nickname = ?
                    order by created_at desc, rowid desc
                    limit 1
                    """,
                    (username,),
                ).fetchone()
                recommendation_count = conn.execute(
                    "select count(*) from rent_preference where user_nickname = ?", (username,)
                ).fetchone()[0]
                detail_view_count = conn.execute(
                    "select count(*) from user_activity where username = ? and event_type = 'detail_view'",
                    (username,),
                ).fetchone()[0]
                saved_count = conn.execute(
                    "select count(*) from evaluation_history where username = ?", (username,)
                ).fetchone()[0]
                last_activity = conn.execute(
                    "select created_at from user_activity where username = ? order by created_at desc, id desc limit 1",
                    (username,),
                ).fetchone()

            facility_preferences = []
            if latest:
                try:
                    stored_facilities = json.loads(latest["facility_preferences"] or "[]")
                    if isinstance(stored_facilities, list):
                        facility_preferences = [
                            str(item).strip() for item in stored_facilities if str(item).strip()
                        ]
                except (TypeError, ValueError):
                    pass

            json_response(
                self,
                200,
                {
                    "success": True,
                    "username": username,
                    "latestPreference": {
                        "workAddress": latest["work_address"],
                        "budgetMin": latest["budget_min"],
                        "budgetMax": latest["budget_max"],
                        "commuteDistanceMin": latest["commute_distance_min"],
                        "commuteDistanceMax": latest["commute_distance_max"],
                        "transportPreference": latest["transport_preference"],
                        "housingType": latest["housing_type"],
                        "facilityPreferences": facility_preferences,
                        "createdAt": latest["created_at"],
                    } if latest else None,
                    "stats": {
                        "recommendationCount": recommendation_count,
                        "detailViewCount": detail_view_count,
                        "savedCommunityCount": saved_count,
                        "lastUsedAt": last_activity["created_at"] if last_activity else None,
                    },
                },
            )
        except Exception as exc:
            json_response(self, 500, {"success": False, "message": "个人信息读取失败，请稍后重试", "detail": str(exc)})

    def handle_profile_detail_view(self) -> None:
        username = profile_session_username(self.headers.get("Authorization", ""))
        if not username:
            json_response(self, 401, {"success": False, "message": "登录状态已失效，请重新登录"})
            return
        try:
            data = parse_body(self)
            preference_id = str(data.get("preferenceId", "")).strip()
            area_name = str(data.get("areaName", "")).strip()
            if not preference_id or not area_name:
                json_response(self, 400, {"success": False, "message": "缺少微社区详情信息"})
                return
            with get_connection() as conn:
                preference = conn.execute(
                    "select id from rent_preference where id = ? and user_nickname = ?",
                    (preference_id, username),
                ).fetchone()
            if not preference:
                json_response(self, 404, {"success": False, "message": "未找到当前用户的租房需求记录"})
                return
            record_user_activity(username, "detail_view", preference_id, area_name)
            json_response(self, 200, {"success": True})
        except Exception as exc:
            json_response(self, 500, {"success": False, "message": "详情查看次数记录失败", "detail": str(exc)})

    def handle_recommend_areas(self) -> None:
        try:
            data = parse_body(self)
            preference, error = validate_preference(data)
            if error or preference is None:
                json_response(self, 400, {"success": False, "message": error or "参数错误"})
                return

            preference_id = str(uuid.uuid4())
            markdown_prompt = build_recommend_prompt(preference)
            preference_json = {
                "user_nickname": preference["user_nickname"],
                "work_address": preference["work_address"],
                "budget_max": preference["budget_max"],
                "budget_min": preference["budget_min"],
                "commute_distance_max": preference["commute_distance_max"],
                "commute_distance_min": preference["commute_distance_min"],
                "facility_preferences": preference["facility_preferences"],
                "transport_preference": preference["transport_preference"],
                "housing_type": preference["housing_type"],
            }
            increment_metric("area_evaluation")

            with get_connection() as conn:
                conn.execute(
                    """
                    insert into rent_preference
                    (id, user_nickname, work_address, budget_min, budget_max,
                     commute_distance_min, commute_distance_max, facility_preferences,
                     transport_preference, housing_type, preference_json,
                     commute_range, priority, markdown_prompt, created_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        preference_id,
                        preference["user_nickname"],
                        preference["work_address"],
                        preference["budget_min"],
                        preference["budget_max"],
                        preference["commute_distance_min"],
                        preference["commute_distance_max"],
                        json.dumps(preference["facility_preferences"], ensure_ascii=False),
                        preference["transport_preference"],
                        preference["housing_type"],
                        json.dumps(preference_json, ensure_ascii=False),
                        preference["commute_range"],
                        preference["priority"],
                        markdown_prompt,
                        utc_now(),
                    ),
                )

            record_user_activity(preference["user_nickname"], "recommendation", preference_id)
            coze_plans, workflow_output, raw_response = run_coze_workflow(preference)
            areas = (
                [area for key in ("commute", "balanced", "cost_effective") for area in coze_plans[key]]
                if coze_plans
                else [
                {**area, "id": f"{index + 1:02d}"}
                for index, area in enumerate(FALLBACK_AREAS[:3])
                ]
            )
            source = "coze" if coze_plans else "fallback"

            with get_connection() as conn:
                conn.execute(
                    """
                    insert into recommendation_result
                    (id, preference_id, areas_json, raw_response, source, created_at)
                    values (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        preference_id,
                        json.dumps(areas, ensure_ascii=False),
                        raw_response,
                        source,
                        utc_now(),
                    ),
                )

            json_response(
                self,
                200,
                {
                    "success": True,
                    "preferenceId": preference_id,
                    "preferenceJson": preference_json,
                    "areas": areas,
                    "plans": coze_plans,
                    "source": source,
                    "workflowSucceeded": coze_plans is not None,
                    "workflowOutput": workflow_output,
                    "message": (
                        "推荐完成，三类方案已根据本次租住需求更新。"
                        if coze_plans is not None
                        else "工作流已响应，但返回结构未包含三类推荐方案。"
                        if workflow_output is not None
                        else get_coze_fallback_message(raw_response)
                    ),
                },
            )
        except Exception as exc:
            json_response(
                self,
                500,
                {
                    "success": False,
                    "message": "租房需求保存失败，请稍后重试",
                    "detail": str(exc),
                },
            )

    def handle_admin_dashboard(self) -> None:
        try:
            dates = recent_day_keys(7)
            today = today_key()
            with get_connection() as conn:
                metric_rows = conn.execute(
                    """
                    select metric_name, metric_date, count
                    from operation_metrics
                    where metric_date in ({})
                    """.format(",".join("?" for _ in dates)),
                    dates,
                ).fetchall()
                reset_row = conn.execute(
                    "select value from admin_settings where key = ?",
                    ("top_area_reset_at",),
                ).fetchone()
                seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
                top_area_since = seven_days_ago
                if reset_row is not None and str(reset_row["value"]) > top_area_since:
                    top_area_since = str(reset_row["value"])
                recommendation_rows = conn.execute(
                    """
                    select areas_json
                    from recommendation_result
                    where created_at >= ?
                    order by created_at desc
                    """,
                    (top_area_since,),
                ).fetchall()
                detail_view_count = conn.execute(
                    """
                    select count(*) from user_activity
                    where event_type = 'detail_view' and date(created_at, '+8 hours') = ?
                    """,
                    (today,),
                ).fetchone()[0]
                recent_login_rows = conn.execute(
                    """
                    select user_login.id, user_login.username, user_login.login_time,
                           (select count(*) from rent_preference
                            where rent_preference.user_nickname = user_login.username) as recommendation_count
                    from user_login
                    order by user_login.login_time desc, user_login.id desc
                    limit 5
                    """
                ).fetchall()

            metrics_by_day: dict[tuple[str, str], int] = {
                (row["metric_name"], row["metric_date"]): int(row["count"]) for row in metric_rows
            }
            workflow_calls = metrics_by_day.get(("area_evaluation", today), 0)
            today_metrics = {
                "siteVisits": metrics_by_day.get(("site_visit", today), 0),
                "newRegistrations": metrics_by_day.get(("new_registration", today), 0),
                "areaEvaluations": workflow_calls * 9,
                "detailViews": int(detail_view_count),
                "workflowCalls": workflow_calls,
                "amapApiCalls": metrics_by_day.get(("amap_api_call", today), 0),
            }
            recent_logins = [
                {
                    "id": row["id"],
                    "username": row["username"],
                    "recommendationCount": int(row["recommendation_count"]),
                    "loginTime": row["login_time"],
                }
                for row in recent_login_rows
            ]
            visit_trend = [
                {
                    "date": date_key,
                    "label": date_key[5:],
                    "value": metrics_by_day.get(("site_visit", date_key), 0),
                }
                for date_key in dates
            ]

            area_counter: dict[str, int] = {}
            for row in recommendation_rows:
                try:
                    areas = json.loads(row["areas_json"] or "[]")
                except Exception:
                    areas = []
                if not isinstance(areas, list):
                    continue
                for area in areas:
                    if not isinstance(area, dict):
                        continue
                    name = str(area.get("name", "")).strip()
                    if name:
                        area_counter[name] = area_counter.get(name, 0) + 1

            top_areas = [
                {"rank": index + 1, "name": name, "count": count}
                for index, (name, count) in enumerate(
                    sorted(area_counter.items(), key=lambda item: (-item[1], item[0]))[:6]
                )
            ]

            json_response(
                self,
                200,
                {
                    "success": True,
                    "todayMetrics": today_metrics,
                    "recentLogins": recent_logins,
                    "visitTrend": visit_trend,
                    "topAreas": top_areas,
                    "updatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "topAreaResetAt": reset_row["value"] if reset_row is not None else "",
                },
            )
        except Exception as exc:
            json_response(self, 500, {"success": False, "message": "运营数据读取失败，请稍后重试", "detail": str(exc)})

    def handle_recalculate_top_areas(self) -> None:
        try:
            reset_at = datetime.now(timezone.utc).isoformat()
            with get_connection() as conn:
                conn.execute(
                    """
                    insert into admin_settings (key, value)
                    values (?, ?)
                    on conflict(key) do update set value = excluded.value
                    """,
                    ("top_area_reset_at", reset_at),
                )

            json_response(self, 200, {"success": True, "topAreaResetAt": reset_at})
        except Exception as exc:
            json_response(self, 500, {"success": False, "message": "片区推荐统计重置失败，请稍后重试", "detail": str(exc)})

    def handle_commute(self) -> None:
        try:
            data = parse_body(self)
            preference_id = str(data.get("preferenceId", "")).strip()
            area_name = str(data.get("areaName", "")).strip()
            area_location_data = data.get("areaLocation")
            commute_mode = str(data.get("mode", "driving")).strip()
            if commute_mode not in {"driving", "transit"}:
                commute_mode = "driving"
            if not preference_id:
                json_response(self, 400, {"success": False, "message": "缺少 preferenceId，请先生成推荐结果"})
                return
            if not area_name:
                json_response(self, 400, {"success": False, "message": "缺少 areaName"})
                return
            if area_location_data is not None and parse_area_location(area_location_data, area_name) is None:
                json_response(self, 400, {"success": False, "message": "微社区经纬度无效"})
                return

            with get_connection() as conn:
                row = conn.execute(
                    """
                    select id, work_address, work_lng, work_lat,
                           budget_min, budget_max, housing_type
                    from rent_preference
                    where id = ?
                    """,
                    (preference_id,),
                ).fetchone()

            if row is None:
                json_response(self, 404, {"success": False, "message": "未找到对应的租房偏好记录，请重新生成推荐"})
                return

            work_location = None
            if row["work_lng"] is not None and row["work_lat"] is not None:
                work_location = {
                    "address": row["work_address"],
                    "lng": float(row["work_lng"]),
                    "lat": float(row["work_lat"]),
                }
            else:
                work_location = geocode_address(str(row["work_address"]))
                if work_location:
                    with get_connection() as conn:
                        conn.execute(
                            "update rent_preference set work_lng = ?, work_lat = ? where id = ?",
                            (work_location["lng"], work_location["lat"], preference_id),
                        )

            area_location = (
                parse_area_location(area_location_data, area_name)
                if area_location_data is not None
                else geocode_area_location(area_name)
            )

            if not work_location and not area_location:
                json_response(
                    self,
                    502,
                    {
                        "success": False,
                        "message": "高德地理编码失败，请检查高德 Web 服务 Key 或地址名称",
                    },
                )
                return

            commute = None
            commute_score_result = None
            recommendation_area = find_recommendation_area(preference_id, area_name)
            rent_context = {
                "budgetMin": int(row["budget_min"]),
                "budgetMax": int(row["budget_max"]),
                "housingType": str(row["housing_type"]),
                "rentMin": recommendation_area.get("rent_min") if recommendation_area else None,
                "rentMax": recommendation_area.get("rent_max") if recommendation_area else None,
            }
            route_message = ""
            if work_location and area_location:
                origin = f"{area_location['lng']},{area_location['lat']}"
                destination = f"{work_location['lng']},{work_location['lat']}"
                driving_commute = None
                transit_commute = None
                if commute_mode == "transit":
                    transit_commute = get_transit_route(origin, destination)
                    driving_commute = get_driving_route(origin, destination)
                    commute = transit_commute
                else:
                    driving_commute = get_driving_route(origin, destination)
                    transit_commute = get_transit_route(origin, destination)
                    commute = driving_commute
                commute_score_result = calculate_commute_score(transit_commute, driving_commute)
                if commute is None:
                    route_message = (
                        "公交/地铁路线规划暂时失败，已展示工作地与推荐片区位置"
                        if commute_mode == "transit"
                        else "驾车路线规划失败，已展示工作地与推荐片区位置"
                    )
                    commute = {
                        "mode": "公交/地铁" if commute_mode == "transit" else "驾车",
                        "routeName": "公共交通通勤" if commute_mode == "transit" else "驾车通勤",
                        "durationMinutes": None,
                        "distanceKm": None,
                        "transferCount": 0,
                        "summary": route_message,
                        "polyline": [],
                    }

            json_response(
                self,
                200,
                {
                    "success": True,
                    "workLocation": work_location,
                    "areaLocation": area_location,
                    "commute": commute,
                    "commuteScoreResult": commute_score_result,
                    "recommendationArea": recommendation_area,
                    "rentContext": rent_context,
                    "message": route_message,
                },
            )
        except Exception as exc:
            json_response(
                self,
                500,
                {
                    "success": False,
                    "message": "通勤信息生成失败，请稍后重试",
                    "detail": str(exc),
                },
            )

    def handle_facilities(self) -> None:
        try:
            data = parse_body(self)
            preference_id = str(data.get("preferenceId", "")).strip()
            area_name = str(data.get("areaName", "")).strip()
            area_location_data = data.get("areaLocation")

            if not area_name:
                json_response(self, 400, {"success": False, "message": "缺少 areaName"})
                return

            if area_location_data is not None:
                area_location = parse_area_location(area_location_data, area_name)
                if area_location is None:
                    json_response(self, 400, {"success": False, "message": "微社区经纬度无效"})
                    return
            else:
                area_location = geocode_area_location(area_name)

            if not area_location:
                json_response(self, 502, {"success": False, "message": "推荐片区坐标解析失败，暂时无法查询生活圈设施"})
                return

            cached = get_cached_facility_result(preference_id, area_name, area_location)
            if cached:
                cached["recommendationReason"] = find_recommendation_reason(preference_id, area_name)
                json_response(self, 200, cached)
                return

            pois, raw_pages, poi_message = fetch_around_pois(float(area_location["lng"]), float(area_location["lat"]))
            if poi_message:
                json_response(self, 502, {"success": False, "message": poi_message})
                return
            poi_summary = build_poi_summary(pois)
            recommendation_reason = find_recommendation_reason(preference_id, area_name)
            created_at = utc_now()

            with get_connection() as conn:
                raw_id = str(uuid.uuid4())
                conn.execute(
                    """
                    insert into facility_poi_raw
                    (id, preference_id, area_name, area_lng, area_lat, raw_json, created_at)
                    values (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        raw_id,
                        preference_id or None,
                        area_name,
                        float(area_location["lng"]),
                        float(area_location["lat"]),
                        json.dumps({"facility_query_version": FACILITY_QUERY_VERSION, "pages": raw_pages}, ensure_ascii=False),
                        created_at,
                    ),
                )
                for item in poi_summary:
                    conn.execute(
                        """
                        insert into facility_evaluation
                        (id, preference_id, area_name, facility_name, count, score, nearest_distance, examples_json, created_at)
                        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            preference_id or None,
                            area_name,
                            item["facilityName"],
                            item["count"],
                            item["score"],
                            item["nearestDistance"],
                            json.dumps(item["examples"], ensure_ascii=False),
                            created_at,
                        ),
                    )

            json_response(
                self,
                200,
                {
                    "success": True,
                    "areaLocation": {
                        "name": area_name,
                        "lng": float(area_location["lng"]),
                        "lat": float(area_location["lat"]),
                    },
                    "poiSummary": poi_summary,
                    "rawPoiCount": len(pois),
                    "recommendationReason": recommendation_reason,
                    "message": poi_message,
                },
            )
        except Exception as exc:
            json_response(
                self,
                500,
                {
                    "success": False,
                    "message": "生活圈设施数据生成失败，请稍后重试",
                    "detail": str(exc),
                },
            )

    def handle_save_evaluation_history(self) -> None:
        try:
            data = parse_body(self)
            username = str(data.get("username", "")).strip() or "xiaoning"
            region_name = str(data.get("regionName", "")).strip()
            try:
                total_score = int(data.get("totalScore"))
                commute_score = int(data.get("commuteScore"))
                facility_score = int(data.get("facilityScore"))
            except (TypeError, ValueError):
                json_response(self, 400, {"success": False, "message": "评分数据不完整，暂时无法保存"})
                return

            if not region_name:
                json_response(self, 400, {"success": False, "message": "缺少片区名称"})
                return

            record_id = str(uuid.uuid4())
            saved_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            other_info = data.get("otherInfo")
            other_info_json = json.dumps(other_info if isinstance(other_info, dict) else {}, ensure_ascii=False)

            with get_connection() as conn:
                conn.execute(
                    """
                    insert into evaluation_history
                    (id, username, region_name, total_score, commute_score, facility_score, time, other_info)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        username,
                        region_name,
                        total_score,
                        commute_score,
                        facility_score,
                        saved_time,
                        other_info_json,
                    ),
                )
                old_rows = conn.execute(
                    """
                    select id from evaluation_history
                    where username = ?
                    order by time desc
                    limit -1 offset 30
                    """,
                    (username,),
                ).fetchall()
                for row in old_rows:
                    conn.execute("delete from evaluation_history where id = ? and username = ?", (row["id"], username))

            record_user_activity(username, "save_evaluation", str(other_info.get("preferenceId") or "") if isinstance(other_info, dict) else None, region_name)
            json_response(
                self,
                200,
                {
                    "success": True,
                    "record": {
                        "id": record_id,
                        "username": username,
                        "regionName": region_name,
                        "totalScore": total_score,
                        "commuteScore": commute_score,
                        "facilityScore": facility_score,
                        "time": saved_time,
                        "otherInfo": other_info if isinstance(other_info, dict) else {},
                    },
                },
            )
        except Exception as exc:
            json_response(self, 500, {"success": False, "message": "评估记录保存失败，请稍后重试", "detail": str(exc)})

    def handle_list_evaluation_history(self) -> None:
        try:
            data = parse_body(self)
            username = str(data.get("username", "")).strip() or "xiaoning"
            with get_connection() as conn:
                rows = conn.execute(
                    """
                    select *
                    from evaluation_history
                    where username = ?
                    order by time desc
                    limit 10
                    """,
                    (username,),
                ).fetchall()

            records = []
            for row in rows:
                try:
                    other_info = json.loads(row["other_info"] or "{}")
                except Exception:
                    other_info = {}
                records.append(
                    {
                        "id": row["id"],
                        "username": row["username"],
                        "regionName": row["region_name"],
                        "totalScore": row["total_score"],
                        "commuteScore": row["commute_score"],
                        "facilityScore": row["facility_score"],
                        "time": row["time"],
                        "otherInfo": other_info,
                    }
                )

            json_response(self, 200, {"success": True, "records": records})
        except Exception as exc:
            json_response(self, 500, {"success": False, "message": "评估记录读取失败，请稍后重试", "detail": str(exc)})

    def handle_delete_evaluation_history(self) -> None:
        try:
            data = parse_body(self)
            username = str(data.get("username", "")).strip() or "xiaoning"
            record_id = str(data.get("id", "")).strip()
            if not record_id:
                json_response(self, 400, {"success": False, "message": "缺少记录ID"})
                return

            with get_connection() as conn:
                conn.execute("delete from evaluation_history where id = ? and username = ?", (record_id, username))

            json_response(self, 200, {"success": True, "id": record_id})
        except Exception as exc:
            json_response(self, 500, {"success": False, "message": "评估记录删除失败，请稍后重试", "detail": str(exc)})


def main() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), NinganjuHandler)
    print(f"Ninganju API running at http://{HOST}:{PORT}")
    print(f"SQLite database: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    main()
