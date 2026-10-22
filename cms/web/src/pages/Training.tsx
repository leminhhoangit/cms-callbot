import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Col, Descriptions, Drawer, Popconfirm, Progress, Row, Skeleton, Space, Statistic, Steps, Table, Tag, Timeline, Typography } from 'antd'
import type { TableColumnsType } from 'antd'
import { CloudUploadOutlined, PlusOutlined, ReloadOutlined, RobotOutlined, StopOutlined } from '@ant-design/icons'
import { fmtAt, trainApi, type TrainBatch, type TrainPlan, type TrainStatus, type TrainSummary } from '../api'

const COLOR: Record<TrainStatus, string> = { DRAFT: 'default', SUBMITTED: 'blue', QUEUED: 'cyan', TRAINING: 'processing', SUCCEEDED: 'green', FAILED: 'red', CANCELLED: 'default' }
const VI: Record<TrainStatus, string> = { DRAFT: 'Chờ gửi', SUBMITTED: 'Đã gửi', QUEUED: 'Xếp hàng', TRAINING: 'Đang train', SUCCEEDED: 'Train xong', FAILED: 'Lỗi', CANCELLED: 'Đã huỷ' }
const ACTIVE: TrainStatus[] = ['SUBMITTED', 'QUEUED', 'TRAINING']
const SRC: Record<string, string> = { USER: 'Người dùng', POLL: 'Hỏi trạng thái', CALLBACK: 'iCC gọi lại', SUBMIT: 'iCC nhận', SYSTEM: 'Hệ thống' }

function stepOf(b: TrainBatch) {
  const order: TrainStatus[] = ['DRAFT', 'SUBMITTED', 'QUEUED', 'TRAINING', 'SUCCEEDED']
  const i = order.indexOf(b.status === 'FAILED' || b.status === 'CANCELLED' ? (b.started_at ? 'TRAINING' : b.submitted_at ? 'QUEUED' : 'DRAFT') : b.status)
  return { current: i, status: b.status === 'FAILED' ? 'error' as const : b.status === 'SUCCEEDED' ? 'finish' as const : 'process' as const }
}

/** Train bot – chỉ nội dung đã duyệt; mỗi lần gửi là một lô có trạng thái job rõ ràng (docs/01_THIET_KE_TRAIN_BOT.md). */
export default function Training({ code }: { code: string }) {
  const { message } = AntApp.useApp()
  const [d, setD] = useState<{ summary: TrainSummary; batches: TrainBatch[] } | null>(null)
  const [plan, setPlan] = useState<TrainPlan | null>(null)
  const [open, setOpen] = useState<TrainBatch | null>(null)
  const [busy, setBusy] = useState(false)
  const load = useCallback(() => {
    trainApi.overview(code).then(setD).catch((e) => message.error((e as Error).message))
    trainApi.plan(code).then(setPlan).catch(() => {})
  }, [code, message])
  useEffect(() => { load() }, [load])
  const active = !!d?.batches.some((b) => ACTIVE.includes(b.status))
  useEffect(() => { if (!active) return; const t = setInterval(load, 3000); return () => clearInterval(t) }, [active, load])
  useEffect(() => { if (open) trainApi.batch(open.id).then(setOpen).catch(() => {}) }, [d]) // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (fn: () => Promise<TrainBatch>, ok: (b: TrainBatch) => string) => {
    setBusy(true)
    try { const b = await fn(); message.success(ok(b)); load(); if (open) setOpen(await trainApi.batch(b.id)) } catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }
  if (!d) return <Skeleton active />
  const s = d.summary
  const cols: TableColumnsType<TrainBatch> = [
    { title: 'Lô', dataIndex: 'id', width: 230, render: (v: string, b) => <><a onClick={() => trainApi.batch(b.id).then(setOpen)}>{v}</a>{b.attempt > 1 && <Tag style={{ marginLeft: 6 }}>lần {b.attempt}</Tag>}</> },
    { title: 'Trạng thái', dataIndex: 'status', width: 130, render: (v: TrainStatus) => <Tag color={COLOR[v]}>{VI[v]}</Tag> },
    { title: 'Tiến độ', key: 'p', width: 170, render: (_, b) => <Progress size="small" percent={b.progress} status={b.status === 'FAILED' ? 'exception' : b.status === 'TRAINING' ? 'active' : undefined} /> },
    { title: 'Cập nhật / xoá', key: 'n', width: 120, render: (_, b) => `${b.upserts} / ${b.deletes}` },
    { title: 'Người gửi', key: 'by', width: 150, render: (_, b) => b.submitted_by ?? <span style={{ color: '#8c8c8c' }}>{b.created_by} (tạo)</span> },
    { title: 'Gửi lúc → xong lúc', key: 't', width: 230, render: (_, b) => `${fmtAt(b.submitted_at)} → ${fmtAt(b.finished_at)}` },
    { title: 'Ghi chú', key: 'm', ellipsis: true, render: (_, b) => b.error ? <Typography.Text type="danger">{b.error}</Typography.Text> : b.message },
    { title: '', key: 'a', width: 200, render: (_, b) => <Space size={4}>
      {b.status === 'DRAFT' && <Popconfirm title={`Gửi ${b.upserts} cập nhật, ${b.deletes} xoá sang bot?`} okText="Gửi" cancelText="Thôi"
        onConfirm={() => act(() => trainApi.submit(b.id), (x) => `Đã gửi – job ${x.remote_job_id}`)}><Button size="small" type="primary" icon={<CloudUploadOutlined />}>Gửi train</Button></Popconfirm>}
      {ACTIVE.includes(b.status) && <Button size="small" icon={<ReloadOutlined />} onClick={() => act(() => trainApi.refresh(b.id), (x) => VI[x.status])}>Cập nhật</Button>}
      {(b.status === 'DRAFT' || b.status === 'SUBMITTED' || b.status === 'QUEUED') && <Popconfirm title="Huỷ lô này?" okText="Huỷ lô" cancelText="Thôi"
        onConfirm={() => act(() => trainApi.cancel(b.id), () => 'Đã huỷ')}><Button size="small" danger icon={<StopOutlined />} /></Popconfirm>}
      {(b.status === 'FAILED' || b.status === 'CANCELLED') && <Button size="small" onClick={() => act(() => trainApi.retry(b.id), (x) => `Đã tạo lô ${x.id} (lần ${x.attempt})`)}>Gửi lại</Button>}
    </Space> },
  ]
  return (
    <div data-testid="training">
      {s.mock && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="Đang dùng API iCC GIẢ LẬP"
        description={`iCC chưa cung cấp API train thật. Bot ${s.bot_id} ở ${s.url} là máy giả lập để kiểm thử luồng – chưa có dữ liệu nào lên bot thật.`} />}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><Card><Statistic title="Bot đang có (đúng bản)" value={s.synced} groupSeparator="." valueStyle={{ color: '#389e0d' }} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="Cần train (đã duyệt, chưa lên bot)" value={s.need_train} groupSeparator="." valueStyle={{ color: s.need_train ? '#0b5cad' : undefined }} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="Cần xoá khỏi bot" value={s.need_delete} groupSeparator="." valueStyle={{ color: s.need_delete ? '#cf1322' : undefined }} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="Chờ duyệt (chưa gửi)" value={s.waiting_review} groupSeparator="." /></Card></Col>
      </Row>
      <Card title={<Space><RobotOutlined />Lô train</Space>} extra={<Space>
        {s.last_success && <Typography.Text type="secondary">Train xong gần nhất: {s.last_success.id} · {fmtAt(s.last_success.finished_at)}</Typography.Text>}
        <Button type="primary" icon={<PlusOutlined />} loading={busy} disabled={!!s.active_batch || d.batches.some((b) => b.status === 'DRAFT') || !(s.need_train + s.need_delete)}
          onClick={() => act(() => trainApi.create(code), (b) => `Đã tạo lô ${b.id}: ${b.upserts} cập nhật, ${b.deletes} xoá`)}>
          Tạo lô train ({(plan?.upserts.length ?? 0) + (plan?.deletes.length ?? 0)})</Button></Space>}>
        <Table<TrainBatch> rowKey="id" size="middle" columns={cols} dataSource={d.batches} pagination={{ pageSize: 10 }}
          locale={{ emptyText: 'Chưa có lô nào – duyệt nội dung ở trang Thủ tục rồi bấm "Tạo lô train"' }} />
        <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
          Chỉ thủ tục <b>đã duyệt</b> được gửi. Mỗi tỉnh chỉ một lô chạy cùng lúc. Trạng thái tự cập nhật (hỏi iCC mỗi 5 giây + iCC gọi lại khi có callback).
          Lỗi → bot giữ bản cũ, bấm "Gửi lại" để tạo lô mới từ những gì còn cần train.</Typography.Paragraph>
      </Card>
      <Drawer open={!!open} onClose={() => setOpen(null)} width="min(900px, 96vw)" title={open && <Space>{open.id}<Tag color={COLOR[open.status]}>{VI[open.status]}</Tag></Space>}>
        {open && <>
          <Steps size="small" {...stepOf(open)} style={{ marginBottom: 16 }}
            items={['Chờ gửi', 'Đã gửi', 'Xếp hàng', 'Đang train', open.status === 'FAILED' ? 'Lỗi' : open.status === 'CANCELLED' ? 'Đã huỷ' : 'Train xong'].map((t) => ({ title: t }))} />
          <Progress percent={open.progress} status={open.status === 'FAILED' ? 'exception' : open.status === 'TRAINING' ? 'active' : undefined} />
          <Descriptions size="small" column={2} style={{ margin: '12px 0' }} items={[
            { key: 'j', label: 'Mã job iCC', children: open.remote_job_id ?? '—' }, { key: 'b', label: 'Bot', children: open.bot_id },
            { key: 'c', label: 'Tạo', children: `${open.created_by} · ${fmtAt(open.created_at)}` }, { key: 's', label: 'Gửi', children: open.submitted_by ? `${open.submitted_by} · ${fmtAt(open.submitted_at)}` : '—' },
            { key: 'st', label: 'Bắt đầu train', children: fmtAt(open.started_at) }, { key: 'f', label: 'Kết thúc', children: fmtAt(open.finished_at) },
            { key: 'n', label: 'Nội dung', children: `${open.upserts} cập nhật · ${open.deletes} xoá · ${open.rows.toLocaleString('vi-VN')} dòng` },
            { key: 'p', label: 'Lô trước', children: open.parent_id ?? '—' },
          ]} />
          {open.error && <Alert type="error" showIcon message={open.error} style={{ marginBottom: 12 }} />}
          <Typography.Title level={5}>Dòng thời gian</Typography.Title>
          <Timeline items={(open.events ?? []).map((e, i) => ({ key: i, color: e.status === 'FAILED' ? 'red' : e.status === 'SUCCEEDED' ? 'green' : 'blue',
            children: <span style={{ fontSize: 12 }}>{fmtAt(e.at)} · <Tag color={COLOR[e.status]}>{VI[e.status]}</Tag>{e.progress ? `${e.progress}% · ` : ''}{SRC[e.source] ?? e.source}{e.message ? ` – ${e.message}` : ''}</span> }))} />
          <Typography.Title level={5}>Thủ tục trong lô ({open.items?.length ?? 0})</Typography.Title>
          <Table size="small" rowKey="fid" pagination={{ pageSize: 20 }} dataSource={open.items} columns={[
            { title: 'Thao tác', dataIndex: 'action', width: 110, render: (v: string) => v === 'DELETE' ? <Tag color="red">Xoá</Tag> : <Tag color="blue">Cập nhật</Tag> },
            { title: 'Mã', dataIndex: 'code', width: 110 }, { title: 'Tên thủ tục', dataIndex: 'name' }, { title: 'Dòng', dataIndex: 'rows', width: 70 },
          ]} />
        </>}
      </Drawer>
    </div>
  )
}
