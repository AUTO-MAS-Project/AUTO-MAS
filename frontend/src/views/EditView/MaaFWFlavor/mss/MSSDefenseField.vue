<template>
  <!-- 「灾变防线」是个人版才有的一次性任务：开关是全局的，状态是这一期的。
       开关关着就只说「未启用」，开着才把这一期打没打摊出来 -->
  <a-form-item
    class="flavor-mss-defense"
    :label="t('edit.mssFlavorDefense')"
    :extra="t('edit.mssFlavorDefenseHint')"
  >
    <a-space :size="12">
      <a-switch
        :checked="enabled"
        :loading="saving"
        :disabled="context.loading"
        @change="handleToggle"
      />
      <a-tag v-if="!enabled" color="default">
        {{ t('edit.mssFlavorDefenseOff') }}
      </a-tag>
      <a-tooltip v-else :title="periodHint">
        <a-tag :color="statusColor">{{ statusText }}</a-tag>
      </a-tooltip>
    </a-space>
  </a-form-item>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { GetService, MaaFwService, UpdateService, type MssDefenseStatusData } from '@/api'
import type { MaaFWUserSlotContext } from '@/composables/maafwFlavorTypes'

/**
 * 个人版「灾变防线」：一个全局开关 + 这一期的状态。
 *
 * 状态由后端算（`/maafw/mss/defense-status`）——「这一期」是官网那一篇公告的开始时刻，
 * 那套口径只在编排里有一份，前端不复刻。开关是全局的 `Function.IfPersonalMss`，
 * 与设置页那个「并非神秘入口」是同一个字段，改哪边都一样。
 */

const props = defineProps<{
  context: MaaFWUserSlotContext
}>()

const { t } = useI18n()
const route = useRoute()

const enabled = ref(false)
const saving = ref(false)
const status = ref<MssDefenseStatusData | null>(null)

const statusText = computed(() => {
  const state = status.value
  if (!state?.known) return t('edit.mssFlavorDefenseUnknown')
  if (state.done) return t('edit.mssFlavorDefenseDone')
  if (state.givenUp) return t('edit.mssFlavorDefenseGivenUp')
  if (state.armed) return t('edit.mssFlavorDefenseArmed')
  return t('edit.mssFlavorDefensePending')
})

const statusColor = computed(() => {
  const state = status.value
  if (!state?.known) return 'default'
  if (state.done) return 'green'
  if (state.givenUp) return 'red'
  if (state.armed) return 'blue'
  return 'orange'
})

/** 悬停给出这一期的开始时间与已失败的天数：状态标签只有四个字，细节放这里 */
const periodHint = computed(() => {
  const state = status.value
  if (!state?.known || !state.period) return t('edit.mssFlavorDefenseUnknown')
  const parts = [t('edit.mssFlavorDefensePeriod', { period: state.period })]
  if (state.failedDays?.length) {
    parts.push(t('edit.mssFlavorDefenseFailedDays', { days: state.failedDays.join('、') }))
  }
  return parts.join('\n')
})

const loadStatus = async () => {
  try {
    const response = await MaaFwService.getMssDefenseStatusApiScriptsMaafwMssDefenseStatusPost({
      scriptId: props.context.scriptId,
      userId: String(route.params.userId || ''),
    })
    status.value = response.data ?? null
  } catch {
    // 查不到就显示「状态未知」：这是只读的展示信息，不该拦住整页
    status.value = null
  }
}

/**
 * 读开关：失败就按关闭显示，**不弹提示**——它挂在一个只读的展示位上，后端一时拿不到
 * 不该在用户的编辑页刷一条红字（真要提示留给下面保存那一步）。
 */
const loadSettings = async () => {
  try {
    const response = await GetService.getScriptsApiSettingGetPost()
    if (response.code !== 200) return
    enabled.value = response.data?.Function?.IfPersonalMss === true
  } catch {
    enabled.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadSettings(), loadStatus()])
})

const handleToggle = async (checked: boolean | string | number) => {
  const next = checked === true
  // 值没变就别写：开关的 onChange 不保证只在用户改过时才来，真实交互里也不该为这种请求跑一趟
  if (next === enabled.value) return
  saving.value = true
  try {
    const response = await UpdateService.updateScriptApiSettingUpdatePost({
      data: { Function: { IfPersonalMss: next } },
    })
    if (response.code !== 200) {
      message.error(response.message || t('edit.mssFlavorDefenseSaveFailed'))
      return
    }
    enabled.value = next
    // 刚打开时状态可能还没查过（页面加载那次的开关是关的），补一次
    if (next) await loadStatus()
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('edit.mssFlavorDefenseSaveFailed'))
  } finally {
    saving.value = false
  }
}
</script>
