import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App as AntApp, ConfigProvider } from 'antd'
import viVN from 'antd/locale/vi_VN'
import App from './App'
import './theme.css'

// Font hệ thống (Segoe UI trên Windows hiển thị tiếng Việt tốt, không tải font ngoài – CMS chạy được trong mạng nội bộ).
const FONT = '"Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={viVN} theme={{
      token: { colorPrimary: '#0b5cad', colorInfo: '#0b5cad', colorSuccess: '#2f7d3b', colorWarning: '#a86400', colorError: '#c0362c',
        colorTextBase: '#1d2733', colorBgLayout: '#f4f6f8', colorBorder: '#d5dbe2', colorBorderSecondary: '#e3e7ec',
        borderRadius: 6, fontFamily: FONT, fontSize: 14, controlHeight: 34, motionDurationMid: '0.18s' },
      components: {
        Layout: { headerBg: '#ffffff', siderBg: '#ffffff', headerHeight: 56, headerPadding: '0 24px' },
        Menu: { itemHeight: 36, itemBorderRadius: 6, itemSelectedBg: '#e8f0fa', itemSelectedColor: '#0b5cad', itemMarginInline: 12,
          groupTitleFontSize: 11, itemColor: '#3b4655' },
        Card: { headerFontSize: 15, headerHeight: 48, paddingLG: 20 },
        Table: { headerBg: '#f7f8fa', headerColor: '#4a5563', rowHoverBg: '#f5f8fc', cellPaddingBlock: 10, headerSplitColor: 'transparent' },
        Tag: { defaultBg: '#f0f2f5' },
        Drawer: { paddingLG: 20 },
      },
    }}>
      <AntApp><App /></AntApp>
    </ConfigProvider>
  </StrictMode>,
)
