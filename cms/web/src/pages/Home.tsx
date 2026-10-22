import { useEffect, useState } from 'react'
import { Alert, Button, Card, Empty, Progress, Skeleton, Space, Table, Tooltip } from 'antd'
import type { TableColumnsType } from 'antd'
import { api, fmtAt, type Province, type Stats } from '../api'
import { go } from '../App'
import { n, PageHeader, StatStrip } from '../ui'

type Row = Province & { stats: Stats }

/** Tổng quan – các tỉnh đã có dữ liệu trong một bảng để so sánh nhanh; số liệu chỉ từ dữ liệu đã nạp. */
export default function Home() {
  const [d, setD] = useState<Province[] | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.provinces().then((x) => setD(x.provinces)).catch((e) => setErr((e as Error).message)) }, [])
  if (err) return <Alert type="error" showIcon message="Không tải được dữ liệu tổng quan" description={err} />
  if (!d) return <Skeleton active paragraph={{ rows: 6 }} />
  const rows = d.filter((p): p is Row => !!p.stats)
  const sum = (k: 'procedures' | 'rows' | 'need_review' | 'approved' | 'removed') => rows.reduce((a, p) => a + p.stats[k], 0)
  const total = sum('procedures')
  const cols: TableColumnsType<Row> = [
    { title: 'Tỉnh / thành', key: 'p', width: 230, render: (_, p) => <>
      <a className="cell-title" onClick={() => go(`/p/${p.code}/list`)}>{p.display}</a> <span className="mono muted">{p.code}</span>
      {!!p.auto && <div className="cell-sub"><Tooltip title="Chưa có địa chỉ Trung tâm Phục vụ HCC thật – nội dung đang dùng câu chung">
        <a onClick={() => go(`/p/${p.code}/settings`)}>Thiếu địa chỉ tiếp nhận</a></Tooltip></div>}</> },
    { title: 'Thủ tục', key: 'n', align: 'right', width: 100, render: (_, p) => <span className="num">{n(p.stats.procedures)}</span> },
    { title: 'Dòng callbot', key: 'r', align: 'right', width: 120, render: (_, p) => <span className="num">{n(p.stats.rows)}</span> },
    { title: 'Có câu hỏi', key: 'q', align: 'right', width: 110, render: (_, p) => <span className="num">{p.stats.questions_pct ?? 0}%</span> },
    { title: 'Tiến độ duyệt', key: 'a', width: 220, render: (_, p) => <>
      <Progress size="small" showInfo={false} percent={p.stats.procedures ? (100 * p.stats.approved) / p.stats.procedures : 0} />
      <div className="cell-sub num">{n(p.stats.approved)} / {n(p.stats.procedures)} đã duyệt</div></> },
    { title: 'Cần duyệt', key: 'w', align: 'right', width: 100, render: (_, p) => <span className="num" data-testid={`need-review-${p.code}`}>{n(p.stats.need_review)}</span> },
    { title: 'Nạp gần nhất', key: 'l', width: 190, render: (_, p) => p.stats.last_import ? <Tooltip title={p.stats.last_import.source}>
      <span className="num">{fmtAt(p.stats.last_import.at)}</span>
      <div className="cell-sub">Mới {p.stats.last_import.added} · Đổi {p.stats.last_import.changed} · Gỡ {p.stats.last_import.removed}</div></Tooltip> : '—' },
    { title: <span className="sr-only">Thao tác</span>, key: 'x', width: 140, render: (_, p) => <Space size={4}>
      <Button size="small" onClick={() => go(`/p/${p.code}/training`)}>Train</Button>
      <Button size="small" onClick={() => go(`/p/${p.code}/export`)}>Xuất</Button></Space> },
  ]
  return (
    <div data-testid="home">
      <PageHeader title="Tổng quan" description="Dữ liệu huấn luyện callbot theo tỉnh / thành, tính từ các lần nạp dữ liệu Cổng Dịch vụ công." />
      <StatStrip label="Số liệu toàn hệ thống" items={[
        { label: 'Tỉnh / thành có dữ liệu', value: rows.length, suffix: `/ ${d.length}` },
        { label: 'Thủ tục hành chính', value: n(total) },
        { label: 'Dòng dữ liệu callbot', value: n(sum('rows')) },
        { label: 'Đã duyệt', value: n(sum('approved')), suffix: total ? `${((100 * sum('approved')) / total).toLocaleString('vi-VN', { maximumFractionDigits: 1 })}%` : undefined, tone: 'success' },
        { label: 'Cần duyệt', value: n(sum('need_review')), tone: sum('need_review') ? 'warning' : undefined },
      ]} />
      {sum('removed') > 0 && <Alert style={{ marginBottom: 16 }} type="error" showIcon
        message={`Có ${n(sum('removed'))} thủ tục đã gỡ khỏi cổng – cần xoá khỏi bot (trang Train bot của từng tỉnh)`} />}
      <Card title="Tỉnh / thành đang quản lý" extra={<span className="small muted">{d.length - rows.length} tỉnh chưa có dữ liệu – chọn ở ô tỉnh trên cùng</span>}
        styles={{ body: { padding: rows.length ? 0 : undefined } }}>
        {rows.length ? <Table<Row> rowKey="code" columns={cols} dataSource={rows} pagination={false} scroll={{ x: 1000 }} />
          : <Empty description="Chưa nạp dữ liệu tỉnh nào"><Button type="primary" onClick={() => go('/p/H32/data')}>Nạp dữ liệu</Button></Empty>}
      </Card>
    </div>
  )
}
