/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  [field: string]: string | number | boolean
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

/** 回滚差异单条目：一个节点上一个资源的覆盖变更与执行结果 */
export type RollbackItem = {
  节点: string
  资源: string
  变更: string
  下发时安全等级: string
  当前安全等级: string
  预览结论: string
  说明: string
  执行结果: string | null
}

/** 执行回执：每次确认/重试生成一份，按节点区分 恢复/未动/未能恢复 */
export type RollbackReceipt = {
  序号: number
  时间: string
  结论: string
  节点结果: {
    节点: string
    已恢复: { 资源: string; 原因: string }[]
    未动: { 资源: string; 原因: string }[]
    未能恢复: { 资源: string; 原因: string }[]
  }[]
}

/** 回滚差异单 */
export type RollbackTicket = {
  id: number
  policy_id: number
  分发编号: string
  当前版本: string
  目标版本: string
  状态: string
  items: RollbackItem[]
  预览时间: string
  执行时间: string | null
  执行次数: number
  回执列表: RollbackReceipt[]
}

export type RollbackResult = {
  ok: boolean
  message: string
  ticket: RollbackTicket | null
}

/** 策略下发的当前覆盖：节点此刻真实可见的资源 */
export type CoverageRow = {
  id: number
  policy_id: number
  节点: string
  资源: string
  可见: boolean
  来源版本: string
  更新时间: string
}

/** 历史下发的覆盖记录：每次版本下发的 节点×资源 快照 */
export type CoverageHistoryRow = {
  id: number
  policy_id: number
  版本: string
  节点: string
  资源: string
  下发时安全等级: string
  操作: string
  操作时间: string
}

/** 分级分类视角的当前覆盖 */
export type ClassifyCoverageRow = {
  id: number
  标签编号: string
  数据资源: string
  安全等级: string
  status: string
  覆盖节点: string[]
  覆盖节点数: number
}
