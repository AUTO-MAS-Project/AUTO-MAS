<template>
  <!-- 左侧：配置文件列表 -->
  <a-col :span="8" class="left-panel">
    <div class="config-groups">
      <div v-for="(group, groupName) in groups" :key="groupName" class="config-group">
        <div class="group-header">{{ groupName }}</div>
        <div class="group-items">
          <div
            v-for="config in group"
            :key="config.filename"
            class="config-item"
            :class="{
              'config-item--active': selected === config.filename,
            }"
            @click="emit('select', config.filename)"
          >
            <div class="config-item-info">
              <span class="config-item-name">{{ config.displayName }}</span>
              <span v-if="config.taskIndex" class="config-item-badge">
                -t {{ config.taskIndex }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </a-col>
</template>
<script setup lang="ts">
defineProps<{
  groups: Record<string, { filename: string; displayName: string; taskIndex: number | null }[]>
  selected: string | null
}>()
const emit = defineEmits<{ select: [filename: string] }>()
</script>
<style scoped>
.config-item {
  padding: 12px;
  cursor: pointer;
  border-left: 3px solid transparent;
}
.config-item--active {
  background: var(--ant-color-primary-bg);
  border-left-color: var(--ant-color-primary);
}
.group-header {
  font-weight: 600;
  padding: 12px;
}
.config-item-badge {
  margin-left: 8px;
}
</style>
