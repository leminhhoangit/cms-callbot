import { useEffect, useState } from 'react'
import { Alert, Card, Table, Tag } from 'antd'
import { api, fmtAt, type Audit } from '../api'

const ACTION: Record<string, string> = { import: 'Nhập dữ liệu', rebuild: 'Dựng lại', edit: 'Sửa câu hỏi / tags', approve: 'Duyệt', unapprove: 'Bỏ duyệt',
  export: 'Xuất Excel', province_update: 'Sửa cấu hình tỉnh' }

/** Nhật ký – mọi thao tác ghi: ai, lúc nào, làm gì. */
export default function AuditLog() {
  const [d, setD] = useState<Audit[] | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.audit().then((r) => setD(r.rows)).catch((e) => setErr((e as Error).message)) }, [])
  if (err) return <Alert type="error" showIcon message={err} />
  return (
    <Card title="Nhật ký thao tác" data-testid="audit">
      <Table<Audit> rowKey="id" size="small" loading={!d} dataSource={d ?? []} pagination={{ pageSize: 50 }} columns={[
        { title: 'Lúc', dataIndex: 'at', render: fmtAt, width: 140 }, { title: 'Người', dataIndex: 'actor', width: 140 },
        { title: 'Thao tác', dataIndex: 'action', width: 150, render: (v: string) => <Tag>{ACTION[v] ?? v}</Tag>,
          filters: Object.entries(ACTION).map(([k, v]) => ({ text: v, value: k })), onFilter: (v, r) => r.action === v },
        { title: 'Tỉnh', dataIndex: 'province', width: 70 }, { title: 'Chi tiết', dataIndex: 'detail' },
      ]} />
    </Card>
  )
}
