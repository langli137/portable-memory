<script setup lang="ts">
/**
 * 召回演示台：输入一句 AI 会问的话，展示它实际会捞到哪些记忆、为什么。
 * 分数拆解全部来自后端真实返回值，不含任何模拟数据。
 */
import { ref } from 'vue'
import { recall } from '../api'
import type { Memory } from '../types'

const props = defineProps<{ namespace: string | null }>()

const query = ref('')
const results = ref<Memory[]>([])
const searched = ref(false)
const loading = ref(false)
const errorMsg = ref('')

async function run() {
  if (!query.value.trim()) return
  loading.value = true
  errorMsg.value = ''
  try {
    const data = await recall(query.value, props.namespace || undefined, 8)
    results.value = data.items
    searched.value = true
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : '召回失败'
  } finally {
    loading.value = false
  }
}

function reset() {
  query.value = ''
  results.value = []
  searched.value = false
  errorMsg.value = ''
}

function pct(v: number | undefined): string {
  return v === undefined ? '0%' : `${Math.round(v * 100)}%`
}
</script>

<template>
  <section class="lab">
    <div class="lab-head">
      <div>
        <h2>召回演示台</h2>
        <p class="hint">输入一句 AI 会问的话，看看它会捞到哪些记忆、以及为什么</p>
      </div>
      <el-button v-if="searched" link size="small" @click="reset">清空</el-button>
    </div>

    <div class="query-row">
      <el-input
        v-model="query"
        placeholder="例如：分页默认几条？"
        clearable
        @keyup.enter="run"
      />
      <el-button type="primary" :loading="loading" @click="run">召回</el-button>
    </div>

    <el-alert v-if="errorMsg" :title="errorMsg" type="error" :closable="false" show-icon />

    <template v-if="searched">
      <p v-if="!results.length" class="empty">没有召回任何记忆，换个问法试试</p>
      <div v-else class="results">
        <article v-for="m in results" :key="m.id" class="result">
          <div class="result-top">
            <span class="content">{{ m.content }}</span>
            <span class="score">{{ m.score?.toFixed(3) ?? '-' }}</span>
          </div>
          <div class="breakdown">
            <span v-if="m.matched_terms?.length" class="terms">
              命中词: {{ m.matched_terms.join('、') }}
            </span>
            <span class="tag-type">{{ m.memory_type || m.type }}</span>
            <span>关键词 {{ pct(m.bm25) }}</span>
            <span>时效 {{ pct(m.recency) }}</span>
            <span>访问 {{ pct(m.frequency) }}</span>
          </div>
        </article>
      </div>
    </template>
    <p v-else class="placeholder">试着问一个你曾经过去告诉过 AI 的事实</p>
  </section>
</template>

<style scoped>
.lab {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 16px;
}
.lab-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
h2 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 4px;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 0 0 14px;
}
.query-row {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}
.results {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.result {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
}
.result-top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}
.content {
  font-size: 13px;
  line-height: 1.5;
}
.score {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
  white-space: nowrap;
}
.breakdown {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.terms {
  color: var(--el-color-primary);
}
.tag-type {
  border: 1px solid var(--el-border-color);
  border-radius: 4px;
  padding: 0 5px;
}
.empty,
.placeholder {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  text-align: center;
  padding: 20px 0;
  margin: 0;
}
</style>
