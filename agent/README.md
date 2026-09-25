# 宁安居双 Agent 设计（阿里云百炼）

面向来宁工作青年的租房地段推荐。分两个 Agent：**Agent A** 通过多轮对话把模糊的租房意向变成结构化偏好，**Agent B** 用工作流基于高德真实数据评估南京各片区，输出地段推荐和房源。

```
用户 ──对话──▶ Agent A（智能体应用）
                    │ submit_preference 插件
                    ▼
              偏好 JSON（preference_contract.json）
                    │ biz_params
                    ▼
              Agent B（工作流应用）
                    │ API 节点 ──▶ 你的 Python 后端 ──▶ 高德 API
                    │ 代码节点 ──▶ 通勤评分 / 生活圈评分 / 排序
                    │ 大模型节点 ─▶ 推荐文案 / 房源匹配理由
                    ▼
              地段推荐 + 每片区 3 套房源 + 评估明细
```

## 相对现有实现改了什么

现在的链路是 **LLM 先拍脑袋出 4 个片区 → 用户点进去才算真实分数**，推荐本身没用到任何数据（`fallbackAreas.js` 和 `staticData.ts` 里的四个片区完全一样，演示时基本走静态数据）。

新链路调转了顺序：**先算分，后推荐**。排序由通勤分和生活圈加权分决定，大模型只负责把数字翻译成人话，还要过一道防编造校验。这样"凭什么推荐这个片区"能拿分数明细回答。

## 文件

| 文件 | 用途 |
|---|---|
| [`preference_contract.json`](preference_contract.json) | 两个 Agent 之间的唯一契约（JSON Schema） |
| [`agent_a/system_prompt.md`](agent_a/system_prompt.md) | Agent A 系统提示词，直接粘贴到百炼 |
| [`agent_a/submit_preference_openapi.yaml`](agent_a/submit_preference_openapi.yaml) | Agent A 插件定义，百炼导入 |
| [`agent_b/workflow_design.md`](agent_b/workflow_design.md) | 工作流节点编排 + 两个大模型节点提示词 |
| [`agent_b/node02_parse_and_weight.py`](agent_b/node02_parse_and_weight.py) | 代码节点：偏好解析与权重推导 |
| [`agent_b/node07_score_and_rank.py`](agent_b/node07_score_and_rank.py) | 代码节点：片区评分与排序（核心） |
| [`agent_b/node11_assemble.py`](agent_b/node11_assemble.py) | 代码节点：结果组装与防编造校验 |
| [`backend_contract.md`](backend_contract.md) | 后端需新增的 5 个接口 + 2 张表 |

三个代码节点都能独立运行自测：

```bash
python agent/agent_b/node07_score_and_rank.py
```

## 两个设计决定，值得单独说

**其一，权重由规则算，不由模型给。** Agent A 只从受控词表里打 `lifestyle_tags`（`cook_often`、`fitness`、`has_child`…），八类设施的权重在代码节点里按固定映射表推导。这样同样的标签永远得到同样的权重，而且能把推导过程 `weight_rationale` 直接展示给用户看——"因为你说常做饭，买菜购物的权重提高了"。让模型直接输出小数权重既不稳定也无法解释。

优先级也是同理：让用户对通勤/生活/租金/品质四项排序，代码节点转成 `[0.40, 0.28, 0.20, 0.12]`。模型排序比模型给小数可靠得多。

**其二，大模型不许新增事实。** 节点 11 会拿代码节点 7 的真实结果去校验模型输出：片区名对不上的丢弃，房源 ID 不在候选池里的丢弃，房源字段一律以后端数据为准，模型唯一能贡献的是 `match_reason` 那句话。自测里故意喂了一个虚构片区和一个伪造房源 ID，都被拦下来了。

## 待办

按依赖顺序：

1. **建 `area_library` 表**（30~50 个南京片区）。这是唯一需要人工整理的数据，也是召回节点的基础。`api_server.py` 的 `TRUSTED_NANJING_LOCATIONS` 有约 80 个南京地名坐标可以当种子，挑出适合居住的，补上行政区、参考租金区间和标签。
2. **实现后端 5 个接口**（见 `backend_contract.md`）。接口 3、4 主要是把已有的 `handle_commute` / `handle_facilities` 拆成"只出原始数据"的版本，工作量不大。别忘了 POI 缓存——这是把演示耗时从几分钟压到几秒的关键。
3. **内网穿透**，让百炼能调到本地后端。
4. **百炼上建两个应用**，粘贴提示词和代码节点，用 `preference_contract.json` 里的示例数据先把 Agent B 单独跑通，再接 Agent A。
5. **前端改造**：新增对话页；分析页改成读一次性返回的评估结果，不再二次请求。

## 房源数据源的现状

这是整套方案里唯一没有干净解法的地方，如实记录：

- [贝壳开放平台](https://open.ke.com/serviceSupport/getToken/) 需要营业执照和行业资质，个人和课程项目申请不下来
- 阿里云云市场上的「安居客 item_get」「房天下 item_get」「58同城 item_get」这类接口，从命名看是第三方数据代采服务商的封装，本质是代理爬取后转卖，不是平台官方开放能力。个人按次付费能买到，但数据合规性经不起追问

所以接口 5 设计成了**可插拔适配器**：先用自建样本库跑通全流程，真买到了第三方 API 就换个 adapter 实现，百炼侧配置一行不用改。无论用哪个源，`source` 和 `source_note` 都必须如实透传到前端展示——样本数据就明确标注是样本数据。
