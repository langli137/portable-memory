<script setup lang="ts">
/** 顶部英雄区：一句话讲清系统价值 + 展示跨编辑器接入能力。 */
defineProps<{ version: string }>()

const editors = [
  { name: 'Claude Code', abbr: 'CC' },
  { name: 'Cursor', abbr: 'CU' },
  { name: 'DeepSeek Harness', abbr: 'DSH' },
  { name: 'WorkBuddy', abbr: 'WB' },
]
</script>

<template>
  <section class="hero">
    <div class="hero-top">
      <div>
        <h1>一套记忆，喂给所有编辑器</h1>
        <p class="tagline">捕获 → 去重 → 按需召回，本地存储，跨项目隔离</p>
      </div>
      <span v-if="version" class="version">服务 v{{ version }}</span>
    </div>
    <div class="editors">
      <span v-for="e in editors" :key="e.name" class="editor">
        <span class="editor-abbr">{{ e.abbr }}</span>
        {{ e.name }}
      </span>
    </div>
  </section>
</template>

<style scoped>
.hero {
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 16px;
}
.hero-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}
h1 {
  font-size: 20px;
  font-weight: 600;
  margin: 0 0 6px;
  color: var(--el-text-color-primary);
}
.tagline {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 0;
}
.version {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
}
.editors {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}
.editor {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  padding: 4px 12px 4px 4px;
  border-radius: 999px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}
.editor-abbr {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  font-size: 10px;
  font-weight: 600;
}
</style>
