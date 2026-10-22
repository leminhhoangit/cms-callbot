import { useEffect, useState } from 'react'
import { Alert, Button, Card, Skeleton, Table } from 'antd'
import { CheckCircleFilled, CloseCircleFilled, ReloadOutlined } from '@ant-design/icons'
import { api, type Health as H } from '../api'
import { PageHeader } from '../ui'

/** Sức khoẻ nguồn – gọi thử các API của Cổng DVC (mỗi API 1 lần, 1 bản ghi). */
export default function Health() {
  const [d, setD] = useState<H[] | null>(null)
  const [err, setErr] = useState('')
  const load = () => { setD(null); setErr(''); api.health().then((r) => setD(r.checks)).catch((e) => setErr((e as Error).message)) }
  useEffect(load, [])
  const bad = d?.filter((x) => !x.ok).length ?? 0
  return (
    <div data-testid="health">
      <PageHeader title="Sức khoẻ nguồn" description="Gọi thử các API của Cổng Dịch vụ công Quốc gia (mỗi API một lần, một bản ghi)."
        actions={<Button icon={<ReloadOutlined />} onClick={load} loading={!d && !err}>Kiểm tra lại</Button>} />
      {err && <Alert type="error" showIcon message="Không kiểm tra được" description={err} />}
      {!d && !err && <Skeleton active />}
      {d && <>
        <Alert type={bad ? 'error' : 'success'} showIcon style={{ marginBottom: 16 }}
          message={bad ? `${bad} API lỗi – sửa script thu thập trước khi chạy` : 'Cổng hoạt động bình thường'} />
        <Card styles={{ body: { padding: 0 } }}>
          <Table<H> rowKey="name" pagination={false} dataSource={d} columns={[
            { title: 'API', dataIndex: 'name', width: 200 },
            { title: 'Kết quả', key: 'ok', render: (_, h) => h.ok ? <span style={{ color: 'var(--c-success)' }}><CheckCircleFilled /> OK</span>
              : <span style={{ color: 'var(--c-error)' }}><CloseCircleFilled /> {h.detail}</span> },
            { title: 'Thời gian', dataIndex: 'ms', width: 110, align: 'right', render: (v: number) => <span className="num">{v} ms</span> },
          ]} />
        </Card>
        <p className="small muted" style={{ marginTop: 12 }}>Cổng từng đổi API không báo trước (10/2026). CMS tự kiểm tra trước mỗi lần thu thập và dừng nếu lỗi.</p>
      </>}
    </div>
  )
}
