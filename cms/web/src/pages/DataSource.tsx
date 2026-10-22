import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Col, InputNumber, Row, Select, Space, Table, Tag } from 'antd'
import { api, fmtAt, type Import, type Job, type RawFile } from '../api'
import { JobTag, n, PageHeader } from '../ui'

/** Dữ liệu nguồn: nạp file raw có sẵn, thu thập mới từ Cổng DVC (chạy nền, tự làm mới), lịch sử nạp. */
export default function DataSource({ code }: { code: string }) {
  const { message } = AntApp.useApp()
  const [d, setD] = useState<{ raws: RawFile[]; imports: Import[]; jobs: Job[]; running: Job | null } | null>(null)
  const [err, setErr] = useState('')
  const [file, setFile] = useState<string>()
  const [limit, setLimit] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const load = useCallback(() => api.data(code).then((r) => { setErr(''); setD(r); setFile((f) => f ?? r.raws[r.raws.length - 1]?.name) })
    .catch((e) => setErr((e as Error).message)), [code])
  useEffect(() => { load() }, [load])
  useEffect(() => { if (!d?.running) return; const t = setInterval(load, 5000); return () => clearInterval(t) }, [d?.running, load])
  const act = async (key: string, fn: () => Promise<unknown>, ok: (r: never) => string) => {
    setBusy(key)
    try { const r = await fn(); message.success(ok(r as never)); load() } catch (e) { message.error((e as Error).message) } finally { setBusy(null) }
  }
  return (
    <div data-testid="data-source">
      <PageHeader title="Dữ liệu nguồn" description="Nạp dữ liệu thủ tục từ Cổng Dịch vụ công. Thủ tục mới / thay đổi chuyển sang Cần duyệt; câu hỏi và tags đã biên tập được giữ." />
      {err && <Alert type="error" showIcon message="Không tải được dữ liệu nguồn" description={err} style={{ marginBottom: 16 }} />}
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="Thu thập mới từ Cổng DVC" style={{ height: '100%' }}>
            <p className="small muted" style={{ marginTop: 0 }}>Kiểm tra sức khoẻ cổng trước, lỗi thì dừng. Đầy đủ mất vài phút / tỉnh (Khánh Hòa ≈ 2 phút).
              Chạy thử N &gt; 0 chỉ tải N thủ tục để kiểm tra, không nạp.</p>
            <Space wrap>
              <Space.Compact>
                <span className="ant-input-group-addon" style={{ display: 'inline-flex', alignItems: 'center', padding: '0 11px', border: '1px solid var(--c-border)', borderInlineEnd: 0, borderRadius: '6px 0 0 6px', background: '#fafafa', fontSize: 13 }}>Chạy thử</span>
                <InputNumber aria-label="Số thủ tục chạy thử" min={0} max={500} value={limit} onChange={(v) => setLimit(v ?? 0)} style={{ width: 90 }} />
              </Space.Compact>
              <Button type="primary" loading={busy === 'collect'} disabled={!!d?.running}
                onClick={() => act('collect', () => api.collect(code, limit), (j: Job) => `Đã bắt đầu ${j.id}`)}>{limit ? `Thu thập thử ${limit} thủ tục` : 'Thu thập đầy đủ'}</Button>
            </Space>
            {d?.running && <Alert style={{ marginTop: 12 }} type="info" showIcon message={`Đang chạy ${d.running.id} – tự làm mới mỗi 5 giây`} />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="Nạp file đã tải" style={{ height: '100%' }}>
            <p className="small muted" style={{ marginTop: 0 }}>File do bộ công cụ (thư mục data/) hoặc CMS tải về, hoặc do browser_collector.js tạo.</p>
            <Space.Compact style={{ width: '100%' }}>
              <Select aria-label="File raw" style={{ flex: 1, minWidth: 0 }} value={file} onChange={setFile} placeholder={`Chưa có file cho ${code}`}
                options={(d?.raws ?? []).map((r) => ({ value: r.name, label: `${r.name} · ${(r.size / 1048576).toFixed(1)} MB · ${fmtAt(r.mtime)}${r.source === 'cms' ? ' · CMS' : ''}` }))} />
              <Button type="primary" disabled={!file} loading={busy === 'import'} onClick={() => act('import', () => api.importRaw(code, file!),
                (r: Import) => `Đã nạp ${n(r.procedures)} thủ tục – Mới ${r.added}, Thay đổi ${r.changed}, Đã gỡ ${r.removed}`)}>Nạp</Button>
            </Space.Compact>
          </Card>
        </Col>
      </Row>
      {!!d?.jobs.length && <Card title="Lần thu thập (phiên chạy CMS này)" style={{ marginTop: 16 }} styles={{ body: { padding: 0 } }}>
        <Table<Job> rowKey="id" size="small" pagination={false} dataSource={d.jobs} scroll={{ x: 640 }} columns={[
          { title: 'Mã', dataIndex: 'id', render: (v: string) => <span className="mono">{v}</span> },
          { title: 'Thời gian', key: 't', render: (_, j) => <span className="small num">{fmtAt(j.started)} → {j.finished ? fmtAt(j.finished).slice(11) : '…'}</span> },
          { title: 'Trạng thái', dataIndex: 'status', width: 110, render: (v: string) => <JobTag value={v} /> },
          { title: 'Kết quả', key: 'r', render: (_, j) => <span className="small">{j.error ?? (j.result && 'trial' in j.result && j.result.trial ? `Chạy thử: tải ${j.result.procedures} thủ tục, ${j.result.failures} lỗi`
            : j.result && 'added' in j.result ? `Mới ${j.result.added} · Thay đổi ${j.result.changed} · Đã gỡ ${j.result.removed}` : '')}</span> },
        ]} /></Card>}
      <Card title="Lịch sử nạp" style={{ marginTop: 16 }} styles={{ body: { padding: 0 } }}>
        <Table<Import> rowKey="id" size="small" loading={!d && !err} dataSource={d?.imports} pagination={{ pageSize: 10, hideOnSinglePage: true }} scroll={{ x: 900 }}
          locale={{ emptyText: 'Chưa nạp lần nào' }} columns={[
          { title: '#', dataIndex: 'id', width: 50, render: (v: number) => <span className="num">{v}</span> },
          { title: 'Lúc', dataIndex: 'at', width: 140, render: (v: string) => <span className="num">{fmtAt(v)}</span> },
          { title: 'Người', dataIndex: 'actor', width: 120 },
          { title: 'Nguồn', dataIndex: 'source', render: (v: string, i) => <><span className="mono">{v}</span>{i.note && <div className="cell-sub">{i.note}</div>}</> },
          { title: 'Thủ tục', dataIndex: 'procedures', width: 90, align: 'right', render: (v: number) => <span className="num">{n(v)}</span> },
          { title: 'Mới', dataIndex: 'added', width: 70, align: 'right', render: (v: number) => <span className="num">{v}</span> },
          { title: 'Thay đổi', dataIndex: 'changed', width: 90, align: 'right', render: (v: number) => <span className="num">{v}</span> },
          { title: 'Đã gỡ', dataIndex: 'removed', width: 80, align: 'right', render: (v: number) => v ? <Tag color="red" bordered={false}>{v}</Tag> : <span className="num">0</span> },
        ]} />
      </Card>
    </div>
  )
}
