<template>
  <section class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
    </p>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <button
              v-for="action in meta.actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <template v-if="meta.key === 'deploy_policy'">
              <button
                class="link"
                type="button"
                :data-testid="`rollback-preview-${row.id}`"
                @click="openRollbackPreview(row)"
              >
                回滚预览
              </button>
              <button
                class="link"
                type="button"
                :data-testid="`coverage-${row.id}`"
                @click="loadDeployCoverage(Number(row.id))"
              >
                覆盖记录
              </button>
            </template>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="meta.fields.length + 2" class="empty-state">
            暂无{{ meta.name }}数据，可先登记{{ meta.entity }}
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 策略下发：当前覆盖与历史下发的覆盖记录 -->
    <section v-if="meta.key === 'deploy_policy' && coveragePolicyId !== null" class="coverage-panel" data-testid="deploy-coverage-panel">
      <h3>策略分发 #{{ coveragePolicyId }} 的资源覆盖</h3>
      <div class="coverage-columns">
        <div>
          <h4>当前覆盖（节点真实可见）</h4>
          <table class="data-table" data-testid="current-coverage-table">
            <thead>
              <tr><th>节点</th><th>资源</th><th>可见</th><th>来源版本</th><th>更新时间</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in deployCoverage" :key="item.id">
                <td>{{ item.节点 }}</td>
                <td>{{ item.资源 }}</td>
                <td>{{ item.可见 ? '可见' : '不可见' }}</td>
                <td>{{ item.来源版本 }}</td>
                <td>{{ item.更新时间 }}</td>
              </tr>
              <tr v-if="!deployCoverage.length">
                <td colspan="5" class="empty-state">该策略暂无当前覆盖记录</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div>
          <h4>历史下发的覆盖记录</h4>
          <table class="data-table" data-testid="history-coverage-table">
            <thead>
              <tr><th>版本</th><th>节点</th><th>资源</th><th>下发时安全等级</th><th>操作时间</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in deployHistory" :key="item.id">
                <td>{{ item.版本 }}</td>
                <td>{{ item.节点 }}</td>
                <td>{{ item.资源 }}</td>
                <td>{{ item.下发时安全等级 }}</td>
                <td>{{ item.操作时间 }}</td>
              </tr>
              <tr v-if="!deployHistory.length">
                <td colspan="5" class="empty-state">该策略暂无历史下发记录</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- 分级分类：当前覆盖（只反映真正执行的回滚）与分级调整 -->
    <section v-if="meta.key === 'classify_tag'" class="coverage-panel" data-testid="classify-coverage-panel">
      <h3>分级分类的当前覆盖</h3>
      <p class="page-desc">覆盖节点来自策略下发真正执行的结果；提高安全等级后，回滚不能恢复已失去的可见性。</p>
      <table class="data-table" data-testid="classify-coverage-table">
        <thead>
          <tr><th>标签编号</th><th>数据资源</th><th>安全等级</th><th>覆盖节点</th><th>调整分级</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in classifyCoverage" :key="item.id" :data-testid="`coverage-row-${item.id}`">
            <td>{{ item.标签编号 }}</td>
            <td>{{ item.数据资源 }}</td>
            <td>{{ item.安全等级 }}</td>
            <td>
              <span v-if="item.覆盖节点.length" class="node-chips">
                <span v-for="node in item.覆盖节点" :key="node" class="node-chip">{{ node }}</span>
              </span>
              <span v-else class="muted-text">无节点覆盖</span>
            </td>
            <td class="row-actions">
              <select v-model="levelDraft[item.id]" :data-testid="`level-select-${item.id}`">
                <option v-for="level in levelOptions" :key="level" :value="level">{{ level }}</option>
              </select>
              <button
                class="link"
                type="button"
                :data-testid="`level-adjust-${item.id}`"
                @click="submitLevelAdjust(item.id)"
              >
                调整分级
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <!-- 回滚差异单：预览 → 确认 → 执行回执 -->
    <div v-if="rollbackTicket" class="modal-backdrop" data-testid="rollback-modal">
      <div class="modal rollback-modal">
        <h3>
          回滚差异单 #{{ rollbackTicket.id }}（{{ rollbackTicket.分发编号 }}）
        </h3>
        <p class="page-desc">
          {{ rollbackTicket.当前版本 }} → {{ rollbackTicket.目标版本 }} ｜ 状态：{{ rollbackTicket.状态 }} ｜
          预览时间：{{ rollbackTicket.预览时间 }} ｜ 执行次数：{{ rollbackTicket.执行次数 }}
        </p>
        <table class="data-table" data-testid="rollback-diff-table">
          <thead>
            <tr>
              <th>节点</th><th>资源</th><th>变更</th><th>下发时等级</th><th>当前等级</th>
              <th>预览结论</th><th>执行结果</th><th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in rollbackTicket.items" :key="index">
              <td>{{ item.节点 }}</td>
              <td>{{ item.资源 }}</td>
              <td>{{ item.变更 }}</td>
              <td>{{ item.下发时安全等级 || '—' }}</td>
              <td>{{ item.当前安全等级 }}</td>
              <td :class="{ 'conflict-text': item.预览结论 === '分级冲突' }">{{ item.预览结论 }}</td>
              <td :class="`result-${item.执行结果 ?? '待执行'}`">{{ item.执行结果 ?? '待执行' }}</td>
              <td>{{ item.说明 }}</td>
            </tr>
          </tbody>
        </table>

        <div v-if="rollbackTicket.回执列表.length" class="receipt-list" data-testid="rollback-receipts">
          <h4>执行回执</h4>
          <div v-for="receipt in rollbackTicket.回执列表" :key="receipt.序号" class="receipt-card">
            <p class="receipt-head">第 {{ receipt.序号 }} 次执行 ｜ {{ receipt.时间 }} ｜ 结论：{{ receipt.结论 }}</p>
            <div v-for="node in receipt.节点结果" :key="node.节点" class="receipt-node" :data-testid="`receipt-${receipt.序号}-${node.节点}`">
              <strong>{{ node.节点 }}</strong>
              <span v-if="node.已恢复.length" class="receipt-group ok">
                恢复：{{ node.已恢复.map((r) => r.资源).join('、') }}
              </span>
              <span v-if="node.未动.length" class="receipt-group">
                未动：{{ node.未动.map((r) => `${r.资源}（${r.原因}）`).join('、') }}
              </span>
              <span v-if="node.未能恢复.length" class="receipt-group bad">
                未能恢复：{{ node.未能恢复.map((r) => `${r.资源}（${r.原因}）`).join('、') }}
              </span>
            </div>
          </div>
        </div>

        <div class="page-actions">
          <button class="btn" type="button" @click="closeRollback">关闭</button>
          <button
            class="btn primary"
            data-testid="rollback-confirm"
            type="button"
            :disabled="rollbackBusy"
            @click="confirmRollbackTicket"
          >
            {{ rollbackBusy ? '执行中…' : rollbackTicket.执行次数 > 0 ? '重试回滚' : '确认回滚' }}
          </button>
        </div>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  adjustClassifyLevel,
  confirmRollback,
  createEntry,
  downloadEntries,
  listClassifyCoverage,
  listDeployCoverage,
  listDeployCoverageHistory,
  listEntries,
  moduleMeta,
  previewRollback,
  runAction as applyAction,
} from '@/api/backend-service'
import type {
  ClassifyCoverageRow,
  CoverageHistoryRow,
  CoverageRow,
  EntryRow,
  RollbackTicket,
} from '@/data/types'

const props = defineProps<{ moduleKey: string }>()
const meta = moduleMeta(props.moduleKey)
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = meta.fields.slice(0, 3)
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})

// ——— 策略下发：回滚预览/确认 与 覆盖记录 ———
const rollbackTicket = ref<RollbackTicket | null>(null)
const rollbackPolicyId = ref<number | null>(null)
const rollbackBusy = ref(false)
const coveragePolicyId = ref<number | null>(null)
const deployCoverage = ref<CoverageRow[]>([])
const deployHistory = ref<CoverageHistoryRow[]>([])

// ——— 分级分类：当前覆盖 与 分级调整 ———
const levelOptions = ['未分级', 'L1', 'L2', 'L3', 'L4']
const classifyCoverage = ref<ClassifyCoverageRow[]>([])
const levelDraft = ref<Record<number, string>>({})

const stats = computed(() => [
  { label: meta.metrics[0], value: total.value },
  { label: meta.metrics[1], value: rows.value.filter((row) => row.status === meta.statuses[1]).length },
  {
    label: meta.metrics[2],
    value: rows.value.filter((row) => row.status === meta.statuses[meta.statuses.length - 1]).length,
  },
])
const statusSummary = computed(() =>
  meta.statuses.map((status) => ({
    status,
    count: rows.value.filter((row) => String(row.status) === status).length,
  })),
)

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  try {
    await downloadEntries(meta.key, filters.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(meta.fields.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await createEntry(meta.key, createValues.value)
    if (!result.ok) throw new Error(result.message)
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: EntryRow) {
  errorMessage.value = ''
  try {
    const result = await applyAction(meta.key, Number(row.id), action)
    if (!result.ok) throw new Error(result.message)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

async function openRollbackPreview(row: EntryRow) {
  errorMessage.value = ''
  rollbackBusy.value = true
  try {
    const result = await previewRollback(Number(row.id))
    if (!result.ok || !result.ticket) throw new Error(result.message)
    rollbackTicket.value = result.ticket
    rollbackPolicyId.value = Number(row.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '回滚预览失败'
  } finally {
    rollbackBusy.value = false
  }
}

async function confirmRollbackTicket() {
  if (!rollbackTicket.value || rollbackPolicyId.value === null) return
  errorMessage.value = ''
  rollbackBusy.value = true
  try {
    const result = await confirmRollback(rollbackPolicyId.value, rollbackTicket.value.id)
    if (!result.ok || !result.ticket) throw new Error(result.message)
    rollbackTicket.value = result.ticket
    await reload()
    await loadDeployCoverage(rollbackPolicyId.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '回滚执行失败'
  } finally {
    rollbackBusy.value = false
  }
}

function closeRollback() {
  rollbackTicket.value = null
  rollbackPolicyId.value = null
}

async function loadDeployCoverage(policyId: number) {
  errorMessage.value = ''
  try {
    coveragePolicyId.value = policyId
    deployCoverage.value = await listDeployCoverage(policyId)
    deployHistory.value = await listDeployCoverageHistory(policyId)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '覆盖记录读取失败'
  }
}

async function loadClassifyCoverage() {
  try {
    classifyCoverage.value = await listClassifyCoverage()
    levelDraft.value = Object.fromEntries(
      classifyCoverage.value.map((item) => [item.id, item.安全等级]),
    )
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分级当前覆盖读取失败'
  }
}

async function submitLevelAdjust(tagId: number) {
  errorMessage.value = ''
  try {
    const result = await adjustClassifyLevel(tagId, levelDraft.value[tagId])
    if (!result.ok) throw new Error(result.message)
    await reload()
    await loadClassifyCoverage()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调整分级失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await listEntries(meta.key, filters.value)
    rows.value = payload.items
    total.value = payload.total
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '业务列表读取失败'
  }
}

onMounted(async () => {
  await reload()
  if (meta.key === 'classify_tag') await loadClassifyCoverage()
})
</script>
