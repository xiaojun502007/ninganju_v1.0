import { readRecommendationHistory } from "../services/recommendService";

type HistoryPageProps = {
  onBack: () => void;
};

export function HistoryPage({ onBack }: HistoryPageProps) {
  const records = readRecommendationHistory();

  return (
    <section className="history-page">
      <div className="history-hero">
        <div>
          <button className="back-button" onClick={onBack} type="button">
            返回推荐页
          </button>
          <h1>推荐历史记录</h1>
          <p>这里保存当前浏览器中提交过的租房偏好和推荐结果，后续可替换为 Supabase 历史记录接口。</p>
        </div>
      </div>

      {records.length === 0 ? (
        <section className="history-empty">
          <h2>暂无推荐记录</h2>
          <p>完成一次片区推荐后，本页会展示偏好信息和 4 个推荐片区，便于对比回看。</p>
          <button className="outline-orange" onClick={onBack} type="button">
            去生成推荐
          </button>
        </section>
      ) : (
        <div className="recommend-history-list">
          {records.map((record) => (
            <article className="recommend-history-card" key={record.id}>
              <div className="history-card-head">
                <div>
                  <h2>{record.preference.workAddress}</h2>
                  <p>{new Date(record.createdAt).toLocaleString("zh-CN")}</p>
                </div>
                <span>{record.preferenceId}</span>
              </div>

              <div className="history-preference-grid">
                <span>预算：{record.preference.budgetMin}-{record.preference.budgetMax} 元/月</span>
                <span>通勤：{record.preference.commuteRange}</span>
                <span>重点：{record.preference.priority}</span>
              </div>

              <div className="history-area-grid">
                {record.areas.map((area, index) => (
                  <section key={`${record.id}-${area.name}`}>
                    <b>{String(index + 1).padStart(2, "0")}</b>
                    <h3>{area.name}</h3>
                    <p>{area.tagline}</p>
                    <small>{area.reason}</small>
                    <div className="tag-list">
                      {area.tags.map((tag) => (
                        <span key={tag}>{tag}</span>
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
