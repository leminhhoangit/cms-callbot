import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Form, Input, InputNumber, Popconfirm, Radio, Select, Skeleton, Space, Table, Tag, Timeline, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { CalendarOutlined, PlayCircleOutlined, SaveOutlined, SyncOutlined } from '@ant-design/icons'
import { fmtAt, syncApi, type SyncConfig, type SyncRun } from '../api'

const STATUS: Record<string, string> = { RUNNING: 'processing', SUCCEEDED: 'green', NO_CHANGE: 'default', SKIPPED: 'gold', FAILED: 'red' }
const WEEKDAYS = ['Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy', 'Chủ nhật']

/** Đồng bộ DVC -> CMS -> train bot: cấu hình Chạy tay / Theo lịch cho từng tỉnh, chạy ngay, lịch sử từng lượt (các bước). */
export default function Sync({ code }: { code: string }) {
  const { message } = AntApp.useApp()
  const [d, setD] = useState<{ config: SyncConfig; runs: SyncRun[]; scopes: Record<string, string>; freqs: Record<string, string> } | null>(null)
  const [busy, setBusy] = useState(false)
  const [form] = Form.useForm()
  const load = useCallback(() => syncApi.get(code).then((r) => { setD(r); return r }).catch((e) => { message.error((e as Error).message); return null }), [code, message])
  useEffect(() => { load().then((r) => r && form.setFieldsValue(r.config)) }, [load, form])
  const running = !!d?.runs.some((r) => r.status === 'RUNNING')
  useEffect(() => { if (!running) return; const t = setInterval(load, 3000); return () => clearInterval(t) }, [running, load])
  const mode = Form.useWatch('mode', form)
  const freq = Form.useWatch('freq', form)
  if (!d) return <Skeleton active />
  const save = async () => {
    const v = await form.validateFields()
    setBusy(true)
    try { const c = await syncApi.save(code, v); message.success(c.mode === 'SCHEDULE' ? `Đã lưu – lần chạy kế tiếp ${fmtAt(c.next_run_at)}` : 'Đã lưu – chỉ chạy khi bấm'); load() }
    catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }
  const runNow = async (scope: string) => {
    setBusy(true)
    try { const r = await syncApi.run(code, scope); message.success(`Đã bắt đầu lượt #${r.run_id}`); load() }
    catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }
  const cols: TableColumnsType<SyncRun> = [
    { title: '#', dataIndex: 'id', width: 60 },
    { title: 'Kích hoạt', dataIndex: 'trigger', width: 120, render: (v: string) => v === 'SCHEDULE' ? <Tag icon={<CalendarOutlined />} color="purple">Theo lịch</Tag> : <Tag>Chạy tay</Tag> },
    { title: 'Phạm vi', dataIndex: 'scope', width: 160, render: (v: string) => v === 'FULL_SYNC' ? 'Đồng bộ đầy đủ' : 'Chỉ train' },
    { title: 'Kết quả', key: 's', width: 170, render: (_, r) => <Tag color={STATUS[r.status]} icon={r.status === 'RUNNING' ? <SyncOutlined spin /> : undefined}>{r.status_vi}</Tag> },
    { title: 'Người / lịch', dataIndex: 'actor', width: 140 },
    { title: 'Bắt đầu → kết thúc', key: 't', width: 230, render: (_, r) => `${fmtAt(r.started_at)} → ${fmtAt(r.finished_at)}` },
    { title: 'Lô train', dataIndex: 'batch_id', width: 200, render: (v: string | null) => v ? <a href={`#/p/${code}/training`}>{v}</a> : '—' },
    { title: 'Ghi chú', dataIndex: 'message', ellipsis: true },
  ]
  return (
    <div data-testid="sync">
      <Card title={<Space><CalendarOutlined />Cấu hình đồng bộ</Space>} style={{ marginBottom: 16 }}
        extra={d.config.updated_by && <Typography.Text type="secondary">Sửa lần cuối: {d.config.updated_by} · {fmtAt(d.config.updated_at)}</Typography.Text>}>
        <Form form={form} layout="vertical" initialValues={d.config} style={{ maxWidth: 900 }}>
          <Form.Item name="mode" label="Cách chạy">
            <Radio.Group optionType="button" buttonStyle="solid" options={[{ value: 'MANUAL', label: 'Chạy tay' }, { value: 'SCHEDULE', label: 'Theo lịch' }]} />
          </Form.Item>
          <Form.Item name="scope" label="Mỗi lượt làm gì">
            <Radio.Group>
              <Space direction="vertical">
                <Radio value="TRAIN_ONLY"><b>Chỉ train</b> <Typography.Text type="secondary">– gửi phần đã duyệt chưa lên bot (không tải cổng)</Typography.Text></Radio>
                <Radio value="FULL_SYNC"><b>Đồng bộ đầy đủ</b> <Typography.Text type="secondary">– kiểm tra cổng DVC → tải dữ liệu mới (vài phút/tỉnh – đo thật Khánh Hòa ≈ 2 phút) → nhập, so sánh → train phần đã duyệt</Typography.Text></Radio>
              </Space>
            </Radio.Group>
          </Form.Item>
          {mode === 'SCHEDULE' && <Space wrap align="start">
            <Form.Item name="freq" label="Tần suất"><Select style={{ width: 160 }} options={Object.entries(d.freqs).map(([k, v]) => ({ value: k, label: v }))} /></Form.Item>
            {freq === 'WEEKLY' && <Form.Item name="weekday" label="Thứ"><Select style={{ width: 140 }} options={WEEKDAYS.map((w, i) => ({ value: i, label: w }))} /></Form.Item>}
            {freq === 'MONTHLY' && <Form.Item name="monthday" label="Ngày trong tháng" tooltip="Tháng ít ngày hơn -> chạy ngày cuối tháng"><InputNumber min={1} max={31} /></Form.Item>}
            <Form.Item name="at_time" label="Giờ chạy" rules={[{ pattern: /^\d{1,2}:\d{2}$/, message: 'HH:MM' }]}><Input style={{ width: 100 }} placeholder="08:00" /></Form.Item>
          </Space>}
          <Space>
            <Button type="primary" icon={<SaveOutlined />} loading={busy} onClick={save}>Lưu cấu hình</Button>
            {d.config.mode === 'SCHEDULE' && d.config.next_run_at && <Tag color="purple" icon={<CalendarOutlined />}>Lần chạy kế tiếp: {fmtAt(d.config.next_run_at)}</Tag>}
          </Space>
        </Form>
        <Alert type="info" showIcon style={{ marginTop: 16 }} message="Lịch không bao giờ tự duyệt nội dung"
          description="Chỉ nội dung đã được người duyệt mới lên bot. Thủ tục mới / thay đổi từ cổng vào trạng thái Cần duyệt. Tỉnh đang có lô chờ gửi / đang train thì lượt đó bỏ qua. Lịch chạy khi CMS đang bật; lỡ giờ thì chạy bù 1 lần khi bật lại." />
      </Card>
      <Card title="Chạy ngay" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button icon={<PlayCircleOutlined />} loading={busy} disabled={running} onClick={() => runNow('TRAIN_ONLY')}>Chỉ train phần đã duyệt</Button>
          <Popconfirm title="Tải toàn bộ dữ liệu tỉnh từ cổng DVC (vài phút) rồi train phần đã duyệt?" okText="Chạy" cancelText="Thôi" onConfirm={() => runNow('FULL_SYNC')}>
            <Button type="primary" icon={<SyncOutlined />} loading={busy} disabled={running}>Đồng bộ đầy đủ từ DVC</Button></Popconfirm>
          {running && <Tag color="processing" icon={<SyncOutlined spin />}>Đang chạy – tự làm mới</Tag>}
        </Space>
      </Card>
      <Card title="Lịch sử đồng bộ">
        <Table<SyncRun> rowKey="id" size="middle" columns={cols} dataSource={d.runs} pagination={{ pageSize: 10 }}
          expandable={{ expandedRowRender: (r) => <Timeline style={{ marginTop: 8 }} items={r.steps.map((s, i) => ({ key: i, color: s.ok ? 'green' : 'red',
            children: <span style={{ fontSize: 12 }}>{fmtAt(s.at)} · <b>{s.step}</b> – {s.detail}</span> }))} /> }}
          locale={{ emptyText: 'Chưa có lượt đồng bộ nào' }} />
      </Card>
    </div>
  )
}
