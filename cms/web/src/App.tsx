import { useEffect, useState } from 'react'
import { Button, Input, Layout, Menu, Select, Space, Typography } from 'antd'
import { AuditOutlined, CloudDownloadOutlined, DashboardOutlined, ExportOutlined, FileSearchOutlined, HeartOutlined, RobotOutlined, SettingOutlined, SyncOutlined, UserOutlined } from '@ant-design/icons'
import { actorStore, api, type Province } from './api'
import Home from './pages/Home'
import Procedures from './pages/Procedures'
import DataSource from './pages/DataSource'
import Exports from './pages/Exports'
import Settings from './pages/Settings'
import Health from './pages/Health'
import AuditLog from './pages/AuditLog'
import Training from './pages/Training'
import Sync from './pages/Sync'

/** Định tuyến bằng hash: #/ · #/p/H32/list · #/p/H32/data · #/p/H32/export · #/p/H32/settings · #/health · #/audit */
export function useRoute() {
  const [h, setH] = useState(window.location.hash.slice(1) || '/')
  useEffect(() => { const f = () => setH(window.location.hash.slice(1) || '/'); window.addEventListener('hashchange', f); return () => window.removeEventListener('hashchange', f) }, [])
  const m = h.match(/^\/p\/(H\d{2})\/(\w+)/)
  return m ? { page: m[2], code: m[1] } : { page: h.replace(/^\//, '') || 'home', code: '' }
}
export const go = (path: string) => { window.location.hash = path }

export default function App() {
  const r = useRoute()
  const [provs, setProvs] = useState<Province[]>([])
  const [actor, setActor] = useState(actorStore.get())
  const [draft, setDraft] = useState(actor)
  const [lastCode, setLastCode] = useState(r.code || 'H32')
  useEffect(() => { api.provinces().then((x) => setProvs(x.provinces)).catch(() => {}) }, [r.page])
  useEffect(() => { if (r.code) setLastCode(r.code) }, [r.code])
  const code = r.code || lastCode
  const sel = r.code ? r.page : r.page
  const items = [
    { key: 'home', icon: <DashboardOutlined />, label: 'Tổng quan' },
    { type: 'group' as const, label: provs.find((p) => p.code === code)?.display ?? code, children: [
      { key: 'list', icon: <FileSearchOutlined />, label: 'Thủ tục hành chính' },
      { key: 'data', icon: <CloudDownloadOutlined />, label: 'Dữ liệu nguồn' },
      { key: 'training', icon: <RobotOutlined />, label: 'Train bot' },
      { key: 'sync', icon: <SyncOutlined />, label: 'Đồng bộ & lịch' },
      { key: 'export', icon: <ExportOutlined />, label: 'Xuất Excel callbot' },
      { key: 'settings', icon: <SettingOutlined />, label: 'Cấu hình tỉnh' },
    ] },
    { type: 'group' as const, label: 'Hệ thống', children: [
      { key: 'health', icon: <HeartOutlined />, label: 'Sức khoẻ nguồn' },
      { key: 'audit', icon: <AuditOutlined />, label: 'Nhật ký' },
    ] },
  ]
  const nav = (k: string) => go(['home', 'health', 'audit'].includes(k) ? `/${k === 'home' ? '' : k}` : `/p/${code}/${k}`)
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Layout.Sider width={232} theme="light" breakpoint="lg" collapsedWidth={0} style={{ borderRight: '1px solid #f0f0f0' }}>
        <div style={{ padding: '16px 18px', fontWeight: 700, color: '#0b3d6e', lineHeight: 1.3 }}>CMS dữ liệu<br />Callbot TTHC</div>
        <Menu mode="inline" selectedKeys={[sel]} items={items} onClick={(e) => nav(e.key)} style={{ borderInlineEnd: 0 }} />
      </Layout.Sider>
      <Layout>
        <Layout.Header style={{ background: '#fff', padding: '0 20px', display: 'flex', alignItems: 'center', gap: 12, borderBottom: '1px solid #f0f0f0' }}>
          <Select aria-label="Tỉnh / thành" showSearch optionFilterProp="label" style={{ width: 260 }} value={code}
            onChange={(v) => go(`/p/${v}/${['list', 'data', 'training', 'sync', 'export', 'settings'].includes(r.page) ? r.page : 'list'}`)}
            options={provs.map((p) => ({ value: p.code, label: `${p.display} (${p.code})${p.stats ? '' : ' – chưa có dữ liệu'}` }))} />
          <span style={{ flex: 1 }} />
          <Space>
            <UserOutlined aria-hidden />
            <Input aria-label="Người thao tác" placeholder="Tên người thao tác" style={{ width: 200 }} value={draft} onChange={(e) => setDraft(e.target.value)}
              onPressEnter={() => { actorStore.set(draft.trim()); setActor(draft.trim()) }} status={actor ? undefined : 'warning'} />
            <Button disabled={draft.trim() === actor} onClick={() => { actorStore.set(draft.trim()); setActor(draft.trim()) }}>Lưu</Button>
          </Space>
        </Layout.Header>
        <Layout.Content style={{ padding: 20, background: '#f5f7fa' }}>
          {!actor && <Typography.Paragraph type="warning" style={{ marginBottom: 12 }}>Nhập tên người thao tác (góc phải) – mọi thao tác ghi (nhập, sửa, duyệt, xuất) cần tên để ghi nhật ký.</Typography.Paragraph>}
          {r.page === 'home' && <Home />}
          {r.page === 'list' && <Procedures code={code} key={code} />}
          {r.page === 'data' && <DataSource code={code} key={code} />}
          {r.page === 'training' && <Training code={code} key={code} />}
          {r.page === 'sync' && <Sync code={code} key={code} />}
          {r.page === 'export' && <Exports code={code} key={code} />}
          {r.page === 'settings' && <Settings code={code} key={code} />}
          {r.page === 'health' && <Health />}
          {r.page === 'audit' && <AuditLog />}
        </Layout.Content>
      </Layout>
    </Layout>
  )
}
