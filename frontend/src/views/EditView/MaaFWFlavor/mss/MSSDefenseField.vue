<template>
  <!-- 「灾变防线」整块都是个人版专属：没在设置页输入密码启用个人版（Function.IfPersonalMss）
       的普通用户不该看到它，连一个灰着的开关也不该有——`enabled` 初值是 false，读到开关为真
       才渲染，所以没有「先闪一下再消失」的问题。启用之后这里留住开关，是为了能就地关掉它。 -->
  <a-form-item
    v-if="enabled"
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
      <a-tooltip :title="periodHint">
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
import { MaaFwService, UpdateService, type MssDefenseStatusData } from '@/api'
import type { MaaFWUserSlotContext } from '@/composables/maafwFlavorTypes'

/**
 * 个人版「灾变防线」：一个全局开关 + 这一期的状态，**整块只在个人版启用后出现**。
 *
 * 状态由后端算（`/maafw/mss/defense-status`）——「这一期」是官网那一篇公告的开始时刻，
 * 那套口径只在编排里有一份，前端不复刻。个人版总开关（`Function.IfPersonalMss`，与神秘入口里
 * 那个「并非神秘入口」是同一个字段）也由它一起带回来：没开时这块 UI 不该存在，而为一个
 * 布尔再去读一遍整份全局配置不值得。
 */

const props = defineProps<{
  context: MaaFWUserSlotContext
}>()

const { t } = useI18n()
const route = useRoute()

const saving = ref(false)
const status = ref<MssDefenseStatusData | null>(null)

/** 总开关来自状态响应：拿不到（还没查到 / 查失败）就按没开算，整块不渲染 */
const enabled = computed(() => status.value?.enabled === true)

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
    // 查不到就当没启用：整块不渲染。这是只读的展示信息，不该拦住整页
    status.value = null
  }
}

onMounted(loadStatus)

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
    // 本地先翻过去，省得为一个布尔再查一次；关掉时这一块会整个消失
    status.value = { ...(status.value ?? {}), enabled: next }
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('edit.mssFlavorDefenseSaveFailed'))
  } finally {
    saving.value = false
  }
}
</script>
