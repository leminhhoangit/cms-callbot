import { useEffect, useState } from 'react'
import { Alert, Button, Card, Col, Empty, Progress, Row, Skeleton, Space, Statistic, Tag, Typography } from 'antd'
import { api, fmtAt, fmtNum, type Province } from '../api'
import { go } from '../App'

/** Tổng quan – mỗi tỉnh đã có dữ liệu một thẻ: quy mô, mức độ biên tập câu hỏi, tiến độ duyệt, lần nhập gần nhất. */
export default function Home() {
  const [d, setD] = useState<Province[] | null>(null)
  const [err, setErr] = useState('')
  useEffect(() => { api.provinces().then((x) => setD(x.provinces)).catch((e) => setErr((e as Error).message)) }, [])
  if (err) return <Alert type="error" showIcon message={err} />
  if (!d) return <Skeleton active />
  const withData = d.filter((p) => p.stats)
  const sum = (k: 'procedures' | 'rows' | 'need_review' | 'approved') => withData.reduce((a, p) => a + (p.stats?.[k] ?? 0), 0)
  return (
    <div data-testid="home">
      <Typography.Title level={4} style={{ marginTop: 0 }}>Tổng quan</Typography.Title>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><Card><Statistic title="Tỉnh / thành có dữ liệu" value={withData.length} suffix={`/ ${d.length}`} /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="Thủ tục hành chính" value={sum('procedures')} groupSeparator="." /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="Dòng dữ liệu callbot" value={sum('rows')} groupSeparator="." /></Card></Col>
        <Col xs={12} md={6}><Card><Statistic title="Thủ tục đã duyệt" value={sum('approved')} groupSeparator="." suffix={<span style={{ fontSize: 14 }}>/ {fmtNum(sum('procedures'))}</span>} /></Card></Col>
      </Row>
      {!withData.length && <Card><Empty description="Chưa nhập dữ liệu tỉnh nào – chọn tỉnh ở thanh trên → Dữ liệu nguồn" /></Card>}
      <Row gutter={[16, 16]}>
        {withData.map((p) => { const s = p.stats!
          const pct = s.procedures ? Math.round((100 * s.approved) / s.procedures) : 0
          return (
            <Col xs={24} lg={12} key={p.code}>
              <Card title={<Space>{p.display}<Tag bordered={false}>{p.code}</Tag></Space>}
                extra={<Space><Button type="primary" onClick={() => go(`/p/${p.code}/list`)}>Mở</Button><Button onClick={() => go(`/p/${p.code}/export`)}>Xuất Excel</Button></Space>}>
                <Row gutter={16}>
                  <Col span={8}><Statistic title="Thủ tục" value={s.procedures ?? 0} groupSeparator="." /></Col>
                  <Col span={8}><Statistic title="Dòng callbot" value={s.rows ?? 0} groupSeparator="." /></Col>
                  <Col span={8}><Statistic title="Dòng có câu hỏi" value={s.questions_pct ?? 0} suffix="%" /></Col>
                </Row>
                <div style={{ marginTop: 12 }}>
                  <Typography.Text type="secondary">Tiến độ duyệt nội dung</Typography.Text>
                  <Progress percent={pct} format={() => `${fmtNum(s.approved)} / ${fmtNum(s.procedures)}`} />
                </div>
                <Space wrap>
                  <Tag color="orange">Cần duyệt {fmtNum(s.need_review)}</Tag><Tag color="green">Đã duyệt {fmtNum(s.approved)}</Tag>
                  {s.removed > 0 && <Tag color="red">Đã gỡ khỏi cổng {s.removed}</Tag>}
                  {!!p.auto && <Tag color="gold">Địa chỉ tiếp nhận đang là câu chung</Tag>}
                </Space>
                {s.last_import && <div style={{ marginTop: 8 }}><Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Nhập gần nhất {fmtAt(s.last_import.at)} · {s.last_import.source} · Mới {s.last_import.added}, Thay đổi {s.last_import.changed}, Đã gỡ {s.last_import.removed}</Typography.Text></div>}
              </Card>
            </Col>) })}
      </Row>
    </div>
  )
}
