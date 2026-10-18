import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import type { MaaFWScriptConfig } from '@/types/script'
import type { MaaFWEnvOutcome } from '../../MaaFWFlavor/sectionContracts'
import type { MaaFWProgressChannel } from './useMaaFWProgressChannel'

/**
 * 读到 interface 之后立刻把运行环境备好（下载 MaaFramework、建 agent 环境）。
 * 不做的话这份成本会推迟到用户第一次点运行时才付，界面上看起来像卡住。
 */
export function useMaaFWEnvPrepare(
  scriptId: string,
  maafwConfig: MaaFWScriptConfig,
  channel: MaaFWProgressChannel
) {
  const { t } = useI18n()
  const { prepareMaaFWAgentEnv } = useScriptApi()
  const { ensureEnvSubscription } = channel

  const envPreparing = ref(false)
  const envReady = ref(false)
  const envFailed = ref(false)
  const envMessage = ref('')
  const envPercent = ref<number | null>(null)
  const envLogs = ref<string[]>([])
  const envAgents = ref<{ runtimeKind?: string | null; executable: string }[]>([])
  // 成功时是哪一种：首次准备 / 更新了已有环境 / 项目没变直接沿用，面板按它选状态词
  const envOutcome = ref<MaaFWEnvOutcome | null>(null)

  channel.onEnvProgress(data => {
    // 响应处理完就不再理会 WS：它走的是另一条路，可能比响应还晚到——日志行会把
    // 最后几行写成两遍，ready 事件那句「MFW 运行环境已就绪」会把响应里写好的
    // 「MaaFramework x.y.z」盖掉
    if (!envPreparing.value) return
    if (data.log) {
      envLogs.value = [...envLogs.value.slice(-199), data.log]
    }
    if (data.stage === 'log') return
    envMessage.value = data.message || envMessage.value
    if (typeof data.percent === 'number') envPercent.value = data.percent
    if (data.status === 'failed') {
      envFailed.value = true
      envPreparing.value = false
    }
  })

  const envPreparedPath = ref('')

  const runAgentEnvPrepare = async (targetPath?: string, force = false) => {
    const path = (targetPath ?? maafwConfig.Info.Path).trim()
    if (!path) return
    if (envPreparing.value) return
    // 同一个项目已经备好过就不重复跑；换了目录才重新准备。
    // 这层只挡住本次停留在页面上的重复调用；跨页面进出由后端比项目指纹来挡。
    if (!force && envReady.value && envPreparedPath.value === path) return
    ensureEnvSubscription()
    envPreparing.value = true
    envReady.value = false
    envFailed.value = false
    envPercent.value = null
    envLogs.value = []
    envOutcome.value = null
    envMessage.value = t('edit.envPreparingHint')
    try {
      const response = await prepareMaaFWAgentEnv(path, scriptId, force)
      if (!response || response.code !== 200 || !response.data) {
        envFailed.value = true
        envMessage.value = response?.message || t('edit.envStatusFailed')
        // 失败响应里同样带着逐行日志，而且这才是最需要它的时候：原先这里直接
        // return，把唯一一份失败原因扔了，用户只剩一句「准备失败」。
        if (response?.data?.logs?.length) envLogs.value = response.data.logs
        message.error(envMessage.value)
        return
      }
      envReady.value = true
      envPercent.value = 100
      envPreparedPath.value = path
      envAgents.value = response.data.agents ?? []
      // 后端返回的完整日志兜底：WS 断连时至少事后能看到
      if (response.data.logs?.length) envLogs.value = response.data.logs
      const version = response.data.maafwVersion
      envMessage.value = version ? `MaaFramework ${version}` : ''
      // 旧后端没有 previouslyPrepared 字段：读不到就按首次准备算
      envOutcome.value = response.data.cached
        ? 'cached'
        : response.data.previouslyPrepared
          ? 'updated'
          : 'prepared'
    } catch (error) {
      envFailed.value = true
      envMessage.value = error instanceof Error ? error.message : String(error)
      message.error(envMessage.value)
    } finally {
      envPreparing.value = false
    }
  }

  return {
    envPreparing,
    envReady,
    envFailed,
    envMessage,
    envPercent,
    envLogs,
    envAgents,
    envOutcome,
    envPreparedPath,
    runAgentEnvPrepare,
  }
}
