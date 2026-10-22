import { useCallback, useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Drawer, Grid, Popconfirm, Progress, Skeleton, Space, Steps, Table, Timeline, Tooltip } from 'antd'
import type { TableColumnsType } from 'antd'
import { CloudUploadOutlined, PlusOutlined, ReloadOutlined, StopOutlined } from '@ant-design/icons'
import { fmtAt, trainApi, type TrainBatch, type TrainPlan, type TrainStatus, type TrainSummary } from '../api'
import { n, PageHeader, StatStrip, TRAIN, TrainTag } from '../ui'

const ACTIVE: TrainStatus[] = ['SUBMITTED', 'QUEUED', 'TRAINING']
const SRC: Record<string, string> = { USER: 'Người dùng', POLL: 'Hỏi trạng thái', CALLBACK: 'iCC gọi lại', SUBMIT: 'iCC nhận', SYSTEM: 'Hệ thống' }

function stepOf(b: TrainBatch) {
  const order: TrainStatus[] = ['DRAFT', 'SUBMITTED', 'QUEUED', 'TRAINING', 'SUCCEEDED']
  const at = b.status === 'FAILED' || b.status === 'CANCELLED' ? (b.started_at ? 'TRAINING' : b.submitted_at ? 'QUEUED' : 'DRAFT') : b.status
  return { current: order.indexOf(at), status: b.status === 'FAILED' ? 'error' as const : b.status === 'SUCCEEDED' ? 'finish' as const : 'process' as const }
}

/** Train bot – chỉ nội dung đã duyệt; mỗi lần gửi là một lô có trạng thái job rõ ràng (docs/01_THIET_KE_TRAIN_BOT.md). */
export default function Training({ code }: { code: string }) {
  const { message } = AntApp.useApp()
  const screens = Grid.useBreakpoint()
  const [d, setD] = useState<{ summary: TrainSummary; batches: TrainBatch[] } | null>(null)
  const [plan, setPlan] = useState<TrainPlan | null>(null)
  const [err, setErr] = useState('')
  const [open, setOpen] = useState<TrainBatch | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const load = useCallback(() => {
    trainApi.overview(code).then((r) => { setErr(''); setD(r) }).catch((e) => setErr((e as Error).message))
    trainApi.plan(code).then(setPlan).catch(() => {})
  }, [code])
  useEffect(() => { load() }, [load])
  const active = !!d?.batches.some((b) => ACTIVE.includes(b.status))
  useEffect(() => { if (!active) return; const t = setInterval(load, 3000); return () => clearInterval(t) }, [active, load])
  useEffect(() => { if (open) trainApi.batch(open.id).then(setOpen).catch(() => {}) }, [d]) // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (key: string, fn: () => Promise<TrainBatch>, ok: (b: TrainBatch) => string) => {
    setBusy(key)
    try { const b = await fn(); message.success(ok(b)); load(); if (open) setOpen(await trainApi.batch(b.id)) } catch (e) { message.error((e as Error).message) } finally { setBusy(null) }
  }
  if (err && !d) return <Alert type="error" showIcon message="Không tải được dữ liệu train" description={err} action={<Button size="small" onClick={load}>Thử lại</Button>} />
  if (!d) return <Skeleton active paragraph={{ rows: 6 }} />
  const s = d.summary
  const pending = (plan?.upserts.length ?? s.need_train) + (plan?.deletes.length ?? s.need_delete)
  const hasDraft = d.batches.some((b) => b.status === 'DRAFT')
  const createHint = s.active_batch ? `Lô ${s.active_batch} đang chạy` : hasDraft ? 'Đang có lô chờ gửi' : !pending ? 'Không có nội dung đã duyệt nào cần train' : undefined
  const cols: TableColumnsType<TrainBatch> = [
    { title: 'Lô', dataIndex: 'id', width: 230, render: (v: string, b) => <>
      <a className="mono" onClick={() => trainApi.batch(b.id).then(setOpen)}>{v}</a>
      {b.attempt > 1 && <div className="cell-sub">Gửi lại lần {b.attempt}</div>}</> },
    { title: 'Trạng thái', dataIndex: 'status', width: 120, render: (v: string) => <TrainTag value={v} /> },
    { title: 'Tiến độ', key: 'p', width: 150, render: (_, b) => <Progress size="small" percent={b.progress}
      status={b.status === 'FAILED' ? 'exception' : b.status === 'TRAINING' ? 'active' : undefined} /> },
    { title: 'Nội dung', key: 'n', width: 150, render: (_, b) => <span className="small num">{b.upserts} cập nhật · {b.deletes} xoá</span> },
    { title: 'Gửi', key: 'by', width: 180, responsive: ['md'], render: (_, b) => b.submitted_by
      ? <><span className="small">{b.submitted_by}</span><div className="cell-sub num">{fmtAt(b.submitted_at)}</div></>
      : <span className="small muted">Tạo bởi {b.created_by}</span> },
    { title: 'Xong lúc', dataIndex: 'finished_at', width: 140, responsive: ['lg'], render: (v: string | null) => <span className="small num">{fmtAt(v)}</span> },
    { title: <span className="sr-only">Thao tác</span>, key: 'a', width: 190, render: (_, b) => <Space size={4}>
      {b.status === 'DRAFT' && <Popconfirm title={`Gửi ${b.upserts} cập nhật, ${b.deletes} xoá sang bot?`} okText="Gửi" cancelText="Thôi"
        onConfirm={() => act(`s${b.id}`, () => trainApi.submit(b.id), (x) => `Đã gửi – job ${x.remote_job_id}`)}>
        <Button size="small" type="primary" icon={<CloudUploadOutlined />} loading={busy === `s${b.id}`}>Gửi train</Button></Popconfirm>}
      {ACTIVE.includes(b.status) && <Button size="small" icon={<ReloadOutlined />} loading={busy === `r${b.id}`}
        onClick={() => act(`r${b.id}`, () => trainApi.refresh(b.id), (x) => TRAIN[x.status].vi)}>Cập nhật</Button>}
      {(b.status === 'DRAFT' || b.status === 'SUBMITTED' || b.status === 'QUEUED') && <Popconfirm title="Huỷ lô này?" okText="Huỷ lô" okButtonProps={{ danger: true }} cancelText="Thôi"
        onConfirm={() => act(`c${b.id}`, () => trainApi.cancel(b.id), () => 'Đã huỷ lô')}>
        <Button size="small" danger icon={<StopOutlined />} aria-label={`Huỷ lô ${b.id}`} /></Popconfirm>}
      {(b.status === 'FAILED' || b.status === 'CANCELLED') && <Button size="small" loading={busy === `g${b.id}`}
        onClick={() => act(`g${b.id}`, () => trainApi.retry(b.id), (x) => `Đã tạo lô ${x.id} (lần ${x.attempt})`)}>Gửi lại</Button>}
    </Space> },
  ]
  return (
    <div data-testid="training">
      <PageHeader title="Train bot" description="Đưa nội dung đã duyệt lên callbot và theo dõi từng job đến khi train xong."
        actions={<Tooltip title={createHint}><Button type="primary" icon={<PlusOutlined />} loading={busy === 'create'} disabled={!!createHint}
          onClick={() => act('create', () => trainApi.create(code), (b) => `Đã tạo lô ${b.id}: ${b.upserts} cập nhật, ${b.deletes} xoá`)}>
          Tạo lô train{pending ? ` (${pending})` : ''}</Button></Tooltip>} />
      {s.mock && <Alert type="warning" showIcon style={{ marginBottom: 16 }}
        message={<>Đang dùng <b>API iCC giả lập</b> ({s.url}) – iCC chưa cung cấp API train thật, chưa có dữ liệu nào lên bot thật.</>} />}
      <StatStrip label="Trạng thái nội dung trên bot" items={[
        { label: 'Bot đang có (đúng bản)', value: n(s.synced), tone: 'success' },
        { label: 'Cần train', value: n(s.need_train), hint: 'Đã duyệt, chưa lên bot', tone: s.need_train ? 'primary' : undefined },
        { label: 'Cần xoá khỏi bot', value: n(s.need_delete), hint: 'Đã gỡ khỏi cổng', tone: s.need_delete ? 'error' : undefined },
        { label: 'Chờ duyệt', value: n(s.waiting_review), hint: 'Không gửi khi chưa duyệt' },
      ]} />
      <Card title="Lô train" extra={s.last_success && <span className="small muted">Train xong gần nhất: <span className="mono">{s.last_success.id}</span> · {fmtAt(s.last_success.finished_at)}</span>}
        styles={{ body: { padding: 0 } }}>
        <Table<TrainBatch> rowKey="id" columns={cols} dataSource={d.batches} pagination={{ pageSize: 10, hideOnSinglePage: true }} scroll={{ x: 760 }}
          locale={{ emptyText: 'Chưa có lô nào – duyệt nội dung ở trang Thủ tục hành chính rồi bấm "Tạo lô train"' }} />
      </Card>
      <p className="small muted" style={{ marginTop: 12 }}>Mỗi tỉnh chỉ một lô chạy cùng lúc. Trạng thái tự cập nhật (hỏi iCC 5 giây/lần và nhận iCC gọi lại).
        Lô lỗi: bot giữ bản cũ, bấm "Gửi lại" để tạo lô mới từ phần còn cần train.</p>
      <Drawer open={!!open} onClose={() => setOpen(null)} width={screens.md ? 'min(880px, 92vw)' : '100%'}
        title={open && <Space><span className="mono">{open.id}</span><TrainTag value={open.status} /></Space>}>
        {open && <>
          <Steps size="small" {...stepOf(open)} style={{ marginBottom: 16 }} responsive
            items={['Chờ gửi', 'Đã gửi', 'Xếp hàng', 'Đang train', open.status === 'FAILED' ? 'Lỗi' : open.status === 'CANCELLED' ? 'Đã huỷ' : 'Train xong'].map((t) => ({ title: t }))} />
          <Progress percent={open.progress} status={open.status === 'FAILED' ? 'exception' : open.status === 'TRAINING' ? 'active' : undefined} />
          <dl className="kv" style={{ margin: '16px 0' }}>
            <dt>Mã job iCC</dt><dd className="mono">{open.remote_job_id ?? '—'}</dd>
            <dt>Bot</dt><dd className="mono">{open.bot_id}</dd>
            <dt>Tạo</dt><dd>{open.created_by} · <span className="num">{fmtAt(open.created_at)}</span></dd>
            <dt>Gửi</dt><dd>{open.submitted_by ? <>{open.submitted_by} · <span className="num">{fmtAt(open.submitted_at)}</span></> : '—'}</dd>
            <dt>Bắt đầu / kết thúc</dt><dd className="num">{fmtAt(open.started_at)} → {fmtAt(open.finished_at)}</dd>
            <dt>Nội dung</dt><dd className="num">{open.upserts} cập nhật · {open.deletes} xoá · {n(open.rows)} dòng</dd>
            {open.parent_id && <><dt>Lô trước</dt><dd className="mono">{open.parent_id}</dd></>}
          </dl>
          {open.error && <Alert type="error" showIcon message={open.error} style={{ marginBottom: 16 }} />}
          <h3 className="section-title" style={{ marginBottom: 12 }}>Dòng thời gian</h3>
          <Timeline items={(open.events ?? []).map((e, i) => ({ key: i, color: e.status === 'FAILED' ? 'red' : e.status === 'SUCCEEDED' ? 'green' : 'blue',
            children: <span className="small"><span className="num">{fmtAt(e.at)}</span> · <TrainTag value={e.status} /> {e.progress ? <span className="num">{e.progress}% · </span> : ''}{SRC[e.source] ?? e.source}{e.message ? ` – ${e.message}` : ''}</span> }))} />
          <h3 className="section-title" style={{ marginBottom: 12 }}>Thủ tục trong lô ({open.items?.length ?? 0})</h3>
          <Table size="small" rowKey="fid" pagination={{ pageSize: 20, hideOnSinglePage: true }} dataSource={open.items} columns={[
            { title: 'Thao tác', dataIndex: 'action', width: 100, render: (v: string) => v === 'DELETE' ? <span style={{ color: 'var(--c-error)' }}>Xoá</span> : 'Cập nhật' },
            { title: 'Thủ tục', dataIndex: 'name', render: (v: string, i) => <>{v}<div className="cell-sub mono">{i.code}</div></> },
            { title: 'Dòng', dataIndex: 'rows', width: 70, align: 'right', render: (v: number) => <span className="num">{v}</span> },
          ]} />
        </>}
      </Drawer>
    </div>
  )
}
