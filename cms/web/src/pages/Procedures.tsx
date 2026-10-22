import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Grid, Input, Select, Table, Tooltip } from 'antd'
import type { TableColumnsType } from 'antd'
import { CheckOutlined } from '@ant-design/icons'
import { api, type Proc, type Province, type Stats } from '../api'
import { CHANGE, ChangeTag, n, PageHeader, REVIEW, ReviewTag, StatStrip } from '../ui'
import ProcedureDrawer from './ProcedureDrawer'

export { CHANGE, REVIEW }

/** Danh sách thủ tục: tìm / lọc, mở chi tiết (biên tập câu hỏi, duyệt), duyệt hàng loạt. */
export default function Procedures({ code }: { code: string }) {
  const { message, modal } = AntApp.useApp()
  const wide = Grid.useBreakpoint().md !== false
  const [f, setF] = useState({ q: '', review: '', change: '', category: '', status: 'ACTIVE', page: 1, size: 50 })
  const [q, setQ] = useState('')
  const [res, setRes] = useState<{ total: number; items: Proc[] } | null>(null)
  const [stats, setStats] = useState<Stats | null>(null)
  const [prov, setProv] = useState<Province | null>(null)
  const [cats, setCats] = useState<string[]>([])
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)
  const [sel, setSel] = useState<string[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const load = useCallback(() => {
    setLoading(true)
    api.procedures(code, f).then((r) => { setErr(''); setRes(r) }).catch((e) => setErr((e as Error).message)).finally(() => setLoading(false))
    api.province(code).then((r) => { setStats(r.stats); setCats(r.categories); setProv(r.province) }).catch(() => {})
  }, [code, f])
  useEffect(() => { load() }, [load])
  const set = (patch: Partial<typeof f>) => { setSel([]); setF({ ...f, page: 1, ...patch }) }
  const filtered = !!(f.q || f.review || f.change || f.category || f.status !== 'ACTIVE')
  const bulk = () => modal.confirm({
    title: `Duyệt ${sel.length} thủ tục?`, content: 'Chỉ duyệt khi đã đọc nội dung. Tên người duyệt được ghi vào nhật ký.', okText: 'Duyệt', cancelText: 'Huỷ',
    onOk: async () => { try { const r = await api.reviewBulk(code, sel); message.success(`Đã duyệt ${r.approved} thủ tục`); setSel([]); load() } catch (e) { message.error((e as Error).message) } },
  })
  const cols: TableColumnsType<Proc> = [
    { title: 'Thủ tục', dataIndex: 'name', render: (v: string, p) => <>
      <a className="cell-title" onClick={() => setOpen(p.fid)}>{v}</a>
      <div className="cell-sub"><span className="mono">{p.code}</span> · {p.category || 'Chưa rõ lĩnh vực'}</div>
      {!wide && <div style={{ marginTop: 4 }}><ChangeTag value={p.change} /></div>}</> },
    { title: 'Cấp', dataIndex: 'levels', width: 120, responsive: ['lg'], render: (v: string) => <span className="small">{v || '—'}</span> },
    { title: <Tooltip title="Số dòng dữ liệu callbot / số dòng đã có câu hỏi">Dòng · câu hỏi</Tooltip>, key: 'rows', width: 120, align: 'right', responsive: ['md'],
      render: (_, p) => <span className="num">{p.n_rows} · {p.n_q}</span> },
    { title: 'Thay đổi', dataIndex: 'change', width: 130, responsive: ['md'], render: (v: string) => <ChangeTag value={v} /> },
    { title: 'Duyệt', dataIndex: 'review', width: wide ? 140 : 104, render: (v: string, p) => <>
      <ReviewTag value={v} />{p.reviewed_by && <div className="cell-sub">{p.reviewed_by}</div>}</> },
  ]
  return (
    <div data-testid="procedures">
      <PageHeader title="Thủ tục hành chính" description={prov ? `${prov.display} – biên tập câu hỏi / tags và duyệt nội dung trước khi đưa lên bot.` : undefined} />
      {stats && <StatStrip label="Số liệu thủ tục" items={[
        { label: 'Thủ tục', value: n(stats.procedures) },
        { label: 'Dòng callbot', value: n(stats.rows) },
        { label: 'Cần duyệt', value: n(stats.need_review), tone: stats.need_review ? 'warning' : undefined },
        { label: 'Đã duyệt', value: n(stats.approved), tone: 'success' },
        { label: 'Dòng có câu hỏi', value: `${stats.questions_pct ?? 0}%` },
      ]} />}
      <Card styles={{ body: { paddingBottom: 8 } }}>
        <div className="toolbar" role="search">
          <Input.Search aria-label="Tìm thủ tục" allowClear placeholder="Tìm theo tên hoặc mã thủ tục" style={{ width: 300 }} value={q}
            onChange={(e) => setQ(e.target.value)} onSearch={(v) => set({ q: v.trim() })} />
          <Select aria-label="Trạng thái duyệt" style={{ width: 170 }} value={f.review} onChange={(v) => set({ review: v })}
            options={[{ value: '', label: 'Mọi trạng thái duyệt' }, ...Object.entries(REVIEW).map(([k, v]) => ({ value: k, label: v.vi }))]} />
          <Select aria-label="Thay đổi" style={{ width: 160 }} value={f.change} onChange={(v) => set({ change: v })}
            options={[{ value: '', label: 'Mọi thay đổi' }, ...Object.entries(CHANGE).map(([k, v]) => ({ value: k, label: v.vi }))]} />
          <Select aria-label="Trên cổng" style={{ width: 170 }} value={f.status} onChange={(v) => set({ status: v })}
            options={[{ value: 'ACTIVE', label: 'Đang có trên cổng' }, { value: 'REMOVED', label: 'Đã gỡ khỏi cổng' }, { value: '', label: 'Tất cả' }]} />
          <Select aria-label="Lĩnh vực" showSearch allowClear placeholder="Mọi lĩnh vực" style={{ width: 240 }} value={f.category || undefined}
            onChange={(v) => set({ category: v ?? '' })} options={cats.map((c) => ({ value: c, label: c }))} />
          {filtered && <Button type="link" onClick={() => { setQ(''); set({ q: '', review: '', change: '', category: '', status: 'ACTIVE' }) }}>Xoá lọc</Button>}
          <span className="grow" />
          <span className="small muted num" aria-live="polite">{res ? `${n(res.total)} thủ tục` : ''}</span>
        </div>
        {sel.length > 0 && <div className="selection-bar" role="region" aria-label="Thao tác hàng loạt">
          <span>Đã chọn <b className="num">{sel.length}</b> thủ tục</span>
          <Button type="primary" size="small" icon={<CheckOutlined />} onClick={bulk}>Duyệt {sel.length} đã chọn</Button>
          <Button size="small" type="text" onClick={() => setSel([])}>Bỏ chọn</Button>
        </div>}
        {err && <Alert type="error" showIcon message="Không tải được danh sách" description={err} style={{ marginBottom: 12 }}
          action={<Button size="small" onClick={load}>Thử lại</Button>} />}
        <Table<Proc> rowKey="fid" columns={cols} dataSource={res?.items} loading={loading && !!res || !res && !err}
          locale={{ emptyText: filtered ? 'Không có thủ tục khớp bộ lọc' : 'Chưa có thủ tục – nạp dữ liệu ở trang Dữ liệu nguồn' }}
          rowSelection={{ selectedRowKeys: sel, onChange: (k) => setSel(k as string[]), getCheckboxProps: (p) => ({ disabled: p.status !== 'ACTIVE' || p.review === 'APPROVED',
            'aria-label': `Chọn ${p.code}` }) }}
          onRow={(p) => ({ onDoubleClick: () => setOpen(p.fid) })}
          pagination={{ current: f.page, pageSize: f.size, total: res?.total, showSizeChanger: true, pageSizeOptions: [20, 50, 100], size: 'small',
            showTotal: (t, [a, b]) => <span className="small muted num">{a}–{b} / {n(t)}</span>, onChange: (page, size) => { setSel([]); setF({ ...f, page, size }) } }} />
      </Card>
      <ProcedureDrawer code={code} fid={open} onClose={() => setOpen(null)} onChanged={load} />
    </div>
  )
}
