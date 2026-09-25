import type { EvaluationHistoryRecord } from "../services/evaluationHistoryService";

type EvaluationHistoryTableProps = {
  records: EvaluationHistoryRecord[];
  loading: boolean;
  onOpen: (record: EvaluationHistoryRecord) => void;
  onDelete: (id: string) => void;
};

export function EvaluationHistoryTable({ records, loading, onOpen, onDelete }: EvaluationHistoryTableProps) {
  return (
    <div className="record-table">
      <div className="record-head">
        <span>片区</span>
        <span>总分</span>
        <span>通勤分</span>
        <span>设施分</span>
        <span>保存时间</span>
        <span>操作</span>
      </div>
      {records.length === 0 && (
        <div className="record-row record-empty">
          <span>暂无评估记录</span><span /><span /><span /><span /><span />
        </div>
      )}
      {records.map((record) => (
        <div className="record-row" key={record.id}>
          <span>{record.regionName}</span>
          <b className="orange-text">{record.totalScore}</b>
          <b className="blue-text">{record.commuteScore}</b>
          <b className="green-text">{record.facilityScore}</b>
          <span>{record.time}</span>
          <span>
            <button onClick={() => onOpen(record)} type="button">查看详情</button>
            <button disabled={loading} onClick={() => onDelete(record.id)} type="button">删除</button>
          </span>
        </div>
      ))}
    </div>
  );
}
