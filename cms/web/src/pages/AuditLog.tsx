import { useEffect, useState } from 'react'
import { Alert, Card, Table } from 'antd'
import { api, fmtAt, type Audit } from '../api'
import { PageHeader } from '../ui'

const ACTION: Record<string, string> = { import: 'Nạp dữ liệu', rebuild: 'Dựng lại', edit: 'Sửa câu hỏi / tags', approve: 'Duyệt', unapprove: 'Bỏ duyệt',
  export: 'Xuất Excel', province_update: 'Sửa cấu hình tỉnh', train_batch_create: 'Tạo lô train', train_submit: 'Gửi train', train_cancel: 'Huỷ lô train',
  train_succeeded: 'Train xong', train_failed: 'Train lỗi', sync_config: 'Cấu hình đồng bộ', sync_run: 'Lượt đồng bộ' }

/** Nhật ký – mọi thao tác ghi: ai, lúc nào, làm gì. */
export default function AuditLog() {
  const [d, setD] = useState<Audit[] | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.audit().then((r) => setD(r.rows)).catch((e) => setErr((e as Error).message)) }, [])
  return (
    <div data-testid="audit">
      <PageHeader title="Nhật ký" description="Mọi thao tác ghi dữ liệu: ai, lúc nào, làm gì (300 dòng gần nhất)." />
      {err && <Alert type="error" showIcon message="Không tải được nhật ký" description={err} style={{ marginBottom: 16 }} />}
      <Card styles={{ body: { padding: 0 } }}>
        <Table<Audit> rowKey="id" size="small" loading={!d && !err} dataSource={d ?? []} pagination={{ pageSize: 50, hideOnSinglePage: true }} scroll={{ x: 820 }}
          locale={{ emptyText: 'Chưa có thao tác' }} columns={[
          { title: 'Lúc', dataIndex: 'at', width: 140, render: (v: string) => <span className="num">{fmtAt(v)}</span> },
          { title: 'Người', dataIndex: 'actor', width: 140 },
          { title: 'Thao tác', dataIndex: 'action', width: 170, render: (v: string) => ACTION[v] ?? v,
            filters: Object.entries(ACTION).map(([k, v]) => ({ text: v, value: k })), onFilter: (v, r) => r.action === v },
          { title: 'Tỉnh', dataIndex: 'province', width: 70, render: (v: string | null) => <span className="mono">{v ?? ''}</span> },
          { title: 'Chi tiết', dataIndex: 'detail', render: (v: string) => <span className="small">{v}</span> },
        ]} />
      </Card>
    </div>
  )
}
