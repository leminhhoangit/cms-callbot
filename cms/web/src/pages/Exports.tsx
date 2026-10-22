import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Checkbox, Col, Radio, Row, Space, Table } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { api, fmtAt, type ExportRec, type Proc, type Stats } from '../api'
import { n, PageHeader } from '../ui'

const KINDS = [
  { value: 'FULL', label: 'Bộ đầy đủ', desc: 'Toàn bộ thủ tục đang có trên cổng – thay toàn bộ tập train.' },
  { value: 'APPROVED', label: 'Chỉ thủ tục đã duyệt', desc: 'Chỉ nội dung đã qua người duyệt.' },
  { value: 'CHANGES', label: 'Bản cập nhật', desc: 'Mới + Thay đổi của lần nạp gần nhất, kèm sheet TongHop (Mới / Thay đổi / Đã gỡ).' },
]

/** Xuất Excel 5 cột (Sheet0) đúng định dạng bộ công cụ – nạp callbot bằng tay khi chưa có API iCC. */
export default function Exports({ code }: { code: string }) {
  const { message } = AntApp.useApp()
  const [d, setD] = useState<{ exports: ExportRec[]; stats: Stats; removed: Proc[] } | null>(null)
  const [err, setErr] = useState('')
  const [kind, setKind] = useState('FULL')
  const [onlyApproved, setOnlyApproved] = useState(false)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => api.exports(code).then((r) => { setErr(''); setD(r) }).catch((e) => setErr((e as Error).message)), [code])
  useEffect(() => { load() }, [load])
  const run = async () => {
    setBusy(true)
    try {
      const r = await api.doExport(code, kind, onlyApproved)
      message.success(`Đã xuất ${n(r.procedures)} thủ tục, ${n(r.rows)} dòng`)
      window.location.href = `/api/exports/${encodeURIComponent(r.file)}`
      load()
    } catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <div data-testid="exports">
      <PageHeader title="Xuất Excel callbot" description="File 5 cột (Tiêu đề, Nội dung, Câu hỏi, Tags, IdentificationInfo) đúng định dạng tập train hiện tại." />
      {err && <Alert type="error" showIcon message="Không tải được lịch sử xuất" description={err} style={{ marginBottom: 16 }} />}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="Tạo file">
            <Radio.Group value={kind} onChange={(e) => setKind(e.target.value)} style={{ width: '100%' }}>
              <Space direction="vertical" size={12}>{KINDS.map((k) => <Radio key={k.value} value={k.value}>
                <b>{k.label}</b><div className="small muted">{k.desc}</div></Radio>)}</Space>
            </Radio.Group>
            <div style={{ margin: '16px 0' }}>
              <Checkbox checked={onlyApproved || kind === 'APPROVED'} disabled={kind === 'APPROVED'} onChange={(e) => setOnlyApproved(e.target.checked)}>Chỉ thủ tục đã duyệt</Checkbox>
            </div>
            <Button type="primary" icon={<DownloadOutlined />} loading={busy} onClick={run}>Xuất và tải về</Button>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="Hiện có">
            {d && <dl className="kv">
              <dt>Thủ tục</dt><dd className="num">{n(d.stats.procedures)}</dd>
              <dt>Đã duyệt</dt><dd className="num">{n(d.stats.approved)}</dd>
              <dt>Cần duyệt</dt><dd className="num">{n(d.stats.need_review)}</dd>
              <dt>Đã gỡ khỏi cổng</dt><dd className="num">{n(d.removed.length)}</dd>
            </dl>}
          </Card>
        </Col>
      </Row>
      <Card title="Đã xuất" style={{ marginTop: 16 }} styles={{ body: { padding: 0 } }}>
        <Table<ExportRec> rowKey="id" size="small" loading={!d && !err} dataSource={d?.exports} pagination={{ pageSize: 10, hideOnSinglePage: true }} scroll={{ x: 760 }}
          locale={{ emptyText: 'Chưa xuất lần nào' }} columns={[
          { title: 'Lúc', dataIndex: 'at', width: 140, render: (v: string) => <span className="num">{fmtAt(v)}</span> },
          { title: 'Loại', dataIndex: 'kind', width: 170, render: (v: string) => KINDS.find((k) => k.value === v)?.label ?? v },
          { title: 'Người', dataIndex: 'actor', width: 130 },
          { title: 'Thủ tục', dataIndex: 'procedures', width: 90, align: 'right', render: (v: number) => <span className="num">{n(v)}</span> },
          { title: 'Dòng', dataIndex: 'rows', width: 90, align: 'right', render: (v: number) => <span className="num">{n(v)}</span> },
          { title: 'File', dataIndex: 'file', render: (v: string) => <a href={`/api/exports/${encodeURIComponent(v)}`}><DownloadOutlined /> <span className="mono">{v}</span></a> },
        ]} />
      </Card>
      {!!d?.removed.length && <Card title={`Thủ tục đã gỡ khỏi cổng (${d.removed.length}) – cần xoá khỏi tập train`} style={{ marginTop: 16 }} styles={{ body: { padding: 0 } }}>
        <Table<Proc> rowKey="fid" size="small" pagination={{ pageSize: 20, hideOnSinglePage: true }} dataSource={d.removed} columns={[
          { title: 'Mã', dataIndex: 'code', width: 120, render: (v: string) => <span className="mono">{v}</span> }, { title: 'Thủ tục', dataIndex: 'name' }]} /></Card>}
    </div>
  )
}
