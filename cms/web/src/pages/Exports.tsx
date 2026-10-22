import { useCallback, useEffect, useState } from 'react'
import { App as AntApp, Button, Card, Checkbox, List, Radio, Space, Table, Typography } from 'antd'
import { DownloadOutlined, FileExcelOutlined } from '@ant-design/icons'
import { api, fmtAt, fmtNum, type ExportRec, type Proc, type Stats } from '../api'

const KINDS = [
  { value: 'FULL', label: 'Bộ đầy đủ', desc: 'Toàn bộ thủ tục đang có trên cổng – thay toàn bộ tập train.' },
  { value: 'APPROVED', label: 'Chỉ thủ tục đã duyệt', desc: 'Chỉ nội dung đã qua người duyệt.' },
  { value: 'CHANGES', label: 'Bản cập nhật', desc: 'Mới + Thay đổi của lần nhập gần nhất, kèm sheet TongHop (Mới / Thay đổi / Đã gỡ) – nạp bổ sung vào tập train.' },
]

/** Xuất Excel 5 cột (Sheet0) đúng định dạng bộ công cụ – nạp callbot. */
export default function Exports({ code }: { code: string }) {
  const { message } = AntApp.useApp()
  const [d, setD] = useState<{ exports: ExportRec[]; stats: Stats; removed: Proc[] } | null>(null)
  const [kind, setKind] = useState('FULL')
  const [onlyApproved, setOnlyApproved] = useState(false)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => api.exports(code).then(setD).catch((e) => message.error((e as Error).message)), [code, message])
  useEffect(() => { load() }, [load])
  const run = async () => {
    setBusy(true)
    try {
      const r = await api.doExport(code, kind, onlyApproved)
      message.success(`Đã xuất ${fmtNum(r.procedures)} thủ tục, ${fmtNum(r.rows)} dòng`)
      window.location.href = `/api/exports/${encodeURIComponent(r.file)}`
      load()
    } catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <div data-testid="exports">
      <Card title={<Space><FileExcelOutlined />Xuất Excel nạp callbot</Space>}>
        <Radio.Group value={kind} onChange={(e) => setKind(e.target.value)} style={{ width: '100%' }}>
          <Space direction="vertical">{KINDS.map((k) => <Radio key={k.value} value={k.value}><b>{k.label}</b> <Typography.Text type="secondary">– {k.desc}</Typography.Text></Radio>)}</Space>
        </Radio.Group>
        <div style={{ margin: '12px 0' }}><Checkbox checked={onlyApproved || kind === 'APPROVED'} disabled={kind === 'APPROVED'} onChange={(e) => setOnlyApproved(e.target.checked)}>Chỉ thủ tục đã duyệt</Checkbox></div>
        <Space><Button type="primary" icon={<DownloadOutlined />} loading={busy} onClick={run}>Xuất và tải về</Button>
          {d && <Typography.Text type="secondary">Hiện có {fmtNum(d.stats.procedures)} thủ tục: {fmtNum(d.stats.approved)} đã duyệt, {fmtNum(d.stats.need_review)} cần duyệt.</Typography.Text>}</Space>
      </Card>
      <Card title="Đã xuất" style={{ marginTop: 16 }}>
        <Table<ExportRec> rowKey="id" size="small" loading={!d} dataSource={d?.exports} pagination={{ pageSize: 10 }} columns={[
          { title: 'Lúc', dataIndex: 'at', render: fmtAt, width: 140 }, { title: 'Loại', dataIndex: 'kind', render: (v: string) => KINDS.find((k) => k.value === v)?.label ?? v },
          { title: 'Người', dataIndex: 'actor' }, { title: 'Thủ tục', dataIndex: 'procedures', render: fmtNum }, { title: 'Dòng', dataIndex: 'rows', render: fmtNum },
          { title: 'File', dataIndex: 'file', render: (v: string) => <a href={`/api/exports/${encodeURIComponent(v)}`}><DownloadOutlined /> {v}</a> },
        ]} />
      </Card>
      {!!d?.removed.length && <Card title={`Thủ tục đã gỡ khỏi cổng (${d.removed.length}) – cần xoá khỏi tập train`} style={{ marginTop: 16 }}>
        <List size="small" dataSource={d.removed} renderItem={(p) => <List.Item><Typography.Text code>{p.code}</Typography.Text> {p.name}</List.Item>} /></Card>}
    </div>
  )
}
