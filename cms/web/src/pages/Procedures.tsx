import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Input, Select, Space, Statistic, Table, Tag, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import { api, fmtNum, type Proc, type Stats } from '../api'
import ProcedureDrawer from './ProcedureDrawer'

export const CHANGE: Record<string, { vi: string; color: string }> = {
  NEW: { vi: 'Mới', color: 'blue' }, CHANGED: { vi: 'Thay đổi', color: 'orange' }, SAME: { vi: 'Không đổi', color: 'default' }, REMOVED: { vi: 'Đã gỡ khỏi cổng', color: 'red' } }
export const REVIEW: Record<string, { vi: string; color: string }> = { NEED_REVIEW: { vi: 'Cần duyệt', color: 'orange' }, APPROVED: { vi: 'Đã duyệt', color: 'green' } }

/** Danh sách thủ tục: tìm / lọc, mở chi tiết (biên tập câu hỏi, duyệt), duyệt hàng loạt. */
export default function Procedures({ code }: { code: string }) {
  const { message, modal } = AntApp.useApp()
  const [f, setF] = useState({ q: '', review: '', change: '', category: '', status: 'ACTIVE', page: 1, size: 50 })
  const [q, setQ] = useState('')
  const [res, setRes] = useState<{ total: number; items: Proc[] } | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [cats, setCats] = useState<string[]>([])
  const [err, setErr] = useState('')
  const [sel, setSel] = useState<string[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const load = useCallback(() => {
    api.procedures(code, f).then((r) => { setErr(''); setRes(r) }).catch((e) => setErr((e as Error).message))
    api.province(code).then((r) => { setStats(r.stats); setCats(r.categories) }).catch(() => {})
  }, [code, f])
  useEffect(() => { load() }, [load])
  const set = (patch: Partial<typeof f>) => { setSel([]); setF({ ...f, page: 1, ...patch }) }
  const bulk = () => modal.confirm({
    title: `Duyệt ${sel.length} thủ tục?`, content: 'Chỉ duyệt khi đã đọc nội dung. Người duyệt được ghi vào nhật ký.', okText: 'Duyệt', cancelText: 'Huỷ',
    onOk: async () => { try { const r = await api.reviewBulk(code, sel); message.success(`Đã duyệt ${r.approved} thủ tục`); setSel([]); load() } catch (e) { message.error((e as Error).message) } },
  })
  const cols: TableColumnsType<Proc> = [
    { title: 'Mã', dataIndex: 'code', width: 110, render: (v: string) => <Typography.Text code>{v}</Typography.Text> },
    { title: 'Tên thủ tục', dataIndex: 'name', render: (v: string, p) => <a onClick={() => setOpen(p.fid)}>{v}</a> },
    { title: 'Lĩnh vực', dataIndex: 'category', width: 200, ellipsis: true },
    { title: 'Cấp', dataIndex: 'levels', width: 130 },
    { title: 'Dòng / có câu hỏi', key: 'rows', width: 130, render: (_, p) => `${p.n_rows} / ${p.n_q}` },
    { title: 'Thay đổi', dataIndex: 'change', width: 120, render: (v: string) => <Tag color={CHANGE[v]?.color}>{CHANGE[v]?.vi ?? v}</Tag> },
    { title: 'Duyệt', dataIndex: 'review', width: 150, render: (v: string, p) => <><Tag color={REVIEW[v].color}>{REVIEW[v].vi}</Tag>
      {p.reviewed_by && <div style={{ fontSize: 12, color: '#8c8c8c' }}>{p.reviewed_by}</div>}</> },
  ]
  return (
    <div data-testid="procedures">
      {stats && <Card size="small" style={{ marginBottom: 16 }}>
        <Space size={40} wrap>
          <Statistic title="Thủ tục" value={stats.procedures ?? 0} groupSeparator="." /><Statistic title="Dòng" value={stats.rows ?? 0} groupSeparator="." />
          <Statistic title="Cần duyệt" value={stats.need_review ?? 0} groupSeparator="." valueStyle={{ color: '#d46b08' }} />
          <Statistic title="Đã duyệt" value={stats.approved ?? 0} groupSeparator="." valueStyle={{ color: '#389e0d' }} />
          <Statistic title="Dòng có câu hỏi" value={stats.questions_pct ?? 0} suffix="%" />
        </Space></Card>}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input.Search aria-label="Tìm thủ tục" allowClear placeholder="Tìm tên / mã thủ tục" style={{ width: 320 }} value={q} onChange={(e) => setQ(e.target.value)} onSearch={(v) => set({ q: v })} />
          <Select aria-label="Trạng thái duyệt" style={{ width: 170 }} value={f.review} onChange={(v) => set({ review: v })}
            options={[{ value: '', label: 'Mọi trạng thái duyệt' }, ...Object.entries(REVIEW).map(([k, v]) => ({ value: k, label: v.vi }))]} />
          <Select aria-label="Thay đổi" style={{ width: 160 }} value={f.change} onChange={(v) => set({ change: v })}
            options={[{ value: '', label: 'Mọi thay đổi' }, ...Object.entries(CHANGE).map(([k, v]) => ({ value: k, label: v.vi }))]} />
          <Select aria-label="Trên cổng" style={{ width: 170 }} value={f.status} onChange={(v) => set({ status: v })}
            options={[{ value: 'ACTIVE', label: 'Đang có trên cổng' }, { value: 'REMOVED', label: 'Đã gỡ khỏi cổng' }, { value: '', label: 'Tất cả' }]} />
          <Select aria-label="Lĩnh vực" showSearch allowClear placeholder="Mọi lĩnh vực" style={{ width: 260 }} value={f.category || undefined}
            onChange={(v) => set({ category: v ?? '' })} options={cats.map((c) => ({ value: c, label: c }))} />
        </Space>
      </Card>
      {err && <Alert type="error" showIcon message={err} style={{ marginBottom: 12 }} />}
      <Card size="small" title={`${fmtNum(res?.total)} thủ tục`}
        extra={<Button type="primary" icon={<CheckOutlined />} disabled={!sel.length} onClick={bulk}>Duyệt {sel.length || ''} đã chọn</Button>}>
        <Table<Proc> rowKey="fid" size="middle" columns={cols} dataSource={res?.items} loading={!res}
          rowSelection={{ selectedRowKeys: sel, onChange: (k) => setSel(k as string[]), getCheckboxProps: (p) => ({ disabled: p.status !== 'ACTIVE' || p.review === 'APPROVED' }) }}
          pagination={{ current: f.page, pageSize: f.size, total: res?.total, showSizeChanger: true, pageSizeOptions: [20, 50, 100],
            onChange: (page, size) => { setSel([]); setF({ ...f, page, size }) } }} />
      </Card>
      <ProcedureDrawer code={code} fid={open} onClose={() => setOpen(null)} onChanged={load} />
    </div>
  )
}
