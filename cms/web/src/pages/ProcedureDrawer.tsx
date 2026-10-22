import { useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Descriptions, Drawer, Input, Skeleton, Space, Table, Tag, Timeline, Typography } from 'antd'
import { BulbOutlined, CheckOutlined, LinkOutlined, SaveOutlined, UndoOutlined } from '@ant-design/icons'
import { api, fmtAt, type ProcDetail, type Row } from '../api'
import { CHANGE, REVIEW } from './Procedures'

/** Chi tiết thủ tục: nội dung từng dòng (sinh từ cổng, chỉ đọc), biên tập Câu hỏi + Tags, điền câu hỏi mẫu, duyệt. */
export default function ProcedureDrawer({ code, fid, onClose, onChanged }: { code: string; fid: string | null; onClose: () => void; onChanged: () => void }) {
  const { message } = AntApp.useApp()
  const [t, setT] = useState<ProcDetail | null>(null)
  const [edit, setEdit] = useState<Record<number, { questions: string; tags: string }>>({})
  const [busy, setBusy] = useState(false)
  useEffect(() => { setT(null); setEdit({}); if (fid) api.procedure(code, fid).then(setT).catch((e) => message.error((e as Error).message)) }, [code, fid, message])
  const dirty = Object.keys(edit).length
  const val = (r: Row, k: 'questions' | 'tags') => edit[r.seq]?.[k] ?? r[k] ?? ''
  const change = (r: Row, k: 'questions' | 'tags', v: string) => setEdit({ ...edit, [r.seq]: { questions: val(r, 'questions'), tags: val(r, 'tags'), [k]: v } })
  const doIt = async (fn: () => Promise<ProcDetail | { changed: number; procedure: ProcDetail }>, ok: (x: number) => string) => {
    setBusy(true)
    try {
      const r = await fn()
      const p = 'procedure' in r ? r.procedure : r
      setT(p); setEdit({}); message.success(ok('changed' in r ? r.changed : 0)); onChanged()
    } catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <Drawer open={!!fid} onClose={onClose} width="min(1200px, 96vw)" destroyOnHidden title={t?.name ?? 'Thủ tục'}
      extra={t && t.status === 'ACTIVE' && <Space>
        <Button icon={<BulbOutlined />} loading={busy} onClick={() => doIt(() => api.suggest(code, t.fid), (n) => `Đã điền câu hỏi mẫu cho ${n} dòng – đọc lại trước khi duyệt`)}>Điền câu hỏi mẫu</Button>
        <Button type="primary" icon={<SaveOutlined />} disabled={!dirty} loading={busy}
          onClick={() => doIt(() => api.saveRows(code, t.fid, Object.entries(edit).map(([s, v]) => ({ seq: Number(s), ...v }))), (n) => (n ? `Đã lưu ${n} dòng` : 'Không có thay đổi'))}>
          Lưu{dirty ? ` (${dirty})` : ''}</Button>
        {t.review === 'APPROVED'
          ? <Button icon={<UndoOutlined />} loading={busy} onClick={() => doIt(() => api.review(code, t.fid, false), () => 'Đã bỏ duyệt')}>Bỏ duyệt</Button>
          : <Button type="primary" style={{ background: '#389e0d' }} icon={<CheckOutlined />} disabled={!!dirty} loading={busy}
              onClick={() => doIt(() => api.review(code, t.fid, true), () => 'Đã duyệt nội dung')}>Duyệt nội dung</Button>}
      </Space>}>
      {!t ? <Skeleton active /> : <>
        <Descriptions size="small" column={{ xs: 1, md: 3 }} style={{ marginBottom: 12 }} items={[
          { key: 'c', label: 'Mã', children: <Typography.Text code>{t.code}</Typography.Text> },
          { key: 'l', label: 'Lĩnh vực', children: t.category },
          { key: 'v', label: 'Cấp', children: t.levels },
          { key: 's', label: 'Trạng thái', children: <Space><Tag color={CHANGE[t.change]?.color}>{CHANGE[t.change]?.vi}</Tag><Tag color={REVIEW[t.review].color}>{REVIEW[t.review].vi}</Tag>
            {t.reviewed_by && <Typography.Text type="secondary">{t.reviewed_by} · {fmtAt(t.reviewed_at)}</Typography.Text>}</Space> },
          { key: 'u', label: 'Nguồn', children: <a href={t.uri} target="_blank" rel="noreferrer"><LinkOutlined /> Cổng Dịch vụ công Quốc gia</a> },
        ]} />
        {t.status === 'REMOVED' && <Alert type="error" showIcon style={{ marginBottom: 12 }} message="Thủ tục đã gỡ khỏi cổng – xoá khỏi tập train callbot." />}
        {dirty > 0 && <Alert type="info" showIcon style={{ marginBottom: 12 }} message={`${dirty} dòng chưa lưu. Sửa thủ tục đã duyệt sẽ chuyển về Cần duyệt.`} />}
        <Table<Row> rowKey="seq" size="small" pagination={false} dataSource={t.rows} scroll={{ y: 'calc(100vh - 330px)' }} columns={[
          { title: 'Tiêu đề (A)', dataIndex: 'title', width: '22%', render: (v: string) => <span style={{ fontSize: 12 }}>{v}</span> },
          { title: 'Nội dung (B) – sinh tự động từ cổng', dataIndex: 'content',
            render: (v: string) => <Typography.Paragraph style={{ fontSize: 12, whiteSpace: 'pre-wrap', margin: 0 }} ellipsis={{ rows: 6, expandable: true, symbol: 'xem thêm' }}>{v}</Typography.Paragraph> },
          { title: 'Câu hỏi liên quan (C) – cách nhau bởi ";"', key: 'q', width: '24%',
            render: (_, r) => <Input.TextArea aria-label={`Câu hỏi dòng ${r.seq + 1}`} autoSize={{ minRows: 2, maxRows: 6 }} value={val(r, 'questions')}
              disabled={t.status !== 'ACTIVE'} onChange={(e) => change(r, 'questions', e.target.value)} /> },
          { title: 'Tags (D)', key: 't', width: '13%',
            render: (_, r) => <Input.TextArea aria-label={`Tags dòng ${r.seq + 1}`} autoSize={{ minRows: 2, maxRows: 4 }} value={val(r, 'tags')}
              disabled={t.status !== 'ACTIVE'} onChange={(e) => change(r, 'tags', e.target.value)} /> },
        ]} />
        {t.history.length > 0 && <>
          <Typography.Title level={5} style={{ marginTop: 16 }}>Lịch sử</Typography.Title>
          <Timeline items={t.history.map((h, i) => ({ key: i, children: <span style={{ fontSize: 12 }}>{fmtAt(h.at)} · <b>{h.actor}</b> · {h.detail}</span> }))} />
        </>}
      </>}
    </Drawer>
  )
}
