import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Col, InputNumber, Row, Select, Space, Table, Tag, Typography } from 'antd'
import { CloudDownloadOutlined, ImportOutlined } from '@ant-design/icons'
import { api, fmtAt, fmtNum, type Import, type Job, type RawFile } from '../api'

const JOB: Record<string, { vi: string; color: string }> = { RUNNING: { vi: 'Đang chạy', color: 'processing' }, SUCCEEDED: { vi: 'Xong', color: 'green' }, FAILED: { vi: 'Lỗi', color: 'red' } }

/** Dữ liệu nguồn: nhập file raw có sẵn, thu thập mới từ Cổng DVCQG (chạy nền, tự làm mới), lịch sử nhập. */
export default function DataSource({ code }: { code: string }) {
  const { message } = AntApp.useApp()
  const [d, setD] = useState<{ raws: RawFile[]; imports: Import[]; jobs: Job[]; running: Job | null } | null>(null)
  const [file, setFile] = useState<string>()
  const [limit, setLimit] = useState(0)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => api.data(code).then((r) => { setD(r); setFile((f) => f ?? r.raws[r.raws.length - 1]?.name) }).catch((e) => message.error((e as Error).message)), [code, message])
  useEffect(() => { load() }, [load])
  useEffect(() => { if (!d?.running) return; const t = setInterval(load, 5000); return () => clearInterval(t) }, [d?.running, load])
  const act = async (fn: () => Promise<unknown>, ok: (r: never) => string) => {
    setBusy(true)
    try { const r = await fn(); message.success(ok(r as never)); load() } catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <div data-testid="data-source">
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title={<Space><ImportOutlined />Nhập file raw có sẵn</Space>} style={{ height: '100%' }}>
            <Typography.Paragraph type="secondary">File do scripts/collect_tthc.py hoặc browser_collector.js tạo, trong thư mục data/. So với bộ đang có:
              thủ tục Mới / Thay đổi → Cần duyệt; câu hỏi / tags đã biên tập được giữ.</Typography.Paragraph>
            <Space.Compact style={{ width: '100%' }}>
              <Select aria-label="File raw" style={{ flex: 1 }} value={file} onChange={setFile} placeholder={`Chưa có file raw cho ${code}`}
                options={(d?.raws ?? []).map((r) => ({ value: r.name, label: `${r.name} · ${(r.size / 1048576).toFixed(1)} MB · ${fmtAt(r.mtime)}` }))} />
              <Button type="primary" disabled={!file} loading={busy} onClick={() => act(() => api.importRaw(code, file!),
                (r: Import) => `Đã nhập ${fmtNum(r.procedures)} thủ tục, ${fmtNum(r.rows)} dòng – Mới ${r.added}, Thay đổi ${r.changed}, Đã gỡ ${r.removed}`)}>Nhập</Button>
            </Space.Compact>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={<Space><CloudDownloadOutlined />Thu thập mới từ Cổng DVCQG</Space>} style={{ height: '100%' }}>
            <Typography.Paragraph type="secondary">Kiểm tra sức khoẻ cổng trước, lỗi thì dừng. Đầy đủ mất vài phút / tỉnh (Khánh Hòa ≈ 2 phút). "Chạy thử N" chỉ tải N thủ tục để kiểm tra, không nhập.</Typography.Paragraph>
            <Space wrap>
              <span>Chạy thử N thủ tục (0 = đầy đủ)</span>
              <InputNumber aria-label="Số thủ tục chạy thử" min={0} max={500} value={limit} onChange={(v) => setLimit(v ?? 0)} />
              <Button type="primary" loading={busy} disabled={!!d?.running} onClick={() => act(() => api.collect(code, limit), (j: Job) => `Đã bắt đầu ${j.id} – trang tự làm mới`)}>Thu thập</Button>
            </Space>
            {d?.running && <Alert style={{ marginTop: 12 }} type="info" showIcon message={`Đang chạy ${d.running.id} – tự làm mới mỗi 5 giây`} />}
          </Card>
        </Col>
      </Row>
      {!!d?.jobs.length && <Card title="Lần thu thập (phiên chạy CMS này)" style={{ marginTop: 16 }}>
        <Table<Job> rowKey="id" size="small" pagination={false} dataSource={d.jobs} columns={[
          { title: 'Mã', dataIndex: 'id' }, { title: 'Bắt đầu', dataIndex: 'started', render: fmtAt }, { title: 'Kết thúc', dataIndex: 'finished', render: fmtAt },
          { title: 'Trạng thái', dataIndex: 'status', render: (v: string) => <Tag color={JOB[v].color}>{JOB[v].vi}</Tag> },
          { title: 'Kết quả', key: 'r', render: (_, j) => j.error ?? (j.result && 'trial' in j.result && j.result.trial ? `Chạy thử: tải ${j.result.procedures} thủ tục, ${j.result.failures} lỗi`
            : j.result && 'added' in j.result ? `Mới ${j.result.added}, Thay đổi ${j.result.changed}, Đã gỡ ${j.result.removed}` : '') },
        ]} /></Card>}
      <Card title="Lịch sử nhập" style={{ marginTop: 16 }}>
        <Table<Import> rowKey="id" size="small" loading={!d} dataSource={d?.imports} pagination={{ pageSize: 10 }} columns={[
          { title: '#', dataIndex: 'id', width: 50 }, { title: 'Lúc', dataIndex: 'at', render: fmtAt, width: 140 }, { title: 'Người', dataIndex: 'actor', width: 120 },
          { title: 'Nguồn', dataIndex: 'source' }, { title: 'Lấy từ cổng lúc', dataIndex: 'fetched_at', render: fmtAt, width: 140 },
          { title: 'Thủ tục', dataIndex: 'procedures', render: fmtNum }, { title: 'Dòng', dataIndex: 'rows', render: fmtNum },
          { title: 'Mới', dataIndex: 'added' }, { title: 'Thay đổi', dataIndex: 'changed' }, { title: 'Đã gỡ', dataIndex: 'removed' },
          { title: 'Ghi chú', dataIndex: 'note', ellipsis: true },
        ]} />
      </Card>
    </div>
  )
}
