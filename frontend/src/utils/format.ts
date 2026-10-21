import dayjs from 'dayjs'

/** 秒 → mm:ss（超过 1 小时显示 hh:mm:ss） */
export function formatSeconds(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '--:--'
  const total = Math.floor(seconds)
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  const pad = (value: number) => String(value).padStart(2, '0')
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`
}

/** ISO 时间 → 本地时间 "YYYY-MM-DD HH:mm"，无效时返回占位 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const parsed = dayjs(iso)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD HH:mm') : '—'
}

/** datetime-local 选择器的值（如 2026-10-17T09:00）→ 带本地时区的 ISO8601 */
export function localDateTimeToIso(value: string): string {
  const parsed = dayjs(value)
  return parsed.isValid() ? parsed.format('YYYY-MM-DDTHH:mm:ssZ') : ''
}

/** 百分制分数展示，非法值显示占位 */
export function formatScore(score: number | null | undefined): string {
  return typeof score === 'number' && Number.isFinite(score) ? score.toFixed(1) : '—'
}
