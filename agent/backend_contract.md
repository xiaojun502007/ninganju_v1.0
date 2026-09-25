# 后端接口契约（百炼 API 节点调用）

混合模式下的分工：**后端只出原始数据，不做评分**。评分和排序全部在百炼代码节点里，这样工作流的编排逻辑是可见的，同时高德 key 不出你的服务器、并发和缓存也好控制。

这五个接口都是新增的，不影响现有的 `/api/recommend-areas`、`/api/commute`、`/api/facilities`——旧接口可以继续给现有前端用，等新链路跑通再切。

## 通用约定

- **鉴权**：Header `X-Agent-Key`，值与环境变量 `NINGANJU_AGENT_KEY` 比对。百炼是从公网调你的后端，裸接口等于把高德配额和数据库敞开给所有人。
- **公网可达**：本地开发用 ngrok / cpolar 之类做内网穿透；线上部署直接用域名。
- **失败语义**：单个片区数据取不到时，在结果里把该片区对应字段置 `null`，**不要整个请求失败**。代码节点 7 会把拿不到通勤数据的片区淘汰掉并记录原因，比整条工作流报错好得多。

---

## 1. `POST /api/agent/submit-preference`

Agent A 的插件回调。落库并返回 preference_id。

**请求**：见 [`agent_a/submit_preference_openapi.yaml`](agent_a/submit_preference_openapi.yaml) 的 `Preference` schema。

**响应**
```json
{ "success": true, "preference_id": "pref_20260825_a1b2c3", "message": "偏好已记录" }
```

**实现要点**
- 落到 `rent_preference` 表（表已存在，需扩几个列存 `lifestyle_tags`、`priority_ranking`、原始 JSON）
- 必填项缺失返回 400，并在 message 里说明缺哪项——Agent A 会据此继续追问

---

## 2. `POST /api/agent/locate-and-recall`

工作地地理编码 + 候选片区召回，合并成一次调用。

**请求**
```json
{
  "work_query": "南京市德基广场",
  "budget_min": 2500, "budget_max": 3500,
  "commute_max_minutes": 40,
  "preferred_modes": ["transit"],
  "limit": 10
}
```

**响应**
```json
{
  "success": true,
  "work_location": {
    "address": "江苏省南京市秦淮区德基广场",
    "lng": 118.7896, "lat": 32.0421, "district": "秦淮区"
  },
  "candidates": [
    {
      "area_id": "A01", "name": "安德门片区", "district": "雨花台区",
      "lng": 118.768, "lat": 31.9954,
      "rent_ref_min": 1800, "rent_ref_max": 2800,
      "tags": ["地铁1号线", "老城南"],
      "straight_km": 5.2
    }
  ]
}
```

**实现要点**

- 地理编码走高德 `/v3/geocode/geo`，失败时回落到 `api_server.py` 里已有的 `TRUSTED_NANJING_LOCATIONS` 字典（约 80 个南京地名坐标，正好能兜住绝大多数情况）
- **召回这一步不能省。** 按直线距离粗筛的换算参考：地铁通勤 40 分钟 ≈ 直线 12 公里，自驾 40 分钟 ≈ 直线 18 公里。先砍到 8~12 个候选，否则后面对每个片区都要调 1 次路径规划 + 8 次 POI 查询，并发上限 3，演示时要跑好几分钟
- 预算过滤要留余量：`rent_ref_min > budget_max * 1.25` 才排除，卡太死会出现无结果
- 候选片区库需要新建一张 `area_library` 表，见下方

---

## 3. `POST /api/agent/commute-raw`

批量通勤原始数据。**只返回时间、距离、换乘次数，不算分。**

**请求**
```json
{
  "work": { "lng": 118.7896, "lat": 32.0421 },
  "areas": [{ "area_id": "A01", "lng": 118.768, "lat": 31.9954 }],
  "modes": ["transit", "driving"]
}
```

**响应**
```json
{
  "success": true,
  "results": [
    {
      "area_id": "A01",
      "transit": { "duration_minutes": 28, "distance_km": 7.2, "transfer_count": 0 },
      "driving": { "duration_minutes": 20, "distance_km": 8.0 },
      "polyline": [[118.768, 31.9954]]
    }
  ]
}
```

**实现要点**
- 复用 `api_server.py` 里 `handle_commute` 已有的高德路径规划逻辑，剥掉评分部分
- **并发严格控制在 3 以内**，用信号量或线程池
- `transfer_count` 从高德公交方案的 `segments` 里数换乘段，注意步行段不算换乘
- `polyline` 可选，前端 `AmapRouteMap` 要画路线才需要，不需要就别传（数据量很大）

---

## 4. `POST /api/agent/poi-raw`

批量八类 POI 汇总。**只返回数量、最近距离、示例名，不算分。**

**请求**
```json
{
  "areas": [{ "area_id": "A01", "lng": 118.768, "lat": 31.9954 }],
  "radius": 1000
}
```

**响应**
```json
{
  "success": true,
  "results": [
    {
      "area_id": "A01",
      "dimensions": {
        "shopping":  { "count": 12, "nearest_distance": 300, "examples": ["苏果超市", "盒马鲜生"] },
        "food":      { "count": 28, "nearest_distance": 150, "examples": ["..."] },
        "transport": { "count": 8,  "nearest_distance": 400, "examples": ["..."] },
        "medical":   { "count": 5,  "nearest_distance": 600, "examples": ["..."] },
        "education": { "count": 4,  "nearest_distance": 700, "examples": ["..."] },
        "sports":    { "count": 3,  "nearest_distance": 700, "examples": ["..."] },
        "park":      { "count": 2,  "nearest_distance": 900, "examples": ["..."] },
        "life":      { "count": 15, "nearest_distance": 200, "examples": ["..."] }
      }
    }
  ]
}
```

**实现要点**
- 完全复用 `handle_facilities` 已有的高德周边搜索 + `SimplifiedPoi` 清洗逻辑，剥掉 `calculateDimensionScore` 部分（评分挪到代码节点 7）
- 八个 key 必须与 `node02` / `node07` 里的 `FACILITY_KEYS` 逐字一致，任何一个拼错该维度就恒为 0 分
- types 参数对应关系：`060000`购物 `050000`餐饮 `150000`交通 `090000`医疗 `140000`科教 `080000`体育 `110000`公园 `070000`生活服务
- **并发严格 ≤ 3**。一个片区要查 8 类，10 个候选就是 80 次请求
- **一定要加缓存。** POI 分布月度内几乎不变，按 `area_id` 缓存 7 天，能把演示耗时从几分钟压到几秒。这是整条链路上性价比最高的一处优化
- `examples` 取该维度距离最近的 3 个 POI 名称，覆盖分就是按这个数组长度算的

---

## 5. `POST /api/agent/listings`

房源候选检索。**这里就是可插拔适配器的位置。**

**请求**
```json
{
  "areas": [{ "area_id": "A01", "name": "安德门片区", "lng": 118.768, "lat": 31.9954 }],
  "budget_min": 2500, "budget_max": 3500,
  "filters": {
    "rent_type": "整租",
    "layout": ["一室一厅"],
    "must_have": ["独立卫生间", "电梯"],
    "deal_breakers": ["临街嘈杂"],
    "metro_walk_max_meters": 800
  },
  "per_area_limit": 8
}
```

**响应**
```json
{
  "success": true,
  "source": "sample",
  "source_note": "样本数据，仅供参考，不代表真实在租房源",
  "results": [
    {
      "area_id": "A01",
      "listings": [
        {
          "id": "L001",
          "title": "安德门大街 精装一室一厅",
          "community": "宁南新寓",
          "layout": "一室一厅", "area_sqm": 45,
          "rent": 2400, "rent_type": "整租",
          "floor": "6/18", "orientation": "南",
          "lng": 118.7695, "lat": 31.9961,
          "metro": "1号线安德门站 步行8分钟",
          "features": ["独立卫生间", "电梯", "家电齐全"],
          "image_url": null,
          "detail_url": null
        }
      ]
    }
  ]
}
```

**适配器设计**

后端内部定义一个统一接口，上层只认这个契约：

```python
class ListingSource:
    def search(self, area, budget_min, budget_max, filters, limit) -> list[dict]:
        ...

# 三种实现，用环境变量 LISTING_SOURCE 切换
class SampleListingSource(ListingSource): ...      # 自建样本库，先跑通用
class ThirdPartyListingSource(ListingSource): ...  # 云市场 API，买到了再接
class NullListingSource(ListingSource): ...        # 返回空，前端优雅降级
```

无论最终接哪个数据源，百炼工作流侧一行都不用改。

**关于 `source` 和 `source_note`**：必须如实透传到前端展示。样本数据就标"样本数据，仅供参考"，第三方数据就标来源和抓取时间。这既是合规要求，也是答辩时的加分项——比含糊其辞地把样本数据当真实房源展示要好。

---

## 新增数据表

### `area_library` — 南京候选片区库

召回节点的数据基础，是整套系统里唯一需要人工整理的数据。

| 字段 | 类型 | 说明 |
|---|---|---|
| `area_id` | text PK | A01, A02... |
| `name` | text | 片区名，如"安德门片区" |
| `district` | text | 行政区 |
| `lng` / `lat` | real | 片区中心坐标 |
| `rent_ref_min` / `rent_ref_max` | integer | 参考租金区间（元/月，一室一厅口径） |
| `tags` | text (JSON) | `["地铁1号线", "老城南"]` |
| `metro_lines` | text (JSON) | 覆盖的地铁线路 |
| `enabled` | integer | 是否参与召回 |

`api_server.py` 里的 `TRUSTED_NANJING_LOCATIONS` 已经有约 80 个南京地名和坐标，是很好的种子——挑出其中适合居住的 30~50 个，补上行政区、参考租金和标签即可。参考租金可以从公开的租房行情数据整理，标注为"参考区间"而非精确值。

### `area_evaluation_cache` — 评估结果缓存

| 字段 | 说明 |
|---|---|
| `area_id` | 片区 |
| `poi_dimensions` | JSON，八类 POI 汇总 |
| `updated_at` | 缓存时间，7 天过期 |

只缓存 POI（与用户无关，可跨用户复用）。通勤数据依赖工作地址，缓存价值低，除非按 `(work_lng, work_lat, area_id)` 做键。

---

## 环境变量

在现有 `.env.example` 基础上补充（沿用已有的 `AMAP_WEB_SERVICE_KEY` 命名，不要另起 `AMAP_KEY`）：

```
NINGANJU_AGENT_KEY=      # 自己生成的随机串，百炼 API 节点 Header 用同一个值
DASHSCOPE_API_KEY=       # 百炼 API Key
BAILIAN_COLLECT_APP_ID=  # Agent A 智能体应用 ID
BAILIAN_RECOMMEND_APP_ID=# Agent B 工作流应用 ID
LISTING_SOURCE=sample
AMAP_MAX_CONCURRENCY=3
```

> 一处提醒：高德 key `71e1f878...` 在 `生活圈情况评分.txt` 里是明文写着的，而那份文档在 git 仓库内（仓库根是「最终产品开发」目录）。`.gitignore` 已经挡住了 `.env` 和 `.env.local`，但挡不住这份 txt。作业提交或代码外发前建议先把它替换成占位符。
