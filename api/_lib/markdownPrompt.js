export function buildRecommendPrompt(preference) {
  return `# 宁安居租住片区推荐任务

请基于来宁青年租房需求，推荐 4 个南京真实租住片区或生活圈。

## 用户偏好
- 工作地址：${preference.workAddress}
- 月租预算：${preference.budgetMin}-${preference.budgetMax} 元/月
- 可接受通勤距离：${preference.commuteRange}
- 最看重因素：${preference.priority}

## 输出约束
1. 不推荐具体房源、具体小区房号或中介信息。
2. 不编造精确租金，只描述片区适配性。
3. 必须返回严格 JSON，不要输出 Markdown 或解释文字。
4. JSON 格式为：{"areas":[{"name":"片区名称","tagline":"一句话推荐标签","reason":"推荐理由","risk":"风险提示","tags":["标签1","标签2","标签3"]}]}
5. areas 必须正好 4 条。`;
}
