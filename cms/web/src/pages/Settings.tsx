import { useEffect, useState } from 'react'
import { Alert, App as AntApp, Button, Card, Checkbox, Form, Input, Popconfirm, Skeleton, Space, Typography } from 'antd'
import { ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import { api, fmtAt, type Province } from '../api'

/** Cấu hình tỉnh: tên, địa chỉ tiếp nhận, tiền tố file; "Dựng lại nội dung" áp dụng cho dữ liệu đã nhập (không tải lại cổng). */
export default function Settings({ code }: { code: string }) {
  const { message } = AntApp.useApp()
  const [p, setP] = useState<Province | null>(null)
  const [busy, setBusy] = useState(false)
  const [form] = Form.useForm()
  useEffect(() => { api.province(code).then((r) => { setP(r.province); form.setFieldsValue({ ...r.province, with_conditions: !!r.province.with_conditions }) })
    .catch((e) => message.error((e as Error).message)) }, [code, form, message])
  if (!p) return <Skeleton active />
  const save = async () => {
    const v = await form.validateFields()
    setBusy(true)
    try { const r = await api.saveSettings(code, v); setP(r); message.success("Đã lưu. Bấm 'Dựng lại nội dung' để áp dụng cho dữ liệu đã nhập.") }
    catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }
  const rebuild = async () => {
    setBusy(true)
    try { const r = await api.rebuild(code); message.success(`Đã dựng lại: ${r.changed} thủ tục thay đổi (cần duyệt lại)`) }
    catch (e) { message.error((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <div data-testid="settings">
      <Card title={`Cấu hình ${p.display}`} extra={p.updated_by && <Typography.Text type="secondary">Sửa lần cuối: {p.updated_by} · {fmtAt(p.updated_at)}</Typography.Text>}>
        {!!p.auto && <Alert type="warning" showIcon style={{ marginBottom: 16 }} message="Cấu hình tự sinh – địa chỉ tiếp nhận đang là câu chung. Bổ sung địa chỉ Trung tâm Phục vụ hành chính công thật." />}
        <Form form={form} layout="vertical" style={{ maxWidth: 900 }}>
          <Space wrap align="start">
            <Form.Item name="display" label="Tên hiển thị"><Input style={{ width: 300 }} /></Form.Item>
            <Form.Item name="short" label="Tên ngắn"><Input style={{ width: 200 }} /></Form.Item>
            <Form.Item name="file_prefix" label="Tiền tố file" rules={[{ pattern: /^[A-Z0-9]{2,6}$/, message: '2–6 chữ in hoa / số' }]}><Input style={{ width: 120 }} /></Form.Item>
          </Space>
          <Space wrap align="start">
            <Form.Item name="ubnd" label="Tên UBND"><Input style={{ width: 300 }} /></Form.Item>
            <Form.Item name="in_phrase" label='Cụm "tại …"'><Input style={{ width: 300 }} /></Form.Item>
          </Space>
          <Form.Item name="center_address" label="Địa chỉ tiếp nhận (Trung tâm Phục vụ hành chính công)"><Input.TextArea autoSize={{ minRows: 3, maxRows: 8 }} /></Form.Item>
          <Form.Item name="with_conditions" valuePropName="checked"><Checkbox>Có dòng "Yêu cầu, điều kiện thực hiện"</Checkbox></Form.Item>
          <Button type="primary" icon={<SaveOutlined />} loading={busy} onClick={save}>Lưu cấu hình</Button>
        </Form>
      </Card>
      <Card title="Dựng lại nội dung" style={{ marginTop: 16 }}>
        <Typography.Paragraph type="secondary">Áp dụng cấu hình mới cho dữ liệu đã nhập (không tải lại cổng). Thủ tục có nội dung đổi → Cần duyệt lại; câu hỏi / tags giữ nguyên.</Typography.Paragraph>
        <Popconfirm title="Dựng lại toàn bộ nội dung của tỉnh?" okText="Dựng lại" cancelText="Huỷ" onConfirm={rebuild}>
          <Button icon={<ReloadOutlined />} loading={busy}>Dựng lại nội dung</Button></Popconfirm>
      </Card>
    </div>
  )
}
