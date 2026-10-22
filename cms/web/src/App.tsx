import { useEffect, useState } from 'react'
import { Alert, Avatar, Button, Drawer, Grid, Input, Layout, Menu, Popover, Select, Space } from 'antd'
import type { MenuProps } from 'antd'
import { AuditOutlined, CloudDownloadOutlined, DashboardOutlined, ExportOutlined, FileSearchOutlined, HeartOutlined, MenuOutlined, RobotOutlined,
  SettingOutlined, SyncOutlined } from '@ant-design/icons'
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

/** Định tuyến bằng hash: #/ · #/p/H32/<trang> · #/health · #/audit */
export function useRoute() {
  const [h, setH] = useState(window.location.hash.slice(1) || '/')
  useEffect(() => { const f = () => setH(window.location.hash.slice(1) || '/'); window.addEventListener('hashchange', f); return () => window.removeEventListener('hashchange', f) }, [])
  const m = h.match(/^\/p\/(H\d{2})\/(\w+)/)
  return m ? { page: m[2], code: m[1] } : { page: h.replace(/^\//, '') || 'home', code: '' }
}
export const go = (path: string) => { window.location.hash = path }

const PROVINCE_PAGES = ['list', 'data', 'training', 'sync', 'export', 'settings']
const initials = (s: string) => s.split(/\s+/).filter(Boolean).slice(-2).map((w) => w[0]).join('').toUpperCase()

/** Người thao tác: chưa có tên -> ô nhập ngay trên thanh đầu; đã có -> chip gọn, bấm để đổi. */
function Actor({ actor, onChange }: { actor: string; onChange: (v: string) => void }) {
  const [draft, setDraft] = useState(actor)
  const [open, setOpen] = useState(false)
  useEffect(() => setDraft(actor), [actor])
  const save = () => { const v = draft.trim(); if (v) { onChange(v); setOpen(false) } }
  const field = <Space.Compact>
    <Input aria-label="Người thao tác" placeholder="Tên người thao tác" style={{ width: 200 }} value={draft} onChange={(e) => setDraft(e.target.value)}
      onPressEnter={save} status={actor ? undefined : 'warning'} autoFocus={open} maxLength={80} />
    <Button type="primary" disabled={!draft.trim() || draft.trim() === actor} onClick={save}>Lưu</Button>
  </Space.Compact>
  if (!actor) return field
  return (
    <Popover trigger="click" open={open} onOpenChange={setOpen} placement="bottomRight" title="Người thao tác" content={field}>
      <button type="button" className="actor-chip" aria-label={`Người thao tác: ${actor} – bấm để đổi`}>
        <Avatar size={26} style={{ background: '#0b5cad', fontSize: 11 }}>{initials(actor)}</Avatar><span className="name">{actor}</span>
      </button>
    </Popover>
  )
}

export default function App() {
  const r = useRoute()
  const screens = Grid.useBreakpoint()
  const wide = screens.lg !== false
  const [provs, setProvs] = useState<Province[]>([])
  const [actor, setActor] = useState(actorStore.get())
  const [lastCode, setLastCode] = useState(r.code || 'H32')
  const [navOpen, setNavOpen] = useState(false)
  useEffect(() => { api.provinces().then((x) => setProvs(x.provinces)).catch(() => {}) }, [r.page])
  useEffect(() => { if (r.code) setLastCode(r.code) }, [r.code])
  useEffect(() => setNavOpen(false), [r.page, r.code])
  const code = r.code || lastCode
  const cur = provs.find((p) => p.code === code)
  const items: MenuProps['items'] = [
    { key: 'home', icon: <DashboardOutlined />, label: 'Tổng quan' },
    { type: 'group', label: cur ? cur.display : code, children: [
      { key: 'list', icon: <FileSearchOutlined />, label: 'Thủ tục hành chính' },
      { key: 'training', icon: <RobotOutlined />, label: 'Train bot' },
      { key: 'sync', icon: <SyncOutlined />, label: 'Đồng bộ & lịch' },
      { key: 'data', icon: <CloudDownloadOutlined />, label: 'Dữ liệu nguồn' },
      { key: 'export', icon: <ExportOutlined />, label: 'Xuất Excel callbot' },
      { key: 'settings', icon: <SettingOutlined />, label: 'Cấu hình tỉnh' },
    ] },
    { type: 'group', label: 'Hệ thống', children: [
      { key: 'health', icon: <HeartOutlined />, label: 'Sức khoẻ nguồn' },
      { key: 'audit', icon: <AuditOutlined />, label: 'Nhật ký' },
    ] },
  ]
  const nav = (k: string) => go(['home', 'health', 'audit'].includes(k) ? `/${k === 'home' ? '' : k}` : `/p/${code}/${k}`)
  const brand = <div className="app-brand"><div className="app-brand-mark" aria-hidden>TTHC</div>
    <div><div className="app-brand-name">CMS Callbot</div><div className="app-brand-sub">Dữ liệu thủ tục hành chính</div></div></div>
  const menu = <Menu mode="inline" selectedKeys={[r.page]} items={items} onClick={(e) => nav(e.key)} style={{ borderInlineEnd: 0 }} />
  const saveActor = (v: string) => { actorStore.set(v); setActor(v) }
  return (
    <Layout style={{ minHeight: '100vh' }}>
      {wide && <Layout.Sider width={240} className="app-sider">{brand}<nav aria-label="Điều hướng chính">{menu}</nav></Layout.Sider>}
      {!wide && <Drawer open={navOpen} onClose={() => setNavOpen(false)} placement="left" width={272} styles={{ body: { padding: 0 } }} title={null} closable={false}>
        {brand}<nav aria-label="Điều hướng chính">{menu}</nav></Drawer>}
      <Layout>
        <Layout.Header className="app-header" style={{ paddingInline: wide ? 24 : 12 }}>
          {!wide && <Button type="text" icon={<MenuOutlined />} aria-label="Mở menu" onClick={() => setNavOpen(true)} />}
          <Select aria-label="Tỉnh / thành" showSearch optionFilterProp="label" style={{ width: wide ? 280 : '100%', maxWidth: 280, minWidth: 0 }} value={code}
            onChange={(v) => go(`/p/${v}/${PROVINCE_PAGES.includes(r.page) ? r.page : 'list'}`)} popupMatchSelectWidth={false}
            options={provs.map((p) => ({ value: p.code, label: `${p.display} (${p.code})${p.stats ? '' : ' · chưa có dữ liệu'}` }))} />
          <span className="grow" />
          <Actor actor={actor} onChange={saveActor} />
        </Layout.Header>
        <Layout.Content className="app-content">
          {!actor && <Alert type="warning" showIcon style={{ marginBottom: 16 }}
            message="Nhập tên người thao tác ở góc phải – mọi thao tác ghi (nhập, sửa, duyệt, xuất, train) cần tên để ghi nhật ký." />}
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
