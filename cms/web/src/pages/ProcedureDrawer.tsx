import { useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Drawer, Grid, Input, Skeleton, Space, Table, Timeline, Tooltip, Typography } from 'antd'
import { BulbOutlined, CheckOutlined, LinkOutlined, SaveOutlined, UndoOutlined } from '@ant-design/icons'
import { api, fmtAt, type ProcDetail, type Row } from '../api'
import { ChangeTag, fieldOf, ReviewTag } from '../ui'

/** Chi tiết thủ tục: nội dung từng dòng (sinh từ cổng, chỉ đọc), biên tập Câu hỏi + Tags, điền câu hỏi mẫu, duyệt.
 *  Cột đầu hiện TÊN TRƯỜNG (Địa chỉ tiếp nhận, Căn cứ pháp lý…) thay vì tiêu đề đầy đủ lặp tên thủ tục; tiêu đề đầy đủ ở tooltip. */
export default function ProcedureDrawer({ code, fid, onClose, onChanged }: { code: string; fid: string | null; onClose: () => void; onChanged: () => void }) {
  const { message, modal } = AntApp.useApp()
  const screens = Grid.useBreakpoint()
  const [t, setT] = useState<ProcDetail | null>(null)
  const [edit, setEdit] = useState<Record<number, { questions: string; tags: string }>>({})
  const [busy, setBusy] = useState<string | null>(null)
  useEffect(() => { setT(null); setEdit({}); if (fid) api.procedure(code, fid).then(setT).catch((e) => message.error((e as Error).message)) }, [code, fid, message])
  const dirty = Object.keys(edit).length
  const val = (r: Row, k: 'questions' | 'tags') => edit[r.seq]?.[k] ?? r[k] ?? ''
  const change = (r: Row, k: 'questions' | 'tags', v: string) => setEdit({ ...edit, [r.seq]: { questions: val(r, 'questions'), tags: val(r, 'tags'), [k]: v } })
  const doIt = async (key: string, fn: () => Promise<ProcDetail | { changed: number; procedure: ProcDetail }>, ok: (x: number) => string) => {
    setBusy(key)
    try {
      const r = await fn()
      setT('procedure' in r ? r.procedure : r); setEdit({}); message.success(ok('changed' in r ? r.changed : 0)); onChanged()
    } catch (e) { message.error((e as Error).message) } finally { setBusy(null) }
  }
  const close = () => {
    if (!dirty) return onClose()
    modal.confirm({ title: `Bỏ ${dirty} dòng chưa lưu?`, okText: 'Bỏ thay đổi', okButtonProps: { danger: true }, cancelText: 'Tiếp tục sửa', onOk: onClose })
  }
  const save = () => doIt('save', () => api.saveRows(code, t!.fid, Object.entries(edit).map(([s, v]) => ({ seq: Number(s), ...v }))),
    (k) => (k ? `Đã lưu ${k} dòng` : 'Không có thay đổi'))
  return (
    <Drawer open={!!fid} onClose={close} width={screens.lg ? 'min(1200px, 92vw)' : '100%'} destroyOnHidden
      title={t ? <div><div style={{ fontWeight: 600, lineHeight: 1.35 }}>{t.name}</div>
        <div className="cell-sub"><span className="mono">{t.code}</span> · {t.category} · {t.levels}</div></div> : 'Thủ tục'}
      extra={t && t.status === 'ACTIVE' && <Space wrap>
        <Tooltip title="Điền câu hỏi theo luật cho các dòng còn trống – đọc lại trước khi duyệt">
          <Button icon={<BulbOutlined />} loading={busy === 'suggest'} disabled={!!dirty} onClick={() => doIt('suggest', () => api.suggest(code, t.fid),
            (k) => `Đã điền câu hỏi mẫu cho ${k} dòng`)}>Điền câu hỏi mẫu</Button></Tooltip>
        <Button type={dirty ? 'primary' : 'default'} icon={<SaveOutlined />} disabled={!dirty} loading={busy === 'save'} onClick={save}>
          Lưu{dirty ? ` (${dirty})` : ''}</Button>
        {t.review === 'APPROVED'
          ? <Button icon={<UndoOutlined />} loading={busy === 'review'} onClick={() => doIt('review', () => api.review(code, t.fid, false), () => 'Đã bỏ duyệt')}>Bỏ duyệt</Button>
          : <Tooltip title={dirty ? 'Lưu thay đổi trước khi duyệt' : undefined}>
              <Button type="primary" icon={<CheckOutlined />} disabled={!!dirty} loading={busy === 'review'}
                onClick={() => doIt('review', () => api.review(code, t.fid, true), () => 'Đã duyệt nội dung')}>Duyệt nội dung</Button></Tooltip>}
      </Space>}>
      {!t ? <Skeleton active paragraph={{ rows: 10 }} /> : <>
        <Space wrap size={16} style={{ marginBottom: 16 }}>
          <Space size={6}><ChangeTag value={t.change} /><ReviewTag value={t.review} /></Space>
          {t.reviewed_by && <span className="small muted">Duyệt bởi {t.reviewed_by} · {fmtAt(t.reviewed_at)}</span>}
          <a href={t.uri} target="_blank" rel="noreferrer" className="small"><LinkOutlined /> Xem trên Cổng Dịch vụ công</a>
        </Space>
        {t.status === 'REMOVED' && <Alert type="error" showIcon style={{ marginBottom: 12 }} message="Thủ tục đã gỡ khỏi cổng – cần xoá khỏi bot, không biên tập." />}
        {dirty > 0 && <Alert type="info" showIcon style={{ marginBottom: 12 }} message={`${dirty} dòng chưa lưu.${t.review === 'APPROVED' ? ' Lưu sẽ chuyển thủ tục về Cần duyệt.' : ''}`}
          action={<Button size="small" type="primary" onClick={save} loading={busy === 'save'}>Lưu</Button>} />}
        <Table<Row> rowKey="seq" size="small" pagination={false} dataSource={t.rows} scroll={{ x: 900, y: 'calc(100vh - 320px)' }} columns={[
          { title: 'Trường', dataIndex: 'title', width: 190, fixed: 'left',
            render: (v: string) => <Tooltip title={v} placement="topLeft"><span className="field-label">{fieldOf(v, t.name)}</span></Tooltip> },
          { title: 'Nội dung – sinh tự động từ cổng', dataIndex: 'content',
            render: (v: string) => <Typography.Paragraph style={{ fontSize: 13, whiteSpace: 'pre-wrap', margin: 0 }} ellipsis={{ rows: 5, expandable: 'collapsible', symbol: (x) => (x ? 'thu gọn' : 'xem thêm') }}>{v}</Typography.Paragraph> },
          { title: 'Câu hỏi liên quan (cách nhau bởi ;)', key: 'q', width: 280,
            render: (_, r) => <Input.TextArea aria-label={`Câu hỏi dòng ${r.seq + 1}`} autoSize={{ minRows: 2, maxRows: 6 }} value={val(r, 'questions')}
              disabled={t.status !== 'ACTIVE'} status={edit[r.seq] ? 'warning' : undefined} onChange={(e) => change(r, 'questions', e.target.value)} /> },
          { title: 'Tags', key: 't', width: 150,
            render: (_, r) => <Input.TextArea aria-label={`Tags dòng ${r.seq + 1}`} autoSize={{ minRows: 2, maxRows: 4 }} value={val(r, 'tags')}
              disabled={t.status !== 'ACTIVE'} onChange={(e) => change(r, 'tags', e.target.value)} /> },
        ]} />
        {t.history.length > 0 && <>
          <h3 className="section-title" style={{ margin: '20px 0 12px' }}>Lịch sử</h3>
          <Timeline items={t.history.map((h, i) => ({ key: i, children: <span className="small"><span className="num">{fmtAt(h.at)}</span> · <b>{h.actor}</b> · {h.detail}</span> }))} />
        </>}
      </>}
    </Drawer>
  )
}
