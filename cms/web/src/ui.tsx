// Thành phần giao diện dùng chung – tiêu đề trang, dải số liệu, nhãn trạng thái. Mỗi trạng thái chỉ có MỘT cách hiển thị trong toàn ứng dụng.
import type { ReactNode } from 'react'
import { Tag, Tooltip } from 'antd'

export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div>
        <h1>{title}</h1>
        {description && <p className="desc">{description}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  )
}

export type StatItem = { label: string; value: ReactNode; suffix?: ReactNode; hint?: ReactNode; tone?: 'warning' | 'success' | 'error' | 'primary' }

export function StatStrip({ items, label }: { items: StatItem[]; label: string }) {
  return (
    <section className="stat-strip" aria-label={label}>
      {items.map((s) => (
        <div key={s.label} className={`stat${s.tone ? ` tone-${s.tone}` : ''}`}>
          <div className="label" title={s.label}>{s.label}</div>
          <div className="value">{s.value}{s.suffix && <small>{s.suffix}</small>}</div>
          {s.hint && <div className="hint">{s.hint}</div>}
        </div>
      ))}
    </section>
  )
}

export const n = (v: number | null | undefined) => (typeof v === 'number' ? v.toLocaleString('vi-VN') : '—')

// ---------------------------------------------------------------- trạng thái (màu theo nghĩa, không trang trí)
type Def = { vi: string; color: string }
const tag = (defs: Record<string, Def>) => ({ value, title }: { value: string; title?: string }) => {
  const d = defs[value] ?? { vi: value, color: 'default' }
  const t = <Tag color={d.color} bordered={false} style={{ marginInlineEnd: 0 }}>{d.vi}</Tag>
  return title ? <Tooltip title={title}>{t}</Tooltip> : t
}

export const CHANGE: Record<string, Def> = { NEW: { vi: 'Mới', color: 'blue' }, CHANGED: { vi: 'Thay đổi', color: 'orange' }, SAME: { vi: 'Không đổi', color: 'default' },
  REMOVED: { vi: 'Đã gỡ khỏi cổng', color: 'red' } }
export const REVIEW: Record<string, Def> = { NEED_REVIEW: { vi: 'Cần duyệt', color: 'gold' }, APPROVED: { vi: 'Đã duyệt', color: 'green' } }
export const TRAIN: Record<string, Def> = { DRAFT: { vi: 'Chờ gửi', color: 'default' }, SUBMITTED: { vi: 'Đã gửi', color: 'blue' }, QUEUED: { vi: 'Xếp hàng', color: 'cyan' },
  TRAINING: { vi: 'Đang train', color: 'processing' }, SUCCEEDED: { vi: 'Train xong', color: 'green' }, FAILED: { vi: 'Lỗi', color: 'red' },
  CANCELLED: { vi: 'Đã huỷ', color: 'default' } }
export const RUN: Record<string, Def> = { RUNNING: { vi: 'Đang chạy', color: 'processing' }, SUCCEEDED: { vi: 'Thành công', color: 'green' },
  NO_CHANGE: { vi: 'Không có gì cần train', color: 'default' }, SKIPPED: { vi: 'Bỏ qua', color: 'gold' }, FAILED: { vi: 'Lỗi', color: 'red' } }
export const JOB: Record<string, Def> = { RUNNING: { vi: 'Đang chạy', color: 'processing' }, SUCCEEDED: { vi: 'Xong', color: 'green' }, FAILED: { vi: 'Lỗi', color: 'red' } }

export const ChangeTag = tag(CHANGE)
export const ReviewTag = tag(REVIEW)
export const TrainTag = tag(TRAIN)
export const RunTag = tag(RUN)
export const JobTag = tag(JOB)

/** "Địa chỉ tiếp nhận Cấp bản sao … của Tỉnh Khánh Hòa" -> "Địa chỉ tiếp nhận" (tên trường của dòng nội dung). */
export function fieldOf(title: string, name: string) {
  const i = name ? title.indexOf(name) : -1
  const f = (i > 0 ? title.slice(0, i) : title).replace(/\s*\(tiếp theo \d+\)\s*$/, '').trim()
  const cont = /\(tiếp theo (\d+)\)$/.exec(title)
  return cont ? `${f} (tiếp theo ${cont[1]})` : f
}
