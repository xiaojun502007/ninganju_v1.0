# -*- coding: utf-8 -*-
"""
Agent B · 代码节点 11：结果组装

把三路结果合并成前端可以直接消费的最终 JSON：
    ranked_areas   代码节点 7 的真实评分（事实）
    area_copy      大模型节点 8 生成的推荐文案（表达）
    listings       大模型节点 10 挑选的房源（事实来自后端，挑选和理由来自模型）

这个节点还承担一项防线职责：**校验大模型有没有编造**。
凡是 area_copy 里出现了 ranked_areas 中不存在的片区名，一律丢弃；
凡是 listings 里出现了后端候选池中不存在的房源 id，一律丢弃。
大模型只被允许改写文字，不允许新增事实。

输出
    result_json  最终结果（Object）
"""

import json
import re
from datetime import datetime


def as_obj(value, default):
    """大模型节点的输出可能是字符串也可能已被平台解析成对象，两种都要能吃。"""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        # 模型有时会用 ```json 包裹，剥掉再解析
        fence = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.S)
        if fence:
            text = fence.group(1)
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return default
    return default


def index_copy(area_copy):
    """把文案按片区名建索引。模型偶尔会把 areas 包一层，这里都兼容。"""
    data = as_obj(area_copy, [])
    if isinstance(data, dict):
        data = data.get("areas") or data.get("result") or []
    out = {}
    for item in data:
        if isinstance(item, dict) and item.get("name"):
            out[item["name"].strip()] = item
    return out


def index_listings(listings_payload):
    data = as_obj(listings_payload, [])
    if isinstance(data, dict):
        data = data.get("results") or data.get("areas") or []
    out = {}
    for row in data:
        if isinstance(row, dict) and row.get("area_id"):
            out[row["area_id"]] = row.get("listings") or []
    return out


def sanitize_listings(picked, candidate_pool, limit=3):
    """
    只保留候选池里真实存在的房源，字段一律以后端数据为准，
    模型唯一被允许贡献的是 match_reason。
    """
    pool = {str(item.get("id")): item for item in (candidate_pool or []) if item.get("id") is not None}
    result = []
    for item in (picked or []):
        if not isinstance(item, dict):
            continue
        listing_id = str(item.get("id", ""))
        source = pool.get(listing_id)
        if not source:
            continue                       # 模型编出来的房源，丢弃
        merged = dict(source)
        reason = (item.get("match_reason") or "").strip()
        if reason:
            merged["match_reason"] = reason
        result.append(merged)
        if len(result) >= limit:
            break
    return result


def run(ranked_areas, area_copy, area_listings, listing_pool,
        work_location, weight_rationale, facility_weights,
        priority_weights, dropped_areas, listing_source):

    copy_map = index_copy(area_copy)
    picked_map = index_listings(area_listings)
    pool_map = index_listings(listing_pool)

    areas = []
    for area in (ranked_areas or []):
        name = (area.get("name") or "").strip()
        copy = copy_map.get(name) or {}
        area_id = area.get("area_id")

        listings = sanitize_listings(picked_map.get(area_id),
                                     pool_map.get(area_id), limit=3)

        areas.append({
            "rank": area.get("rank"),
            "area_id": area_id,
            "name": name,
            "district": area.get("district"),
            "center": area.get("center"),

            # 文案层：模型生成，兜底用真实数据拼出的保守表述
            "tagline": copy.get("tagline") or "通勤与生活配套综合表现较好",
            "reason": copy.get("reason") or _fallback_reason(area),
            "risk": copy.get("risk") or _fallback_risk(area),
            "tags": (copy.get("tags") or area.get("area_tags") or [])[:4],

            # 事实层：全部来自代码节点 7 的真实计算
            "scores": area.get("scores"),
            "commute": area.get("commute"),
            "facility": area.get("facility"),
            "rent_fit": area.get("rent_fit"),
            "quality": area.get("quality"),
            "best_commute_minutes": area.get("best_commute_minutes"),

            "listings": listings,
            "listing_count": len(listings),
        })

    return {
        "result_json": {
            "success": True,
            "schema_version": "1.0",
            "work": work_location,
            "areas": areas,
            "explain": {
                "weight_rationale": weight_rationale or [],
                "facility_weights": facility_weights or {},
                "priority_weights": priority_weights or {},
            },
            "meta": {
                "evaluated_at": datetime.now().isoformat(timespec="seconds"),
                "area_count": len(areas),
                "dropped_areas": dropped_areas or [],
                "listing_source": listing_source or "unknown",
                "disclaimer": "通勤与生活圈评分基于高德地图实时数据计算；"
                              "居住品质为代理指标；房源信息仅供参考，请以实地看房为准。",
            },
        }
    }


def _fallback_reason(area):
    """模型没给文案时，用真实数据拼一句保守但准确的话，绝不留空。"""
    scores = area.get("scores") or {}
    minutes = area.get("best_commute_minutes")
    parts = []
    if minutes is not None:
        parts.append("到工作地最快约 {} 分钟".format(minutes))
    if scores.get("facility") is not None:
        parts.append("生活圈设施加权得分 {} 分".format(scores["facility"]))
    return "，".join(parts) + "。" if parts else "综合评分较高。"


def _fallback_risk(area):
    weakest = area.get("weakest")
    label = {"commute": "通勤", "facility": "生活配套",
             "rent": "租金匹配度", "quality": "居住品质"}.get(weakest, "部分条件")
    return "该片区在{}方面相对较弱，建议实地确认后再做决定。".format(label)


# --- 百炼代码节点入口 -------------------------------------------------------
def main(params):
    return run(
        ranked_areas=params.get("ranked_areas"),
        area_copy=params.get("area_copy"),
        area_listings=params.get("area_listings"),
        listing_pool=params.get("listing_pool"),
        work_location=params.get("work_location"),
        weight_rationale=params.get("weight_rationale"),
        facility_weights=params.get("facility_weights"),
        priority_weights=params.get("priority_weights"),
        dropped_areas=params.get("dropped_areas"),
        listing_source=params.get("listing_source"),
    )


if __name__ == "__main__":
    ranked = [{
        "rank": 1, "area_id": "A01", "name": "安德门片区", "district": "雨花台区",
        "center": {"lng": 118.768, "lat": 31.9954},
        "scores": {"total": 82, "commute": 89, "facility": 84, "rent": 83, "quality": 66},
        "best_commute_minutes": 28, "weakest": "quality", "area_tags": ["地铁1号线"],
    }]
    # 模型编了一个不存在的片区，还编了一条不存在的房源 —— 都应该被拦掉
    copy = '```json\n[{"name":"安德门片区","tagline":"通勤高效","reason":"地铁直达","risk":"房龄偏大","tags":["地铁1号线","通勤友好"]},{"name":"虚构片区","tagline":"不存在"}]\n```'
    pool = [{"area_id": "A01", "listings": [
        {"id": "L001", "title": "安德门 一室一厅", "rent": 2400},
        {"id": "L002", "title": "安德门 开间", "rent": 2100}]}]
    picked = [{"area_id": "A01", "listings": [
        {"id": "L001", "match_reason": "步行8分钟到地铁"},
        {"id": "L999", "match_reason": "模型编造的房源"}]}]

    out = run(ranked, copy, picked, pool, {"address": "德基广场"},
              ["常做饭，提高了购物权重"], {}, {}, [], "sample")
    area = out["result_json"]["areas"][0]
    print("片区数:", len(out["result_json"]["areas"]), "（虚构片区已被过滤）")
    print("tagline:", area["tagline"])
    print("房源数:", area["listing_count"], "->", [l["id"] for l in area["listings"]])
    print("match_reason:", area["listings"][0].get("match_reason"))
