import { useEffect, useState } from 'react'
import { Alert, Button, Card, Result, Skeleton, Table, Tag, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { api, type Health as H } from '../api'

/** Sức khoẻ nguồn – gọi thử các API của Cổng DVCQG (mỗi API 1 lần, 1 bản ghi). */
export default function Health() {
  const [d, setD] = useState<H[] | null>(null)
  const [err, setErr] = useState('')
  const load = () => { setD(null); api.health().then((r) => setD(r.checks)).catch((e) => setErr((e as Error).message)) }
  useEffect(load, [])
  if (err) return <Alert type="error" showIcon message={err} />
  const bad = d?.filter((x) => !x.ok).length ?? 0
  return (
    <Card title="Sức khoẻ nguồn – Cổng Dịch vụ công Quốc gia" extra={<Button icon={<ReloadOutlined />} onClick={load}>Kiểm tra lại</Button>} data-testid="health">
      {!d ? <Skeleton active /> : <>
        <Result style={{ padding: 16 }} status={bad ? 'error' : 'success'} title={bad ? `${bad} API lỗi – sửa script thu thập trước khi chạy` : 'Cổng hoạt động bình thường'} />
        <Table<H> rowKey="name" size="small" pagination={false} dataSource={d} columns={[
          { title: 'API', dataIndex: 'name' },
          { title: 'Kết quả', key: 'ok', render: (_, h) => h.ok ? <Tag color="green">OK</Tag> : <><Tag color="red">LỖI</Tag> {h.detail}</> },
          { title: 'Thời gian', dataIndex: 'ms', render: (v: number) => `${v} ms`, width: 110 },
        ]} />
        <Typography.Paragraph type="secondary" style={{ marginTop: 12 }}>Cổng từng đổi API không báo trước (10/2026). CMS tự kiểm tra trước mỗi lần thu thập và dừng nếu lỗi.</Typography.Paragraph>
      </>}
    </Card>
  )
}
