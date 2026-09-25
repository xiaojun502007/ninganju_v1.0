# -*- coding: utf-8 -*-
"""
Agent B · 代码节点 7：片区评分与排序

这是整个系统的核心。它决定了推荐哪些片区 —— 注意大模型在这一步之前不参与任何决策，
大模型只在下一个节点负责把这里算出的数字翻译成人话。

输入
    candidates        Array   候选片区（来自后端 locate-and-recall）
    commute_results   Array   通勤原始数据（来自后端 commute-raw，未评分）
    poi_results       Array   八类 POI 汇总（来自后端 poi-raw，未评分）
    facility_weights  Object  节点 2 推导
    priority_weights  Object  节点 2 推导
    preferred_modes   Array
    commute_max_min   Number
    budget_min        Number
    budget_max        Number
    top_n             Number  默认 4

输出
    ranked_areas   Array   Top N 片区，含完整评分明细
    dropped_areas  Array   被硬约束淘汰的片区及原因（便于调试和向用户解释）

评分口径
    通勤评分完全照搬《通勤情况评分模块.txt》，生活圈评分完全照搬《生活圈情况评分.txt》，
    与后端 api_server.py 中已有实现保持一致 —— 三处口径必须同源，否则前端展示的分数
    会和推荐依据对不上。

    唯一的口径扩展：原文档固定按 公交0.7 + 自驾0.3 合成通勤总分。这里改为按用户的
    preferred_modes 决定主次，自驾用户不应因为地铁方案差而被扣分。
"""

import json

FACILITY_KEYS = ["shopping", "food", "transport", "medical",
                 "education", "sports", "park", "life"]

FACILITY_NAMES = {
    "shopping": "购物服务", "food": "餐饮服务", "transport": "交通设施",
    "medical": "医疗资源", "education": "科教文化", "sports": "体育休闲",
    "park": "公园绿地", "life": "生活服务",
}


def clamp_score(score):
    return max(0, min(100, int(round(score))))


# ---------------------------------------------------------------------------
# 通勤评分 —— 对应《通勤情况评分模块.txt》
# ---------------------------------------------------------------------------

def get_transit_time_score(minutes):
    if minutes <= 25: return 100
    if minutes <= 35: return 90
    if minutes <= 45: return 80
    if minutes <= 60: return 65
    if minutes <= 75: return 50
    if minutes <= 90: return 35
    return 20


def get_driving_time_score(minutes):
    if minutes <= 15: return 100
    if minutes <= 25: return 90
    if minutes <= 35: return 80
    if minutes <= 50: return 65
    if minutes <= 65: return 50
    if minutes <= 80: return 35
    return 20


def get_commute_distance_score(distance_km):
    if distance_km <= 3: return 100
    if distance_km <= 5: return 90
    if distance_km <= 8: return 80
    if distance_km <= 12: return 70
    if distance_km <= 16: return 55
    if distance_km <= 20: return 40
    return 25


def get_transfer_score(transfer_count):
    if transfer_count == 0: return 100
    if transfer_count == 1: return 85
    if transfer_count == 2: return 65
    if transfer_count == 3: return 45
    return 25


def calculate_transit_score(transit):
    """公交地铁：时间 60% + 距离 20% + 换乘 20%"""
    if not transit:
        return None
    minutes = transit.get("duration_minutes")
    distance = transit.get("distance_km")
    transfers = transit.get("transfer_count")
    if minutes is None or distance is None or transfers is None:
        return None

    time_score = get_transit_time_score(minutes)
    distance_score = get_commute_distance_score(distance)
    transfer_score = get_transfer_score(transfers)
    return {
        "score": clamp_score(time_score * 0.6 + distance_score * 0.2 + transfer_score * 0.2),
        "time_score": time_score,
        "distance_score": distance_score,
        "transfer_score": transfer_score,
    }


def calculate_driving_score(driving):
    """自驾：时间 70% + 距离 30%"""
    if not driving:
        return None
    minutes = driving.get("duration_minutes")
    distance = driving.get("distance_km")
    if minutes is None or distance is None:
        return None

    time_score = get_driving_time_score(minutes)
    distance_score = get_commute_distance_score(distance)
    return {
        "score": clamp_score(time_score * 0.7 + distance_score * 0.3),
        "time_score": time_score,
        "distance_score": distance_score,
    }


def get_commute_level(score):
    if score >= 90: return "通勤极佳"
    if score >= 80: return "通勤友好"
    if score >= 70: return "通勤可接受"
    if score >= 60: return "通勤略有压力"
    if score >= 45: return "通勤压力较大"
    return "不建议优先选择"


def build_commute_tags(score, transit, driving):
    tags = []
    if score >= 80:
        tags.append("通勤友好")
    elif score >= 60:
        tags.append("基本可通勤")
    else:
        tags.append("通勤压力较大")

    if transit and transit.get("duration_minutes") is not None and transit["duration_minutes"] <= 45:
        tags.append("公交地铁可控")
    if transit and transit.get("transfer_count") is not None and transit["transfer_count"] <= 1:
        tags.append("换乘较少")
    if driving and driving.get("duration_minutes") is not None and driving["duration_minutes"] <= 30:
        tags.append("自驾较快")

    best_distance = (transit or {}).get("distance_km")
    if best_distance is None:
        best_distance = (driving or {}).get("distance_km")
    if best_distance is not None and best_distance <= 10:
        tags.append("距离适中")

    seen, unique = set(), []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique.append(tag)
    return unique[:4]


def calculate_commute(transit, driving, preferred_modes):
    """
    合成通勤总分。相对原文档的扩展：主次由用户的通勤方式决定。
    自驾用户不应因为该片区地铁方案差而被扣分，反之亦然。
    """
    transit_result = calculate_transit_score(transit)
    driving_result = calculate_driving_score(driving)

    modes = preferred_modes or ["transit"]
    driving_first = "driving" in modes and "transit" not in modes

    if transit_result and driving_result:
        if driving_first:
            final = driving_result["score"] * 0.7 + transit_result["score"] * 0.3
        else:
            final = transit_result["score"] * 0.7 + driving_result["score"] * 0.3
    elif transit_result:
        # 只有公交方案：自驾优先的用户按单一数据源打折
        final = transit_result["score"] * (0.9 if driving_first else 1.0)
    elif driving_result:
        final = driving_result["score"] * (1.0 if driving_first else 0.9)
    else:
        final = 0

    score = clamp_score(final)
    return {
        "commute_score": score,
        "commute_level": get_commute_level(score),
        "commute_tags": build_commute_tags(score, transit, driving),
        "transit_score": transit_result["score"] if transit_result else None,
        "driving_score": driving_result["score"] if driving_result else None,
        "detail": {"transit": transit_result, "driving": driving_result},
    }


# ---------------------------------------------------------------------------
# 生活圈评分 —— 对应《生活圈情况评分.txt》
# ---------------------------------------------------------------------------

def get_count_score(count):
    if count >= 10: return 100
    if count >= 6: return 85
    if count >= 3: return 70
    if count >= 1: return 55
    return 20


def get_poi_distance_score(distance):
    if distance is None: return 20
    if distance <= 300: return 100
    if distance <= 600: return 85
    if distance <= 1000: return 70
    return 45


def get_coverage_score(examples):
    n = len(examples or [])
    if n >= 3: return 100
    if n == 2: return 80
    if n == 1: return 60
    return 20


def calculate_dimension_score(item):
    """维度得分 = 数量分 40% + 距离分 40% + 覆盖分 20%"""
    return int(round(
        get_count_score(item.get("count", 0)) * 0.4
        + get_poi_distance_score(item.get("nearest_distance")) * 0.4
        + get_coverage_score(item.get("examples")) * 0.2
    ))


def calculate_facility(dimensions, facility_weights):
    """算出八个维度分，再按用户权重合成加权总分。"""
    detail, weighted_sum, weight_total = [], 0.0, 0.0

    for key in FACILITY_KEYS:
        item = (dimensions or {}).get(key) or {"count": 0, "nearest_distance": None, "examples": []}
        score = calculate_dimension_score(item)
        weight = float(facility_weights.get(key, 0))
        weighted_sum += score * weight
        weight_total += weight
        detail.append({
            "key": key,
            "name": FACILITY_NAMES[key],
            "count": item.get("count", 0),
            "nearest_distance": item.get("nearest_distance"),
            "examples": (item.get("examples") or [])[:3],
            "score": score,
            "weight": round(weight, 4),
        })

    weighted = clamp_score(weighted_sum / weight_total) if weight_total > 0 else 0
    plain = clamp_score(sum(d["score"] for d in detail) / len(detail)) if detail else 0
    return {
        "weighted_score": weighted,   # 按用户偏好加权，用于排序
        "plain_score": plain,         # 不加权的均分，用于对比展示"你的偏好改变了什么"
        "dimensions": detail,
    }


# ---------------------------------------------------------------------------
# 租金匹配与居住品质
# ---------------------------------------------------------------------------

def calculate_rent_fit(area, budget_min, budget_max):
    """
    片区参考租金区间与用户预算的匹配度。
    低于预算不重罚（便宜是好事，但可能意味着品质落差），高于预算按超出幅度递减。
    """
    ref_min = area.get("rent_ref_min")
    ref_max = area.get("rent_ref_max")
    if ref_min is None or ref_max is None:
        return {"score": 70, "note": "该片区缺少租金参考数据，按中性分处理"}

    overlap = min(budget_max, ref_max) - max(budget_min, ref_min)
    if overlap >= 0:
        span = max(1, ref_max - ref_min)
        ratio = min(1.0, (overlap + 1) / span)
        return {"score": clamp_score(75 + 25 * ratio),
                "note": "片区参考租金 {}-{} 元与预算重合".format(ref_min, ref_max)}

    if ref_min > budget_max:                       # 片区偏贵
        over_ratio = (ref_min - budget_max) / max(1.0, float(budget_max))
        return {"score": clamp_score(70 - over_ratio * 180),
                "note": "片区参考租金起步 {} 元，高于预算上限 {} 元".format(ref_min, budget_max)}

    over_ratio = (budget_min - ref_max) / max(1.0, float(budget_min))   # 片区偏便宜
    return {"score": clamp_score(85 - over_ratio * 40),
            "note": "片区参考租金上限 {} 元低于预算下限，租金压力小但需关注房源品质".format(ref_max)}


def calculate_quality(facility_detail):
    """
    居住品质的代理指标 —— 没有实测数据源，用 POI 结构派生：
    绿地和体育设施拉高，餐饮商业密度过高则拉低（嘈杂）。
    这是 proxy 而非实测，必须在输出里如实标注，不要当作硬事实展示。
    """
    by_key = {d["key"]: d for d in facility_detail}
    park = by_key.get("park", {}).get("score", 50)
    sports = by_key.get("sports", {}).get("score", 50)
    food_count = by_key.get("food", {}).get("count", 0)
    shopping_count = by_key.get("shopping", {}).get("count", 0)

    base = park * 0.5 + sports * 0.3 + 50 * 0.2
    noise_penalty = 0
    if food_count + shopping_count > 40:
        noise_penalty = min(18, (food_count + shopping_count - 40) * 0.5)

    return {
        "score": clamp_score(base - noise_penalty),
        "is_proxy": True,
        "note": "居住品质为代理指标，由绿地、体育设施与商业密度推算，非实地测评",
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def index_by_area(rows):
    return {row.get("area_id"): row for row in (rows or []) if row.get("area_id")}


def run(candidates, commute_results, poi_results, facility_weights,
        priority_weights, preferred_modes, commute_max_min,
        budget_min, budget_max, top_n=4):

    commute_map = index_by_area(commute_results)
    poi_map = index_by_area(poi_results)

    # 硬约束：通勤时间超出用户上限 30% 的直接淘汰。
    # 留 30% 容差是为了避免用户填 30 分钟时把所有候选都过滤光，导致无结果可推。
    hard_limit = commute_max_min * 1.3

    scored, dropped = [], []

    for area in (candidates or []):
        area_id = area.get("area_id")
        commute_row = commute_map.get(area_id) or {}
        poi_row = poi_map.get(area_id) or {}

        commute = calculate_commute(commute_row.get("transit"),
                                    commute_row.get("driving"),
                                    preferred_modes)

        transit_minutes = (commute_row.get("transit") or {}).get("duration_minutes")
        driving_minutes = (commute_row.get("driving") or {}).get("duration_minutes")

        # 硬约束必须按用户实际会用的通勤方式判定。
        # 用户说坐地铁，就不能拿他不会用的自驾时间把一个 70 分钟的地铁片区救回来。
        driving_first = "driving" in (preferred_modes or []) and "transit" not in (preferred_modes or [])
        if driving_first:
            judged_minutes = driving_minutes if driving_minutes is not None else transit_minutes
            mode_label = "自驾"
        else:
            judged_minutes = transit_minutes if transit_minutes is not None else driving_minutes
            mode_label = "公交地铁"

        if judged_minutes is None:
            dropped.append({"area_id": area_id, "name": area.get("name"),
                            "reason": "未能获取通勤路径数据"})
            continue

        if judged_minutes > hard_limit:
            dropped.append({
                "area_id": area_id, "name": area.get("name"),
                "reason": "{}通勤约 {} 分钟，超出可接受的 {} 分钟".format(
                    mode_label, int(judged_minutes), commute_max_min)
            })
            continue

        best_duration = judged_minutes

        facility = calculate_facility(poi_row.get("dimensions"), facility_weights)
        rent = calculate_rent_fit(area, budget_min, budget_max)
        quality = calculate_quality(facility["dimensions"])

        total = (commute["commute_score"] * priority_weights.get("commute", 0.4)
                 + facility["weighted_score"] * priority_weights.get("facility", 0.3)
                 + rent["score"] * priority_weights.get("rent", 0.2)
                 + quality["score"] * priority_weights.get("quality", 0.1))

        scored.append({
            "area_id": area_id,
            "name": area.get("name"),
            "district": area.get("district"),
            "center": {"lng": area.get("lng"), "lat": area.get("lat")},
            "area_tags": area.get("tags") or [],
            "rent_ref": {"min": area.get("rent_ref_min"), "max": area.get("rent_ref_max")},
            "scores": {
                "total": clamp_score(total),
                "commute": commute["commute_score"],
                "facility": facility["weighted_score"],
                "facility_plain": facility["plain_score"],
                "rent": rent["score"],
                "quality": quality["score"],
            },
            "commute": commute,
            "facility": facility,
            "rent_fit": rent,
            "quality": quality,
            "best_commute_minutes": int(best_duration),
        })

    scored.sort(key=lambda a: a["scores"]["total"], reverse=True)

    ranked = scored[:int(top_n)]
    for i, area in enumerate(ranked):
        area["rank"] = i + 1
        # 标出该片区最强和最弱的维度，供下游大模型写推荐理由和风险提示时定向取材
        dims = area["scores"]
        judged = {k: dims[k] for k in ["commute", "facility", "rent", "quality"]}
        area["strongest"] = max(judged, key=judged.get)
        area["weakest"] = min(judged, key=judged.get)

    return {"ranked_areas": ranked, "dropped_areas": dropped}


# --- 百炼代码节点入口 -------------------------------------------------------
def main(params):
    return run(
        candidates=params.get("candidates"),
        commute_results=params.get("commute_results"),
        poi_results=params.get("poi_results"),
        facility_weights=params.get("facility_weights") or {},
        priority_weights=params.get("priority_weights") or {},
        preferred_modes=params.get("preferred_modes"),
        commute_max_min=params.get("commute_max_min") or 45,
        budget_min=params.get("budget_min") or 0,
        budget_max=params.get("budget_max") or 999999,
        top_n=params.get("top_n") or 4,
    )


if __name__ == "__main__":
    candidates = [
        {"area_id": "A01", "name": "安德门片区", "district": "雨花台区",
         "lng": 118.768, "lat": 31.9954, "rent_ref_min": 1800, "rent_ref_max": 2800,
         "tags": ["地铁1号线"]},
        {"area_id": "A02", "name": "河西奥体片区", "district": "建邺区",
         "lng": 118.724, "lat": 32.004, "rent_ref_min": 3500, "rent_ref_max": 5500,
         "tags": ["新城区"]},
        {"area_id": "A03", "name": "马群片区", "district": "栖霞区",
         "lng": 118.8942, "lat": 32.0496, "rent_ref_min": 1600, "rent_ref_max": 2600,
         "tags": ["地铁2号线"]},
    ]
    commute_results = [
        {"area_id": "A01", "transit": {"duration_minutes": 28, "distance_km": 7.2, "transfer_count": 0},
         "driving": {"duration_minutes": 20, "distance_km": 8.0}},
        {"area_id": "A02", "transit": {"duration_minutes": 35, "distance_km": 9.1, "transfer_count": 1},
         "driving": {"duration_minutes": 24, "distance_km": 10.2}},
        {"area_id": "A03", "transit": {"duration_minutes": 72, "distance_km": 18.5, "transfer_count": 2},
         "driving": {"duration_minutes": 45, "distance_km": 20.1}},
    ]

    def dims(**kw):
        out = {}
        for key in FACILITY_KEYS:
            count, dist = kw.get(key, (3, 500))
            out[key] = {"count": count, "nearest_distance": dist,
                        "examples": ["示例A", "示例B", "示例C"][:min(3, count)]}
        return out

    poi_results = [
        {"area_id": "A01", "dimensions": dims(food=(28, 150), shopping=(12, 300),
                                              transport=(8, 400), park=(2, 900), sports=(3, 700))},
        {"area_id": "A02", "dimensions": dims(food=(35, 200), shopping=(20, 250),
                                              transport=(6, 500), park=(6, 300), sports=(9, 400))},
        {"area_id": "A03", "dimensions": dims(food=(15, 400), shopping=(6, 600),
                                              transport=(5, 350), park=(3, 800), sports=(2, 1100))},
    ]

    facility_weights = {"transport": 0.1818, "food": 0.1074, "shopping": 0.1322,
                        "life": 0.1405, "medical": 0.0992, "park": 0.1488,
                        "sports": 0.1322, "education": 0.0579}
    priority_weights = {"commute": 0.40, "facility": 0.28, "quality": 0.20, "rent": 0.12}

    result = run(candidates, commute_results, poi_results, facility_weights,
                 priority_weights, ["transit"], 40, 2500, 3500, top_n=4)

    for area in result["ranked_areas"]:
        s = area["scores"]
        print("#{} {} 总分{} (通勤{} 设施{} 租金{} 品质{}) 最强={} 最弱={}".format(
            area["rank"], area["name"], s["total"], s["commute"], s["facility"],
            s["rent"], s["quality"], area["strongest"], area["weakest"]))
    for d in result["dropped_areas"]:
        print("淘汰:", d["name"], "-", d["reason"])
