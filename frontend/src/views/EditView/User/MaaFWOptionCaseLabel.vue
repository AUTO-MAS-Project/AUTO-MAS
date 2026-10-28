<template>
  <!-- 单选、下拉、多选的每一项共用：项目给了 case 图标就放在文字前面 -->
  <span class="case-label">
    <img
      v-if="iconUrl"
      :src="iconUrl"
      alt=""
      width="16"
      height="16"
      class="case-icon"
      @error="hideBrokenMaaFWIcon"
      @load="showLoadedMaaFWIcon"
    />
    <span>{{ caseItem.label || caseItem.name }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { buildMaaFWAssetUrl } from '@/composables/useMaaFWApi'
import type { MaaFWOptionCaseInfo } from '@/types/script'
import { hideBrokenMaaFWIcon, showLoadedMaaFWIcon } from './maafwIconImage'

const props = defineProps<{
  caseItem: MaaFWOptionCaseInfo
  /** 图标按项目目录解析 */
  basePath: string
}>()

const iconUrl = computed(() => buildMaaFWAssetUrl(props.basePath, props.caseItem.icon))
</script>

<style scoped>
.case-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.case-icon {
  width: 16px;
  height: 16px;
  object-fit: contain;
  flex: 0 0 auto;
}
</style>
