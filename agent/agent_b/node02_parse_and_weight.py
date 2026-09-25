# -*- coding: utf-8 -*-
"""
Agent B · 代码节点 2：偏好解析与权重推导

输入（来自开始节点）
    preference_json : String  Agent A 通过 submit_preference 产出的偏好 JSON 字符串

输出
    work_query        String  用于地理编码的地址
    budget_min        Number
    budget_max        Number
    commute_max_min   Number
    preferred_modes   Array
    facility_weights  Object  八类生活圈设施权重，和为 1
    priority_weights  Object  四个评估维度权重，和为 1
    filters           Object  房源检索的过滤条件
    weight_rationale  Array   权重推导过程，用于向用户解释"为什么这么算"
    preference        Object  规范化后的完整偏好，透传给后续节点

设计要点
    权重不由大模型给出，而是在这里按确定性规则从 lifestyle_tags 推导。
    好处有三：可复现（同样的标签永远得到同样的权重）、可解释（weight_rationale
    能直接展示给用户）、模型不用做小数运算（它做不准）。

平台适配
    百炼代码节点的入口函数签名如有出入，只需改动文件末尾的 main() 包装，
    上面的纯函数不用动。
"""

import json

# ---------------------------------------------------------------------------
# 八类生活圈设施 —— 必须与《生活圈情况评分.txt》和后端 handle_facilities 完全一致
# ---------------------------------------------------------------------------

FACILITY_KEYS = ["shopping", "food", "transport", "medical",
                 "education", "sports", "park", "life"]

FACILITY_NAMES = {
    "shopping": "购物服务", "food": "餐饮服务", "transport": "交通设施",
    "medical": "医疗资源", "education": "科教文化", "sports": "体育休闲",
    "park": "公园绿地", "life": "生活服务",
}

# 无任何生活画像信息时的基线权重（来宁青年的普适分布：交通和吃饭最要紧）
BASELINE_WEIGHTS = {
    "transport": 0.18, "food": 0.16, "shopping": 0.14, "life": 0.14,
    "medical": 0.12, "park": 0.10, "sports": 0.09, "education": 0.07,
}

# lifestyle_tag -> 权重增量。归一化在后面统一做，这里只表达"相对更重要多少"
TAG_ADJUSTMENTS = {
    "cook_often":       ({"shopping": 0.05, "life": 0.03},
                         "常做饭，提高了买菜购物和生活服务的权重"),
    "eat_out":          ({"food": 0.06},
                         "常在外就餐，提高了餐饮服务的权重"),
    "fitness":          ({"sports": 0.07, "park": 0.04},
                         "有健身习惯，提高了体育休闲和公园绿地的权重"),
    "night_owl":        ({"transport": 0.06, "life": 0.04},
                         "夜归较多，提高了交通设施和便利店等生活服务的权重"),
    "online_shopping":  ({"life": 0.05},
                         "网购频繁，提高了快递驿站等生活服务的权重"),
    "has_child":        ({"education": 0.09, "medical": 0.05, "park": 0.03},
                         "家中有孩子，显著提高了教育、医疗和公园的权重"),
    "has_pet":          ({"park": 0.07},
                         "养宠物，提高了公园绿地的权重"),
    "elder_care":       ({"medical": 0.07, "park": 0.03},
                         "与老人同住，提高了医疗资源和公园的权重"),
    "health_sensitive": ({"medical": 0.09},
                         "就医需求较多，显著提高了医疗资源的权重"),
    "quiet_preference": ({"park": 0.04, "food": -0.03, "shopping": -0.03},
                         "偏好安静环境，降低了餐饮商业密度的权重"),
    "car_owner":        ({"transport": -0.06, "shopping": 0.03},
                         "自驾出行，降低了对地铁公交站点的权重依赖"),
    "homebody":         ({"life": 0.05, "food": 0.03},
                         "居家为主，提高了近距离生活服务的权重"),
}

# priority_ranking 的名次 -> 权重。四档差距明显但不极端，避免单一维度通吃
RANK_WEIGHTS = [0.40, 0.28, 0.20, 0.12]
PRIORITY_KEYS = ["commute", "facility", "rent", "quality"]
PRIORITY_NAMES = {"commute": "通勤", "facility": "生活便利",
                  "rent": "租金", "quality": "居住品质"}


def normalize(weights):
    """把权重字典裁剪到非负并归一化到和为 1。"""
    clipped = {k: max(0.0, float(v)) for k, v in weights.items()}
    total = sum(clipped.values())
    if total <= 0:
        n = len(clipped)
        return {k: round(1.0 / n, 4) for k in clipped}
    return {k: round(v / total, 4) for k, v in clipped.items()}


def build_facility_weights(lifestyle_tags, preferred_modes):
    """从生活画像标签推导八类设施权重，同时产出可展示的推导说明。"""
    weights = dict(BASELINE_WEIGHTS)
    rationale = []

    for tag in (lifestyle_tags or []):
        entry = TAG_ADJUSTMENTS.get(tag)
        if not entry:
            continue          # 词表外的标签直接忽略，不让模型自创的值污染权重
        deltas, explanation = entry
        for key, delta in deltas.items():
            weights[key] = weights.get(key, 0.0) + delta
        rationale.append(explanation)

    # 通勤方式对交通设施权重的影响：自驾用户不必为了地铁口牺牲其他条件
    modes = preferred_modes or ["transit"]
    if "transit" in modes:
        weights["transport"] += 0.04
        rationale.append("以地铁公交通勤，提高了交通设施的权重")
    elif "driving" in modes:
        weights["transport"] -= 0.04
        rationale.append("以自驾通勤，交通设施权重相应下调")

    if not rationale:
        rationale.append("未采集到明显的生活习惯偏好，采用面向来宁青年的基线权重")

    return normalize(weights), rationale


def build_priority_weights(ranking):
    """把四维排序转成权重。排序缺失或不合法时回落到通勤优先的默认顺序。"""
    ranking = [k for k in (ranking or []) if k in PRIORITY_KEYS]

    seen, ordered = set(), []
    for key in ranking:
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    for key in PRIORITY_KEYS:          # 补齐用户没提到的维度
        if key not in seen:
            ordered.append(key)

    ordered = ordered[:4]
    weights = {key: RANK_WEIGHTS[i] for i, key in enumerate(ordered)}
    note = "评估权重按你的优先级排序设定：" + " > ".join(
        "{} {}%".format(PRIORITY_NAMES[k], round(weights[k] * 100)) for k in ordered
    )
    return normalize(weights), note


def build_filters(preference):
    """整理房源检索的过滤条件。"""
    housing = preference.get("housing") or {}
    commute = preference.get("commute") or {}
    budget = preference.get("budget") or {}
    return {
        "rent_type": housing.get("rent_type") or "不限",
        "layout": housing.get("layout") or [],
        "area_min_sqm": housing.get("area_min_sqm"),
        "must_have": housing.get("must_have") or [],
        "deal_breakers": housing.get("deal_breakers") or [],
        "move_in_date": housing.get("move_in_date"),
        "metro_walk_max_meters": commute.get("metro_walk_max_meters"),
        "budget_min": budget.get("min"),
        "budget_max": budget.get("max"),
    }


def parse_preference(preference_json):
    """解析并校验偏好 JSON。必填项缺失直接抛错，让工作流走异常分支。"""
    pref = preference_json if isinstance(preference_json, dict) else json.loads(preference_json)

    work = pref.get("work") or {}
    budget = pref.get("budget") or {}
    commute = pref.get("commute") or {}

    work_query = (work.get("address_query") or work.get("address_raw") or "").strip()
    if not work_query:
        raise ValueError("缺少工作地址，无法进行地段评估")

    budget_min = budget.get("min")
    budget_max = budget.get("max")
    if budget_min is None or budget_max is None:
        raise ValueError("缺少预算区间，无法进行地段评估")
    budget_min, budget_max = int(budget_min), int(budget_max)
    if budget_min > budget_max:
        budget_min, budget_max = budget_max, budget_min

    max_minutes = commute.get("max_minutes")
    if max_minutes is None:
        # 给一个宽松默认值让流程能跑完，但在 completeness 里留痕
        max_minutes = 45
        completeness = pref.setdefault("completeness", {})
        completeness.setdefault("missing", []).append("commute.max_minutes")
    max_minutes = int(max_minutes)

    modes = commute.get("preferred_modes") or ["transit"]

    # 地址里没有"南京"时补上，避免高德把地址匹配到外地同名地点
    if "南京" not in work_query:
        work_query = "南京市" + work_query

    return pref, work_query, budget_min, budget_max, max_minutes, modes


def run(preference_json):
    pref, work_query, budget_min, budget_max, max_minutes, modes = parse_preference(preference_json)

    lifestyle_tags = ((pref.get("profile") or {}).get("lifestyle_tags")) or []
    facility_weights, facility_rationale = build_facility_weights(lifestyle_tags, modes)
    priority_weights, priority_note = build_priority_weights(pref.get("priority_ranking"))

    return {
        "work_query": work_query,
        "budget_min": budget_min,
        "budget_max": budget_max,
        "commute_max_min": max_minutes,
        "preferred_modes": modes,
        "facility_weights": facility_weights,
        "priority_weights": priority_weights,
        "filters": build_filters(pref),
        "weight_rationale": facility_rationale + [priority_note],
        "preference": pref,
    }


# --- 百炼代码节点入口 -------------------------------------------------------
def main(params):
    return run(params.get("preference_json"))


if __name__ == "__main__":
    # 本地自测：常做饭 + 健身 + 怕吵，最看重通勤
    demo = {
        "schema_version": "1.0",
        "work": {"address_raw": "新街口德基广场", "address_query": "南京市德基广场"},
        "budget": {"min": 2500, "max": 3500},
        "commute": {"max_minutes": 40, "preferred_modes": ["transit"],
                    "metro_walk_max_meters": 800},
        "housing": {"rent_type": "整租", "layout": ["一室一厅"],
                    "must_have": ["独立卫生间", "电梯"], "deal_breakers": ["临街嘈杂"]},
        "profile": {"lifestyle_tags": ["cook_often", "fitness", "quiet_preference"]},
        "priority_ranking": ["commute", "facility", "quality", "rent"],
    }
    out = run(json.dumps(demo, ensure_ascii=False))
    print("facility_weights:", json.dumps(out["facility_weights"], ensure_ascii=False))
    print("sum =", round(sum(out["facility_weights"].values()), 4))
    print("priority_weights:", json.dumps(out["priority_weights"], ensure_ascii=False))
    print("rationale:")
    for line in out["weight_rationale"]:
        print("  -", line)
