<template>
  <!-- 常用入口：位于主页右上角工具行（编辑布局/查看公告/刷新 旁），风格与该行一致 -->
  <div class="quick-actions" role="list" aria-label="快速操作">
    <a-button
      v-for="action in actions"
      :key="action.path"
      class="quick-action"
      role="listitem"
      @click="onNavigate(action.path)"
    >
      <template #icon>
        <component :is="action.icon" />
      </template>
      {{ action.title }}
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { ApiOutlined, PlayCircleOutlined, PlusOutlined } from '@ant-design/icons-vue'

const actions = [
  {
    title: '启动脚本',
    path: '/scheduler',
    icon: PlayCircleOutlined,
  },
  {
    title: '添加脚本',
    path: '/scripts',
    icon: PlusOutlined,
  },
  {
    title: '管理插件',
    path: '/plugins',
    icon: ApiOutlined,
  },
]

const emit = defineEmits<{
  (e: 'navigate', path: string): void
}>()

const onNavigate = (path: string) => {
  emit('navigate', path)
}
</script>

<style scoped>
.quick-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* 低性能模式 / reduced-motion 下去除过渡 */
:root[data-perf-mode='low'] .quick-action {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .quick-action {
    transition: none;
  }
}
</style>
