<script setup lang="ts">
/**
 * 记忆工作台主组件：组装各区域，集中管理项目/会话/记忆状态。
 * 所有数据来自 Python 服务的 REST API，不内置任何假数据。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  deleteMemory as apiDeleteMemory,
  deleteSession as apiDeleteSession,
  health,
  listMemories,
  projects as apiProjects,
  registerProject,
  remember,
  sessions as apiSessions,
  setToken,
  startSession,
  stats as apiStats,
  updateMemory,
} from './api'
import type { Memory, Project, Session, Stats } from './types'
import HeroSection from './components/HeroSection.vue'
import RecallLab from './components/RecallLab.vue'
import SidePanels from './components/SidePanels.vue'
import MemoryLibrary from './components/MemoryLibrary.vue'

const version = ref('')
const token = ref('')
const activeNamespace = ref<string | null>(null)
const projects = ref<Project[]>([])
const sessions = ref<Session[]>([])
const memories = ref<Memory[]>([])
const stats = ref<Stats>({ total: 0, namespaces: 0, total_accesses: 0 })
const connected = ref(false)
const sessionFilter = ref<{ id: number; title: string } | null>(null)

const memoryCounts = computed<Record<string, number>>(() => {
  const counts: Record<string, number> = {}
  for (const p of projects.value) counts[p.namespace] = 0
  for (const m of memories.value) {
    if (m.namespace) counts[m.namespace] = (counts[m.namespace] || 0) + 1
  }
  return counts
})

const projectName = computed(() => {
  const p = projects.value.find((x) => x.namespace === activeNamespace.value)
  return p ? p.name : activeNamespace.value || '全部项目'
})

// 记忆编辑弹窗
const memDialog = reactive({ visible: false, editing: false, id: 0, content: '', type: 'fact', tags: '' })
// 项目弹窗
const projDialog = reactive({ visible: false, namespace: '', name: '' })

async function loadAll() {
  setToken(token.value)
  try {
    const h = await health()
    connected.value = true
    version.value = h.version
  } catch {
    connected.value = false
    ElMessage.error('无法连接记忆服务')
    return
  }
  await Promise.all([loadProjects(), loadStats(), loadMemories(), loadSessions()])
}

async function loadProjects() {
  const d = await apiProjects()
  projects.value = d.items
  if (!activeNamespace.value) {
    activeNamespace.value = d.active_namespace || (d.items.length ? d.items[0].namespace : null)
  }
}

async function loadStats() {
  stats.value = await apiStats()
}

async function loadMemories() {
  const d = await listMemories(activeNamespace.value || undefined)
  memories.value = sessionFilter.value
    ? d.items.filter((m) => m.source === `session:${sessionFilter.value!.id}`)
    : d.items
}

async function loadSessions() {
  const d = await apiSessions(activeNamespace.value || undefined)
  sessions.value = d.items
}

async function switchProject(ns: string) {
  activeNamespace.value = ns
  sessionFilter.value = null
  await registerProject(ns)
  await Promise.all([loadProjects(), loadMemories(), loadSessions()])
}

function filterBySession(s: Session) {
  if (sessionFilter.value?.id === s.id) {
    sessionFilter.value = null
  } else {
    sessionFilter.value = { id: s.id, title: s.title || `会话 #${s.id}` }
  }
  loadMemories()
}

async function newSession() {
  try {
    const { value } = await ElMessageBox.prompt('会话标题（可留空）', '新会话', {
      inputValue: '',
      confirmButtonText: '创建',
      cancelButtonText: '取消',
    })
    await startSession(activeNamespace.value || 'default', value || '')
    ElMessage.success('会话已创建')
    await loadSessions()
  } catch {
    // 用户取消
  }
}

async function removeSession(id: number) {
  try {
    await ElMessageBox.confirm(`删除会话 #${id}？`, '确认', { type: 'warning' })
    await apiDeleteSession(id)
    if (sessionFilter.value?.id === id) sessionFilter.value = null
    await loadSessions()
  } catch {
    // 用户取消或删除失败
  }
}

function openAdd() {
  Object.assign(memDialog, { visible: true, editing: false, id: 0, content: '', type: 'fact', tags: '' })
}

function openEdit(m: Memory) {
  Object.assign(memDialog, {
    visible: true,
    editing: true,
    id: m.id,
    content: m.content,
    type: m.memory_type || m.type || 'fact',
    tags: (m.tags || []).join(','),
  })
}

async function saveMemory() {
  if (!memDialog.content.trim()) {
    ElMessage.warning('内容不能为空')
    return
  }
  const payload = {
    content: memDialog.content,
    type: memDialog.type,
    tags: memDialog.tags.split(',').map((s) => s.trim()).filter(Boolean),
    namespace: activeNamespace.value || 'default',
  }
  if (memDialog.editing) await updateMemory(memDialog.id, payload)
  else await remember(payload)
  memDialog.visible = false
  ElMessage.success(memDialog.editing ? '已更新' : '已添加')
  await Promise.all([loadMemories(), loadStats()])
}

async function removeMemory(id: number) {
  try {
    await ElMessageBox.confirm(`删除记忆 #${id}？`, '确认', { type: 'warning' })
    await apiDeleteMemory(id)
    ElMessage.success('已删除')
    await Promise.all([loadMemories(), loadStats()])
  } catch {
    // 用户取消
  }
}

function openAddProject() {
  Object.assign(projDialog, { visible: true, namespace: '', name: '' })
}

async function saveProject() {
  if (!projDialog.namespace.trim()) {
    ElMessage.warning('命名空间不能为空')
    return
  }
  await registerProject(projDialog.namespace.trim(), projDialog.name.trim())
  projDialog.visible = false
  ElMessage.success('项目已注册')
  await Promise.all([loadProjects(), loadStats()])
}

onMounted(loadAll)
</script>

<template>
  <div class="app">
    <header class="topbar">
      <div class="brand">
        <span class="brand-mark">PM</span>
        <span class="brand-name">Portable Memory</span>
        <span class="brand-sub">记忆工作台</span>
      </div>
      <div class="top-actions">
        <span class="conn" :class="{ off: !connected }">
          {{ connected ? '● 已连接' : '● 未连接' }}
        </span>
        <el-input
          v-model="token"
          type="password"
          placeholder="访问令牌（可选）"
          size="small"
          style="width: 170px"
          @keyup.enter="loadAll"
        />
        <el-button size="small" @click="loadAll">刷新</el-button>
        <el-button size="small" tag="a" href="/ui" target="_blank">简洁版</el-button>
      </div>
    </header>

    <main class="main">
      <HeroSection :version="version" />

      <div class="metrics">
        <div class="metric">
          <span class="metric-label">记忆总数</span>
          <span class="metric-value">{{ stats.total }}</span>
        </div>
        <div class="metric">
          <span class="metric-label">项目数</span>
          <span class="metric-value">{{ stats.namespaces }}</span>
        </div>
        <div class="metric">
          <span class="metric-label">累计访问</span>
          <span class="metric-value">{{ stats.total_accesses }}</span>
        </div>
      </div>

      <div class="workspace">
        <SidePanels
          :projects="projects"
          :active-namespace="activeNamespace"
          :sessions="sessions"
          :memory-counts="memoryCounts"
          @switch-project="switchProject"
          @new-project="openAddProject"
          @filter-session="filterBySession"
          @new-session="newSession"
          @delete-session="removeSession"
        />
        <div class="content">
          <RecallLab :namespace="activeNamespace" />
          <MemoryLibrary
            :memories="memories"
            :project-name="projectName"
            :session-filter="sessionFilter?.title || null"
            @add="openAdd"
            @edit="openEdit"
            @delete="removeMemory"
            @clear-filter="sessionFilter = null; loadMemories()"
          />
        </div>
      </div>
    </main>

    <el-dialog v-model="memDialog.visible" :title="memDialog.editing ? '编辑记忆' : '添加记忆'" width="520px">
      <el-form label-position="top">
        <el-form-item label="内容">
          <el-input v-model="memDialog.content" type="textarea" :rows="4" placeholder="写下要记住的偏好、决策、踩坑…" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="memDialog.type" style="width: 100%">
            <el-option label="事实 fact" value="fact" />
            <el-option label="偏好 preference" value="preference" />
            <el-option label="规则 rule" value="rule" />
            <el-option label="决策 decision" value="decision" />
            <el-option label="环境 environment" value="environment" />
            <el-option label="踩坑 pitfall" value="pitfall" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签（逗号分隔）">
          <el-input v-model="memDialog.tags" placeholder="前端,分页" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="memDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveMemory">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="projDialog.visible" title="新建项目" width="440px">
      <el-form label-position="top">
        <el-form-item label="命名空间（英文标识）">
          <el-input v-model="projDialog.namespace" placeholder="my-project" />
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="projDialog.name" placeholder="我的项目" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="projDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveProject">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.app {
  min-height: 100vh;
  background: #faf8f3;
}
.topbar {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 12px 24px;
  background: #e8e4d9;
  border-bottom: 1px solid #d5d0c2;
  flex-wrap: wrap;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}
.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #2563eb;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.brand-name {
  font-size: 16px;
  font-weight: 600;
  color: #2b2620;
}
.brand-sub {
  font-size: 12px;
  color: #7d7566;
}
.top-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.conn {
  font-size: 12px;
  color: #3b6d11;
}
.conn.off {
  color: #c0392b;
}
.main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 16px 24px 40px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.metric {
  background: #fffdfa;
  border: 1px solid #e6e3da;
  border-radius: 8px;
  padding: 12px 16px;
}
.metric-label {
  display: block;
  font-size: 12px;
  color: #7d7566;
}
.metric-value {
  display: block;
  font-size: 24px;
  font-weight: 600;
  color: #2b2620;
}
.workspace {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.content {
  min-width: 0;
}
@media (max-width: 900px) {
  .workspace {
    grid-template-columns: 1fr;
  }
  .metrics {
    grid-template-columns: 1fr;
  }
}
</style>
