import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { App as AntApp } from 'antd'
import { beforeEach, expect, test, vi } from 'vitest'
import Home from './Home'
import Procedures from './Procedures'

const json = (b: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(b), { status, headers: { 'Content-Type': 'application/json' } }))
const STATS = { procedures: 2753, rows: 72875, rows_with_questions: 0, questions_pct: 0, need_review: 2750, approved: 3, removed: 0,
  last_import: { id: 1, province: 'H32', source: 'H32_raw.json.gz', fetched_at: null, at: '2026-10-22T16:17:16', actor: 'Claude (AI)', procedures: 2753, rows: 72875, added: 2753, changed: 0, removed: 0, note: '' } }
const P = { province: 'H32', fid: 'f1', uri: 'https://dichvucong.gov.vn/x', code: '2.000635', name: 'Cấp bản sao Giấy khai sinh', category: 'Hộ tịch', type: 'STANDARD',
  levels: 'Cấp Xã', status: 'ACTIVE', change: 'NEW', review: 'NEED_REVIEW', reviewed_by: null, reviewed_at: null, n_rows: 25, n_q: 0 }
let calls: { url: string; method?: string; body?: any; actor?: string }[] = []

beforeEach(() => {
  calls = []
  localStorage.setItem('cms.actor', 'Lê Minh Hoàng')
  globalThis.fetch = vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : undefined, actor: (init?.headers as Record<string, string>)?.['X-Actor'] })
    if (url === '/api/provinces') return json({ provinces: [{ code: 'H32', display: 'Tỉnh Khánh Hòa', auto: 0, stats: STATS }, { code: 'H05', display: 'Thành phố Bắc Ninh', auto: 1, stats: null }], raws: [], jobs: [] })
    if (url.startsWith('/api/p/H32/procedures')) return json({ total: 1, page: 1, size: 50, items: [P] })
    if (url === '/api/p/H32') return json({ province: { code: 'H32' }, stats: STATS, categories: ['Hộ tịch'] })
    if (url === '/api/p/H32/review-bulk') return json({ approved: 1 })
    return json({ detail: 'x' }, 404)
  }) as unknown as typeof fetch
})

test('Tổng quan: chỉ thẻ tỉnh có dữ liệu, số liệu + tiến độ duyệt', async () => {
  render(<AntApp><Home /></AntApp>)
  expect(await screen.findByText('Tỉnh Khánh Hòa')).toBeInTheDocument()
  expect(screen.queryByText('Thành phố Bắc Ninh')).not.toBeInTheDocument()
  expect(document.body.textContent).toContain("72.875")
  expect(screen.getByText('Cần duyệt 2.750')).toBeInTheDocument()
})

test('Thủ tục: duyệt hàng loạt gửi đúng thủ tục + tên người thao tác', async () => {
  render(<AntApp><Procedures code="H32" /></AntApp>)
  expect(await screen.findByText('Cấp bản sao Giấy khai sinh')).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('checkbox')[1])
  fireEvent.click(screen.getByRole('button', { name: /Duyệt 1 đã chọn/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'Duyệt' }))
  await waitFor(() => expect(calls.some((c) => c.url === '/api/p/H32/review-bulk')).toBe(true))
  const c = calls.find((x) => x.url === '/api/p/H32/review-bulk')!
  expect(c.body).toEqual({ fids: ['f1'] })
  expect(decodeURIComponent(c.actor!)).toBe('Lê Minh Hoàng')
})
