# Agent B · 地段评估工作流（百炼「工作流应用」）

## 一条必须守住的原则

**大模型不做决策，只做表达。**

推荐哪几个片区、按什么顺序排，完全由代码节点 7 基于高德真实数据算出来。大模型只在节点 8 和节点 10 出现，任务是把分数翻译成人话、从已有候选里挑房源。节点 11 还会校验模型有没有编造，凡是真实数据里不存在的片区名和房源 ID 一律丢弃。

这样做的直接好处：答辩时被问"你凭什么推荐这个片区"，你能把 `scores` 明细摊开——通勤 89 分是因为地铁 28 分钟零换乘，生活圈 84 分是八个维度按用户权重加出来的。这是原来"让 LLM 直接吐 4 个片区"给不出的东西。

## 节点编排

采用**混合模式**：高德调用走你的 Python 后端（保护 key、控并发、做缓存），评分和排序逻辑放百炼代码节点（编排结构可见，符合 workflow agent 的展示需求）。

| # | 节点名 | 类型 | 输入 | 输出 |
|---|---|---|---|---|
| 1 | 开始 | 开始 | `preference_json` (String) | — |
| 2 | 偏好解析与配权 | 代码 (Python) | `preference_json` | `work_query` `budget_min` `budget_max` `commute_max_min` `preferred_modes` `facility_weights` `priority_weights` `filters` `weight_rationale` `preference` |
| 3 | 工作地解析与候选召回 | API | 节点 2 全部输出 | `work_location` `candidates` |
| 4 | 通勤原始数据 | API | `work_location` `candidates` `preferred_modes` | `commute_results` |
| 5 | 生活圈原始数据 | API | `candidates` | `poi_results` |
| 6 | — | 并行汇聚 | 节点 4、5 | — |
| 7 | 片区评分与排序 | 代码 (Python) | 节点 2、3、4、5 输出 | `ranked_areas` `dropped_areas` |
| 8 | 片区文案生成 | 大模型 | `ranked_areas` `preference` | `area_copy` |
| 9 | 房源候选检索 | API | `ranked_areas` `filters` `budget_*` | `listing_pool` `listing_source` |
| 10 | 房源筛选与匹配理由 | 大模型 | `listing_pool` `preference` `ranked_areas` | `area_listings` |
| 11 | 结果组装 | 代码 (Python) | 节点 2、3、7、8、9、10 输出 | `result_json` |
| 12 | 结束 | 结束 | `result_json` | — |

**节点 4 和 5 配成并行分支。** 两者都是耗时的高德批量调用，串行会让整个工作流慢一倍。后端各自在内部把并发压到 3 以内（《生活圈情况评分.txt》的硬性要求），百炼这边只管并行发两个请求。

节点 3 把地理编码和候选召回合并成一次调用，少一次网络往返——它们逻辑上就是一件事："定位工作地，圈出周边够得着的片区"。

代码节点 2、7、11 的完整实现见同目录下的 `node02_*.py` / `node07_*.py` / `node11_*.py`，可直接粘贴。若百炼代码节点的入口函数签名与 `def main(params)` 不同，只需改文件末尾的包装，上面的纯函数不用动。

## API 节点配置

四个 API 节点都指向你自己的后端，接口契约见 [`../backend_contract.md`](../backend_contract.md)。统一配置：

- **Method**：POST
- **Header**：`Content-Type: application/json`、`X-Agent-Key: {{环境变量 NINGANJU_AGENT_KEY}}`
- **超时**：节点 4、5 设到 60 秒以上（高德批量调用 + 并发限流，快不了）
- **失败重试**：1 次

---

## 节点 8 · 片区文案生成（大模型节点提示词）

模型建议 qwen-max，温度 0.7（文案需要一点变化），开启 JSON 输出模式。

```
你是宁安居的居住片区分析师。系统已经基于高德地图的真实通勤路径和周边 POI 数据，
算出了适合这位用户的片区排名。你的任务是把这些数字写成用户看得懂的推荐说明。

## 用户画像
{{节点2.preference}}

## 已评估的片区（含全部真实数据）
{{节点7.ranked_areas}}

## 你的任务
为每个片区生成 tagline、reason、risk、tags 四项文案。

## 硬性约束

1. **只能使用输入数据中出现的数字。** 输入里没有的数值一律不许写。
   特别是租金——你只能引用 rent_ref 区间并注明"参考"，绝不能写出具体某套房子的价格。

2. **reason 必须至少各引用一项通勤数据和一项设施数据**，并且数字要和输入完全一致。
   好的写法："地铁 28 分钟直达且无需换乘，周边餐饮 POI 28 处、最近仅 150 米"
   坏的写法："交通便利，配套成熟"（没有引用任何数据，等于没说）

3. **risk 必须针对该片区 weakest 字段指向的那个维度写**，写具体的短板，不要写套话。
   如果 weakest 是 quality 且 quality.is_proxy 为 true，措辞要留有余地
   （"绿地和体育设施相对偏少"而不是"居住环境差"）。

4. **不推荐任何具体房源、小区、中介或联系方式。** 那是后续环节的事。

5. tagline 控制在 12 字以内，tags 给 3 到 4 个短标签。

6. 用平实的中文，像在跟朋友解释，不要用"赋能""生态位""宜居标杆"这类词。

## 输出格式
严格 JSON 数组，不要 Markdown 代码块，不要任何解释性文字。
name 字段必须与输入中的片区名逐字一致，否则该条会被系统丢弃。

[
  {
    "name": "与输入完全一致的片区名",
    "tagline": "12字以内",
    "reason": "引用真实数据的推荐理由，60-100字",
    "risk": "针对最弱维度的具体风险提示，40-70字",
    "tags": ["标签1", "标签2", "标签3"]
  }
]
```

---

## 节点 10 · 房源筛选与匹配理由（大模型节点提示词）

模型建议 qwen-plus（这一步是筛选和短文案，不需要 max），温度 0.3（要稳），开启 JSON 输出模式。

```
你是宁安居的房源匹配助手。系统已经为每个推荐片区检索出了一批候选房源。
你的任务是从每个片区的候选中挑出最匹配这位用户的 3 套，并说明为什么匹配。

## 用户需求
预算：{{节点2.budget_min}} - {{节点2.budget_max}} 元/月
硬性要求与排除项：{{节点2.filters}}
完整偏好：{{节点2.preference}}

## 各片区候选房源
{{节点9.listing_pool}}

## 硬性约束

1. **只能从候选列表里选，绝对不能新增房源。**
   你输出的每一个 id 都必须在候选列表中原样存在。系统会逐条校验，
   编造的 id 会被直接丢弃，那个片区就会少一套房源。

2. **不要修改任何房源字段。** 你只需要输出 id 和 match_reason 两项，
   标题、租金、面积、坐标等全部由系统从原始数据取，你改了也不会生效。

3. **候选不足 3 套时，有几套输出几套。** 不许为了凑数编造。

4. **match_reason 只能引用候选数据里已有的字段和用户的明确需求。**
   好的写法："2400 元在你的预算内，一室一厅带独卫，步行 8 分钟到地铁 1 号线"
   坏的写法："性价比高，值得考虑"（没有对应到任何具体条件）

5. 优先满足用户的 must_have，严格规避 deal_breakers。
   在满足硬条件的前提下，再按预算贴合度和交通便利度排序。

6. match_reason 控制在 40 字以内。

## 输出格式
严格 JSON 数组，不要 Markdown 代码块，不要解释文字。

[
  {
    "area_id": "与候选数据一致的片区ID",
    "listings": [
      { "id": "候选中真实存在的房源ID", "match_reason": "40字以内的匹配理由" }
    ]
  }
]
```

---

## 调用方式

工作流应用通过 DashScope 的应用调用接口触发，`preference_json` 作为业务参数传入：

```
POST https://dashscope.aliyuncs.com/api/v1/apps/{APP_ID}/completion
Authorization: Bearer {DASHSCOPE_API_KEY}
Content-Type: application/json

{
  "input": {
    "prompt": "",
    "biz_params": {
      "preference_json": "{\"schema_version\":\"1.0\",\"work\":{...},...}"
    }
  },
  "parameters": {},
  "debug": {}
}
```

> 这段调用格式请对照你控制台里该应用的「API 调用示例」再核一遍——百炼的参数传递方式（`biz_params` 还是直接展开成自定义入参）随应用类型和控制台版本有过调整，以你实际看到的示例为准。节点设计和代码节点不受影响。

## 前端对接

节点 12 输出的 `result_json` 结构是照着你现有前端类型设计的，改造量很小：

| result_json 字段 | 对应现有前端 |
|---|---|
| `areas[].name/tagline/reason/risk/tags` | `RecommendedArea`（[src/types/recommendation.ts](../../src/types/recommendation.ts)），字段名完全一致 |
| `areas[].commute` | `CommuteData.commuteScoreResult`（[src/services/commuteService.ts](../../src/services/commuteService.ts)） |
| `areas[].facility.dimensions` | `FacilityData.poiSummary`，可直接喂给 `FacilityRadarChart` 画雷达图 |
| `explain.weight_rationale` | 新增展示项——把"为什么这么推荐"讲给用户听，是这次改造最值得放到界面上的东西 |
| `areas[].listings` | 新增房源卡片区 |

最大的变化是**一次调用拿回全部数据**。现在的流程是先 `/api/recommend-areas` 拿片区，用户点进去再分别调 `/api/commute` 和 `/api/facilities`；新流程在推荐生成时评分就已经算完了，分析页直接读缓存结果即可，不必二次请求。
