import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Col, Form, Input, InputNumber, Popconfirm, Radio, Row, Select, Skeleton, Space, Table, Timeline } from 'antd'
import type { TableColumnsType } from 'antd'
import { CalendarOutlined, PlayCircleOutlined, SaveOutlined, SyncOutlined } from '@ant-design/icons'
import { fmtAt, syncApi, type SyncConfig, type SyncRun } from '../api'
import { PageHeader, RunTag } from '../ui'

const WEEKDAYS = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ nhật']

/** Đồng bộ DVC -> CMS -> train bot: cấu hình Chạy tay / Theo lịch cho từng tỉnh, chạy ngay, lịch sử từng lượt (các bước). */
export default function Sync({ code }: { code: string }) {
  const { message } = AntApp.useApp()
  const [d, setD] = useState<{ config: SyncConfig; runs: SyncRun[]; scopes: Record<string, string>; freqs: Record<string, string> } | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [form] = Form.useForm()
  const load = useCallback(() => syncApi.get(code).then((r) => { setErr(''); setD(r); return r }).catch((e) => { setErr((e as Error).message); return null }), [code])
  useEffect(() => { load().then((r) => { if (r) { form.setFieldsValue(r.config); setDirty(false) } }) }, [load, form])
  const running = !!d?.runs.some((r) => r.status === 'RUNNING')
  useEffect(() => { if (!running) return; const t = setInterval(load, 3000); return () => clearInterval(t) }, [running, load])
  const mode = Form.useWatch('mode', form)
  const freq = Form.useWatch('freq', form)
  if (err && !d) return <Alert type="error" showIcon message="Không tải được cấu hình đồng bộ" description={err} />
  if (!d) return <Skeleton active paragraph={{ rows: 8 }} />
  const save = async () => {
    const v = await form.validateFields()
    setBusy('save')
    try { const c = await syncApi.save(code, v); setDirty(false); message.success(c.mode === 'SCHEDULE' ? `Đã lưu – lần chạy kế tiếp ${fmtAt(c.next_run_at)}` : 'Đã lưu – chỉ chạy khi bấm'); load() }
    catch (e) { message.error((e as Error).message) } finally { setBusy(null) }
  }
  const runNow = async (scope: string) => {
    setBusy(scope)
    try { const r = await syncApi.run(code, scope); message.success(`Đã bắt đầu lượt #${r.run_id}`); load() }
    catch (e) { message.error((e as Error).message) } finally { setBusy(null) }
  }
  const c = d.config
  const cols: TableColumnsType<SyncRun> = [
    { title: '#', dataIndex: 'id', width: 56, render: (v: number) => <span className="num">{v}</span> },
    { title: 'Kích hoạt', dataIndex: 'trigger', width: 110, render: (v: string) => v === 'SCHEDULE' ? <span><CalendarOutlined /> Theo lịch</span> : 'Chạy tay' },
    { title: 'Phạm vi', dataIndex: 'scope', width: 140, render: (v: string) => v === 'FULL_SYNC' ? 'Đồng bộ đầy đủ' : 'Chỉ train' },
    { title: 'Kết quả', dataIndex: 'status', width: 170, render: (v: string) => <RunTag value={v} /> },
    { title: 'Người / lịch', dataIndex: 'actor', width: 130, responsive: ['md'] },
    { title: 'Thời gian', key: 't', width: 200, render: (_, r) => <span className="small num">{fmtAt(r.started_at)} → {r.finished_at ? fmtAt(r.finished_at).slice(11) : '…'}</span> },
    { title: 'Ghi chú', dataIndex: 'message', ellipsis: true, responsive: ['lg'], render: (v: string | null, r) => r.batch_id
      ? <a href={`#/p/${code}/training`} className="mono">{r.batch_id}</a> : <span className="small">{v}</span> },
  ]
  return (
    <div data-testid="sync">
      <PageHeader title="Đồng bộ & lịch" description="Tải dữ liệu mới từ Cổng Dịch vụ công và train phần đã duyệt – chạy tay hoặc theo lịch cho từng tỉnh." />
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} xl={15}>
          <Card title="Cấu hình" style={{ height: '100%' }} extra={c.updated_by && <span className="small muted">Sửa lần cuối: {c.updated_by} · {fmtAt(c.updated_at)}</span>}>
            <Form form={form} layout="vertical" initialValues={c} onValuesChange={() => setDirty(true)} requiredMark={false}>
              <Form.Item name="mode" label="Cách chạy">
                <Radio.Group optionType="button" buttonStyle="solid" options={[{ value: 'MANUAL', label: 'Chạy tay' }, { value: 'SCHEDULE', label: 'Theo lịch' }]} />
              </Form.Item>
              <Form.Item name="scope" label="Mỗi lượt làm gì">
                <Radio.Group>
                  <Space direction="vertical" size={8}>
                    <Radio value="TRAIN_ONLY"><b>Chỉ train</b> <span className="muted">– gửi phần đã duyệt chưa lên bot, không tải cổng</span></Radio>
                    <Radio value="FULL_SYNC"><b>Đồng bộ đầy đủ</b> <span className="muted">– kiểm tra cổng → tải dữ liệu mới → nạp, so sánh → train phần đã duyệt</span></Radio>
                  </Space>
                </Radio.Group>
              </Form.Item>
              {mode === 'SCHEDULE' && <Space wrap align="start" size={12}>
                <Form.Item name="freq" label="Tần suất"><Select style={{ width: 150 }} options={Object.entries(d.freqs).map(([k, v]) => ({ value: k, label: v }))} /></Form.Item>
                {freq === 'WEEKLY' && <Form.Item name="weekday" label="Thứ"><Select style={{ width: 130 }} options={WEEKDAYS.map((w, i) => ({ value: i, label: w }))} /></Form.Item>}
                {freq === 'MONTHLY' && <Form.Item name="monthday" label="Ngày" tooltip="Tháng ít ngày hơn thì chạy ngày cuối tháng"><InputNumber min={1} max={31} style={{ width: 90 }} /></Form.Item>}
                <Form.Item name="at_time" label="Giờ" rules={[{ pattern: /^\d{1,2}:\d{2}$/, message: 'Dạng HH:MM, ví dụ 08:00' }]}><Input style={{ width: 90 }} placeholder="08:00" /></Form.Item>
              </Space>}
              <Space wrap>
                <Button type="primary" icon={<SaveOutlined />} loading={busy === 'save'} disabled={!dirty} onClick={save}>Lưu cấu hình</Button>
                {dirty && <span className="small muted">Có thay đổi chưa lưu</span>}
              </Space>
            </Form>
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card title="Trạng thái" style={{ height: '100%' }}>
            <dl className="kv" style={{ marginBottom: 16 }}>
              <dt>Cách chạy</dt><dd>{c.mode_vi}</dd>
              <dt>Phạm vi</dt><dd>{c.scope === 'FULL_SYNC' ? 'Đồng bộ đầy đủ' : 'Chỉ train'}</dd>
              <dt>Lần chạy kế tiếp</dt><dd className="num">{c.mode === 'SCHEDULE' && c.next_run_at ? fmtAt(c.next_run_at) : 'Không có (chạy tay)'}</dd>
            </dl>
            <Space wrap>
              <Button icon={<PlayCircleOutlined />} loading={busy === 'TRAIN_ONLY'} disabled={running} onClick={() => runNow('TRAIN_ONLY')}>Chỉ train phần đã duyệt</Button>
              <Popconfirm title="Tải toàn bộ dữ liệu tỉnh từ Cổng DVC (vài phút) rồi train phần đã duyệt?" okText="Chạy" cancelText="Thôi" onConfirm={() => runNow('FULL_SYNC')}>
                <Button type="primary" icon={<SyncOutlined />} loading={busy === 'FULL_SYNC'} disabled={running}>Đồng bộ đầy đủ</Button></Popconfirm>
            </Space>
            {running && <p className="small" style={{ marginTop: 12, marginBottom: 0 }}><SyncOutlined spin /> Đang chạy – trang tự cập nhật.</p>}
            <ul className="small muted" style={{ margin: '16px 0 0', paddingInlineStart: 18 }}>
              <li>Lịch không tự duyệt – chỉ nội dung đã duyệt lên bot.</li>
              <li>Tỉnh đang có lô chờ gửi / đang train thì lượt đó bỏ qua.</li>
              <li>Lịch chạy khi CMS bật; lỡ giờ thì chạy bù 1 lần khi bật lại.</li>
            </ul>
          </Card>
        </Col>
      </Row>
      <Card title="Lịch sử đồng bộ" styles={{ body: { padding: 0 } }}>
        <Table<SyncRun> rowKey="id" columns={cols} dataSource={d.runs} pagination={{ pageSize: 10, hideOnSinglePage: true }} scroll={{ x: 720 }}
          expandable={{ expandedRowRender: (r) => <Timeline style={{ margin: '8px 0 0 8px' }} items={r.steps.map((s, i) => ({ key: i, color: s.ok ? 'green' : 'red',
            children: <span className="small"><span className="num">{fmtAt(s.at).slice(11)}</span> · <b>{s.step}</b> – {s.detail}</span> }))} /> }}
          locale={{ emptyText: 'Chưa có lượt đồng bộ nào' }} />
      </Card>

    </div>
  )
}
