import { useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Checkbox, Col, Form, Input, Popconfirm, Row, Skeleton } from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { api, fmtAt, type Province } from '../api'
import { PageHeader } from '../ui'

/** Cấu hình tỉnh: tên, địa chỉ tiếp nhận, tiền tố file; "Dựng lại nội dung" áp dụng cho dữ liệu đã nạp (không tải lại cổng). */
export default function Settings({ code }: { code: string }) {
  const { message } = AntApp.useApp()
  const [p, setP] = useState<Province | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [dirty, setDirty] = useState(false)
  const [form] = Form.useForm()
  useEffect(() => { api.province(code).then((r) => { setP(r.province); form.setFieldsValue({ ...r.province, with_conditions: !!r.province.with_conditions }) })
    .catch((e) => setErr((e as Error).message)) }, [code, form])
  if (err) return <Alert type="error" showIcon message="Không tải được cấu hình" description={err} />
  if (!p) return <Skeleton active paragraph={{ rows: 6 }} />
  const save = async () => {
    const v = await form.validateFields()
    setBusy('save')
    try { const r = await api.saveSettings(code, v); setP(r); setDirty(false); message.success("Đã lưu. Bấm 'Dựng lại nội dung' để áp dụng cho dữ liệu đã nạp.") }
    catch (e) { message.error((e as Error).message) } finally { setBusy(null) }
  }
  const rebuild = async () => {
    setBusy('rebuild')
    try { const r = await api.rebuild(code); message.success(`Đã dựng lại: ${r.changed} thủ tục thay đổi (cần duyệt lại)`) }
    catch (e) { message.error((e as Error).message) } finally { setBusy(null) }
  }
  return (
    <div data-testid="settings">
      <PageHeader title="Cấu hình tỉnh" description={`${p.display} – các giá trị dùng khi sinh nội dung callbot.`} />
      {!!p.auto && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="Địa chỉ tiếp nhận đang là câu chung"
        description="Cấu hình được sinh tự động. Bổ sung địa chỉ Trung tâm Phục vụ hành chính công thật để callbot trả lời đúng." />}
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={16}>
          <Card title="Thông tin tỉnh" extra={p.updated_by && <span className="small muted">Sửa lần cuối: {p.updated_by} · {fmtAt(p.updated_at)}</span>}>
            <Form form={form} layout="vertical" requiredMark={false} onValuesChange={() => setDirty(true)}>
              <Row gutter={16}>
                <Col xs={24} md={12}><Form.Item name="display" label="Tên hiển thị"><Input /></Form.Item></Col>
                <Col xs={12} md={8}><Form.Item name="short" label="Tên ngắn"><Input /></Form.Item></Col>
                <Col xs={12} md={4}><Form.Item name="file_prefix" label="Tiền tố file" rules={[{ pattern: /^[A-Z0-9]{2,6}$/, message: '2–6 chữ in hoa / số' }]}><Input /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name="ubnd" label="Tên UBND"><Input /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name="in_phrase" label='Cụm "tại …"'><Input /></Form.Item></Col>
              </Row>
              <Form.Item name="center_address" label="Địa chỉ tiếp nhận (Trung tâm Phục vụ hành chính công)"><Input.TextArea autoSize={{ minRows: 3, maxRows: 8 }} /></Form.Item>
              <Form.Item name="with_conditions" valuePropName="checked"><Checkbox>Có dòng "Yêu cầu, điều kiện thực hiện"</Checkbox></Form.Item>
              <Button type="primary" icon={<SaveOutlined />} loading={busy === 'save'} disabled={!dirty} onClick={save}>Lưu cấu hình</Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} xl={8}>
          <Card title="Dựng lại nội dung">
            <p className="small muted" style={{ marginTop: 0 }}>Áp dụng cấu hình cho dữ liệu đã nạp (không tải lại cổng). Thủ tục có nội dung đổi chuyển về Cần duyệt; câu hỏi / tags giữ nguyên.</p>
            <Popconfirm title="Dựng lại toàn bộ nội dung của tỉnh?" okText="Dựng lại" cancelText="Huỷ" onConfirm={rebuild}>
              <Button icon={<ReloadOutlined />} loading={busy === 'rebuild'} disabled={dirty}>Dựng lại nội dung</Button></Popconfirm>
            {dirty && <p className="small muted" style={{ marginBottom: 0 }}>Lưu cấu hình trước khi dựng lại.</p>}
          </Card>
        </Col>
      </Row>
    </div>
  )
}
