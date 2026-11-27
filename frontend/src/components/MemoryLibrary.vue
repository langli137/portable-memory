<script setup lang="ts">
/** 记忆库：列表、类型/标签过滤、编辑删除。按会话筛选时显示来源提示。 */
import type { Memory } from '../types'

const props = defineProps<{
  memories: Memory[]
  projectName: string
  sessionFilter: string | null
}>()

const emit = defineEmits<{
  (e: 'add'): void
  (e: 'edit', m: Memory): void
  (e: 'delete', id: number): void
  (e: 'clear-filter'): void
}>()

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false })
}
</script>

<template>
  <section class="library">
    <div class="lib-head">
      <div>
        <h2>记忆库 <span class="count">{{ memories.length }}</span></h2>
        <p class="hint">{{ projectName }} · 所有记忆均来自真实数据库</p>
      </div>
      <el-button type="primary" size="small" @click="emit('add')">+ 添加记忆</el-button>
    </div>

    <div v-if="sessionFilter" class="filter-bar">
      <el-tag type="info" size="small" closable @close="emit('clear-filter')">
        按会话筛选：{{ sessionFilter }}
      </el-tag>
    </div>

    <div v-if="!memories.length" class="empty">暂无记忆，点右上角添加</div>
    <div v-else class="list">
      <article v-for="m in memories" :key="m.id" class="item">
        <div class="meta">
          <el-tag size="small" effect="plain">{{ m.memory_type || m.type }}</el-tag>
          <el-tag v-for="t in m.tags || []" :key="t" size="small" type="info" effect="plain">
            {{ t }}
          </el-tag>
          <span class="dim">#{{ m.id }}</span>
          <span class="dim">{{ fmt(m.created_at) }}</span>
          <span class="dim">访问 {{ m.access_count }}</span>
        </div>
        <p class="content">{{ m.content }}</p>
        <div v-if="m.source" class="source">来源: {{ m.source }}</div>
        <div class="actions">
          <el-button link size="small" @click="emit('edit', m)">编辑</el-button>
          <el-button link size="small" type="danger" @click="emit('delete', m.id)">删除</el-button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.library {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 18px 20px;
}
.lib-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
}
h2 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 4px;
}
.count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-weight: 400;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0;
}
.filter-bar {
  margin-bottom: 12px;
}
.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.dim {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.content {
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
.source {
  font-size: 11px;
  color: var(--el-color-primary);
  margin-top: 6px;
}
.actions {
  margin-top: 8px;
}
.empty {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 30px 0;
}
</style>
