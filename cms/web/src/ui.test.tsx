import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { App as AntApp } from 'antd'
import { beforeEach, expect, test, vi } from 'vitest'
import { fieldOf } from './ui'
import Sync from './pages/Sync'

test('fieldOf: tên trường thay vì tiêu đề lặp tên thủ tục', () => {
  const name = 'Cấp bản sao Giấy khai sinh'
  expect(fieldOf(`Địa chỉ tiếp nhận ${name} của Tỉnh Khánh Hòa`, name)).toBe('Địa chỉ tiếp nhận')
  expect(fieldOf(`Căn cứ pháp lý ${name} của Tỉnh Khánh Hòa (tiếp theo 1)`, name)).toBe('Căn cứ pháp lý (tiếp theo 1)')
  expect(fieldOf('Tiêu đề không chứa tên', name)).toBe('Tiêu đề không chứa tên')
})

const json = (b: unknown) => Promise.resolve(new Response(JSON.stringify(b), { status: 200, headers: { 'Content-Type': 'application/json' } }))
let puts: unknown[] = []
const CFG = { province: 'H32', mode: 'MANUAL', scope: 'TRAIN_ONLY', freq: 'MONTHLY', at_time: '08:00', weekday: 0, monthday: 1, next_run_at: null,
  updated_by: null, updated_at: null, mode_vi: 'Chạy tay', scope_vi: '', freq_vi: 'Hằng tháng' }
beforeEach(() => {
  puts = []
  localStorage.setItem('cms.actor', 'QA')
  globalThis.fetch = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === 'PUT') { puts.push(JSON.parse(String(init.body))); return json({ ...CFG, mode: 'SCHEDULE', next_run_at: '2026-11-01T08:00:00' }) }
    return json({ config: CFG, runs: [], scopes: {}, freqs: { DAILY: 'Hằng ngày', WEEKLY: 'Hằng tuần', MONTHLY: 'Hằng tháng' } })
  }) as unknown as typeof fetch
})

test('Đồng bộ: chuyển sang Theo lịch mới hiện tần suất / giờ; Lưu chỉ bật khi có thay đổi', async () => {
  render(<AntApp><Sync code="H32" /></AntApp>)
  const save = await screen.findByRole('button', { name: /Lưu cấu hình/ })
  expect(save).toBeDisabled()
  expect(screen.queryByLabelText('Giờ')).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('Theo lịch'))
  expect(await screen.findByLabelText('Giờ')).toBeInTheDocument()
  expect(save).toBeEnabled()
  fireEvent.click(save)
  await waitFor(() => expect(puts).toHaveLength(1))
  expect(puts[0]).toMatchObject({ mode: 'SCHEDULE', freq: 'MONTHLY', at_time: '08:00' })
})
