import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type {
  ActionResult,
  ClassifyCoverageRow,
  CoverageHistoryRow,
  CoverageRow,
  EntryRow,
  OverviewResult,
  PageResult,
  RollbackResult,
} from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

/** 回滚预览：服务端比较当前与目标版本的资源覆盖，生成回滚差异单 */
export async function previewRollback(policyId: number, targetVersion?: string): Promise<RollbackResult> {
  const response = await request(`/api/deploy_policy/${policyId}/rollback/preview`, {
    method: 'POST',
    body: JSON.stringify({ 目标版本: targetVersion ?? null }),
  })
  return await response.json()
}

/** 回滚确认：执行差异单并返回按节点区分的执行回执，可重试 */
export async function confirmRollback(policyId: number, ticketId: number): Promise<RollbackResult> {
  const response = await request(`/api/deploy_policy/${policyId}/rollback/confirm`, {
    method: 'POST',
    body: JSON.stringify({ ticket_id: ticketId }),
  })
  return await response.json()
}

/** 策略下发的当前覆盖（节点此刻真实可见的资源） */
export async function listDeployCoverage(policyId: number): Promise<CoverageRow[]> {
  const response = await request(`/api/deploy_policy/${policyId}/coverage`)
  if (!response.ok) throw new Error('当前覆盖读取失败')
  return (await response.json()).items
}

/** 历史下发的覆盖记录（每次版本下发的 节点×资源 快照） */
export async function listDeployCoverageHistory(policyId: number): Promise<CoverageHistoryRow[]> {
  const response = await request(`/api/deploy_policy/${policyId}/coverage/history`)
  if (!response.ok) throw new Error('历史覆盖记录读取失败')
  return (await response.json()).items
}

/** 分级分类视角的当前覆盖：每个数据资源当前在哪些节点真实可见 */
export async function listClassifyCoverage(): Promise<ClassifyCoverageRow[]> {
  const response = await request('/api/classify_tag/coverage')
  if (!response.ok) throw new Error('分级当前覆盖读取失败')
  return (await response.json()).items
}

/** 调整数据资源的安全等级 */
export async function adjustClassifyLevel(tagId: number, level: string): Promise<ActionResult> {
  const response = await request(`/api/classify_tag/${tagId}/level`, {
    method: 'POST',
    body: JSON.stringify({ 安全等级: level }),
  })
  return await response.json()
}
