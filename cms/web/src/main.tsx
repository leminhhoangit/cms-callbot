import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App as AntApp, ConfigProvider } from 'antd'
import viVN from 'antd/locale/vi_VN'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={viVN} theme={{ token: { colorPrimary: '#0b5cad', borderRadius: 6, fontFamily: 'system-ui, "Segoe UI", Roboto, sans-serif' } }}>
      <AntApp><App /></AntApp>
    </ConfigProvider>
  </StrictMode>,
)
