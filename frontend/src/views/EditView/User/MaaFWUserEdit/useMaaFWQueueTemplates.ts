import { computed, shallowRef, watch, type Ref } from 'vue'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { useScriptApi } from '@/composables/useScriptApi'
import type { MaaFWScriptConfig, MaaFWTaskSnapshot } from '@/types/script'
import type { MaaFWQueueTemplateView } from '../../MaaFWFlavor/sectionContracts'
import {
  addMaaFWQueueTemplate,
  buildMaaFWQueueTemplateSnapshot,
  createMaaFWKeyedWriteCoordinator,
  parseMaaFWQueueTemplates,
  removeMaaFWQueueTemplate,
  renameMaaFWQueueTemplate,
  type MaaFWQueueTemplate,
} from '../maafwQueueTemplates'
import type { MaaFWTaskQueue } from './useMaaFWTaskQueue'

interface MaaFWQueueTemplatesOptions {
  scriptId: string
  /** 页面加载时读到的脚本配置：模板列表的初值 */
  scriptConfig: Ref<MaaFWScriptConfig | null>
  taskSnapshot: Ref<MaaFWTaskSnapshot>
  queue: Pick<
    MaaFWTaskQueue,
    | 'showPresetModal'
    | 'passwordFields'
    | 'templateDraftEntries'
    | 'describeQueueSnapshot'
    | 'replaceQueueWith'
  >
}

/**
 * 模板写入按脚本 id 串行、刷新按版本号丢弃旧结果，放在模块级：页面卸载后在途的写入照样排队，
 * 同一脚本的下一个用户页也在同一条队里。
 */
const templateWrites = createMaaFWKeyedWriteCoordinator()
const MAX_REFRESH_ATTEMPTS = 3

/**
 * 用户页的自定义模板：脚本级 `Task.Templates`，同一脚本的用户共用。
 *
 * 写之前一律先从后端读最新的列表再改（读最新 → 改 → 写），不拿页面加载时那份旧列表整份覆盖：
 * 另一个用户页同时在存模板时，旧列表会把对方刚存的冲掉。打开模板弹窗时也重读一次。
 * 两个窗口同时写的原子性要后端做版本校验，这里不管。
 */
export function useMaaFWQueueTemplates({
  scriptId,
  scriptConfig,
  taskSnapshot,
  queue,
}: MaaFWQueueTemplatesOptions) {
  const { getScript, updateScript } = useScriptApi()

  const templates = shallowRef<MaaFWQueueTemplate[]>([])

  watch(
    scriptConfig,
    config => {
      templates.value = parseMaaFWQueueTemplates(config?.Task?.Templates)
    },
    { immediate: true }
  )

  /** 每个模板在当前项目下的样子：哪些任务已失效、能套用的有哪些 */
  const queueTemplates = computed<MaaFWQueueTemplateView[]>(() =>
    templates.value.map(template => ({
      name: template.name,
      ...queue.describeQueueSnapshot(template.snapshot),
    }))
  )

  /** 「存为模板」弹窗里列出的任务 */
  const queueTemplateDraft = computed(() =>
    queue.templateDraftEntries.value.map(entry => ({
      id: entry.id,
      label: entry.task.label || entry.task.name,
      invalid: false,
    }))
  )

  const readLatestTemplates = async () => {
    try {
      const script = await getScript(scriptId)
      if (!script) return null
      return parseMaaFWQueueTemplates((script.config as MaaFWScriptConfig).Task?.Templates)
    } catch {
      // getScript 已经提示过错误
      return null
    }
  }

  /**
   * 重读模板列表。先等本脚本在途的写入落定再读；读的过程中有写入开始或完成（任何一个用户页的），
   * 这次读到的可能是旧列表，丢弃后再读，最多三次。
   */
  const refreshQueueTemplates = async () => {
    for (let attempt = 0; attempt < MAX_REFRESH_ATTEMPTS; attempt += 1) {
      await templateWrites.settled(scriptId)
      const epoch = templateWrites.epoch(scriptId)
      const latest = await readLatestTemplates()
      if (templateWrites.epoch(scriptId) !== epoch) continue
      if (latest) templates.value = latest
      return
    }
  }

  // 按脚本串行（模块级共享）：连着点、或刚离开的用户页还在写，都等前一次写完、基于它的结果再改
  const writeTemplates = (
    mutate: (latest: MaaFWQueueTemplate[]) => MaaFWQueueTemplate[] | null
  ): Promise<boolean> =>
    templateWrites.write(scriptId, async () => {
      const latest = await readLatestTemplates()
      if (!latest) return false
      const next = mutate(latest)
      if (!next) {
        templates.value = latest
        return false
      }
      const success = await updateScript(scriptId, {
        Task: { Templates: JSON.stringify(next) },
      })
      templates.value = success ? next : latest
      return success
    })

  const rejectDuplicate = (next: MaaFWQueueTemplate[] | null) => {
    if (!next) message.error(t('edit.queueTemplateNameExists'))
    return next
  }

  /** 把当前队列存成模板（去掉虚影、受管任务与密码值）；同名不覆盖 */
  const saveQueueTemplate = async (name: string) => {
    const snapshot = buildMaaFWQueueTemplateSnapshot(
      queue.templateDraftEntries.value,
      taskSnapshot.value.taskOptions,
      queue.passwordFields.value
    )
    if (snapshot.taskOrder.length === 0) return false
    return await writeTemplates(latest =>
      rejectDuplicate(addMaaFWQueueTemplate(latest, { name, snapshot }))
    )
  }

  const renameQueueTemplate = async (name: string, nextName: string) =>
    await writeTemplates(latest => {
      // 原模板已经被别处删掉：列表换成最新的就行，不再提示重名
      if (!latest.some(item => item.name === name)) return null
      return rejectDuplicate(renameMaaFWQueueTemplate(latest, name, nextName))
    })

  const deleteQueueTemplate = async (name: string) =>
    await writeTemplates(latest => removeMaaFWQueueTemplate(latest, name))

  /** 套用模板：直接替换队列（语义同套用预设），失效任务跳过 */
  const applyQueueTemplate = async (name: string) => {
    const template = queueTemplates.value.find(item => item.name === name)
    if (!template || template.entries.length === 0) return
    await queue.replaceQueueWith(template)
  }

  watch(queue.showPresetModal, open => {
    if (open) void refreshQueueTemplates()
  })

  return {
    queueTemplates,
    queueTemplateDraft,
    saveQueueTemplate,
    renameQueueTemplate,
    deleteQueueTemplate,
    applyQueueTemplate,
  }
}
