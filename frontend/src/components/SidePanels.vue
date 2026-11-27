<script setup lang="ts">
/** 左侧：项目隔离与会话回溯。点项目即切换命名空间，点会话可筛选其记忆。 */
import type { Project, Session } from '../types'

defineProps<{
  projects: Project[]
  activeNamespace: string | null
  sessions: Session[]
  memoryCounts: Record<string, number>
}>()

const emit = defineEmits<{
  (e: 'switch-project', ns: string): void
  (e: 'new-project'): void
  (e: 'filter-session', session: Session): void
  (e: 'new-session'): void
  (e: 'delete-session', id: number): void
}>()

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <aside class="side">
    <section class="panel">
      <div class="panel-head">
        <h2>项目隔离</h2>
        <el-button link size="small" @click="emit('new-project')">+ 新建</el-button>
      </div>
      <p class="hint">在哪个项目开编辑器，记忆就写到哪里</p>
      <div v-if="!projects.length" class="empty">暂无项目</div>
      <button
        v-for="p in projects"
        :key="p.namespace"
        class="proj"
        :class="{ active: p.namespace === activeNamespace }"
        @click="emit('switch-project', p.namespace)"
      >
        <span class="proj-name">{{ p.name }}</span>
        <span class="proj-meta">
          {{ p.namespace }} · {{ memoryCounts[p.namespace] ?? 0 }} 条
          <span v-if="p.namespace === activeNamespace" class="current">当前</span>
        </span>
      </button>
    </section>

    <section class="panel">
      <div class="panel-head">
        <h2>会话回溯</h2>
        <el-button link size="small" @click="emit('new-session')">+ 新会话</el-button>
      </div>
      <p class="hint">每次协作及其产生的记忆</p>
      <div v-if="!sessions.length" class="empty">暂无会话</div>
      <div v-for="s in sessions" :key="s.id" class="session">
        <button class="session-main" @click="emit('filter-session', s)">
          <span class="session-title">{{ s.title || `会话 #${s.id}` }}</span>
          <span class="session-meta">
            {{ fmt(s.started_at) }} · {{ s.memory_count }} 条记忆
            <span v-if="s.ended_at">· 已结束</span>
          </span>
        </button>
        <el-button
          v-if="s.ended_at"
          link
          size="small"
          type="danger"
          @click="emit('delete-session', s.id)"
        >删除</el-button>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.side {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 16px;
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
h2 {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
}
.hint {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin: 6px 0 12px;
}
.proj {
  display: block;
  width: 100%;
  text-align: left;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 4px;
  cursor: pointer;
  font-family: inherit;
}
.proj:hover {
  background: var(--el-fill-color-light);
}
.proj.active {
  background: var(--el-color-primary-light-9);
  border-color: var(--el-color-primary-light-5);
}
.proj-name {
  display: block;
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.proj-meta {
  display: block;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.current {
  color: var(--el-color-primary);
}
.session {
  display: flex;
  align-items: center;
  gap: 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 6px 0;
}
.session:last-child {
  border-bottom: none;
}
.session-main {
  flex: 1;
  min-width: 0;
  text-align: left;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 2px 0;
  font-family: inherit;
}
.session-title {
  display: block;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-meta {
  display: block;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.empty {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 12px 0;
}
</style>
