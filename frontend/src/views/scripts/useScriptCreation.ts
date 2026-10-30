import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { translate as t } from '@/i18n'
import { useScriptApi } from '@/composables/useScriptApi'
import type { useTemplateApi } from '@/composables/useTemplateApi'
import type { useMaaFWEmbeddedApi } from '@/composables/useMaaFWEmbeddedApi'
import { maafwRouteLocation } from '@/router/maafwFlavorRoutes'
import {
  getScriptEditSegment,
  isMfwFamily,
  type ScriptCreateRequest,
} from './components/scriptCreateFlow'
import type { ScriptType } from '@/types/script'
import type { ScriptListItem } from './scriptListModel'
import { analyticsScriptType, beginAnalyticsOperation } from '@/utils/analytics'
import type { AnalyticsEventProps } from '@/types/analytics'

interface CreationOptions {
  reloadScripts(): Promise<void>
  closeDialog(): void
  importTemplate: ReturnType<typeof useTemplateApi>['importScriptFromTemplate']
  cloneProject: ReturnType<typeof useMaaFWEmbeddedApi>['cloneEmbedded']
}

/** 新建、模板导入、项目复用与复制的完整流程；基础记录创建不等于导入完成。 */
export function useScriptCreation(options: CreationOptions) {
  const router = useRouter()
  const { addScript, deleteScript } = useScriptApi()
  const logger = window.electronAPI.getLogger('脚本创建')
  const addLoading = ref(false)
  const copyingScriptId = ref<string | null>(null)
  const navigate = (scriptId: string, type: ScriptType, data?: Record<string, unknown>) => {
    void router.push({
      ...(isMfwFamily(type)
        ? maafwRouteLocation(type, 'setup', { id: scriptId })
        : { path: `/scripts/${scriptId}/edit/${getScriptEditSegment(type)}` }),
      ...(data
        ? {
            state: { scriptData: { id: scriptId, type, config: JSON.parse(JSON.stringify(data)) } },
          }
        : {}),
    })
  }

  const submit = async (request: ScriptCreateRequest) => {
    const operation = beginAnalyticsOperation('script_create_finished')
    const type = request.kind === 'new' || request.kind === 'mfw-reuse' ? request.type : 'General'
    const create_kind =
      request.kind === 'general-template'
        ? 'template'
        : request.kind === 'mfw-reuse'
          ? 'reuse'
          : 'new'
    let outcome: AnalyticsEventProps['script_create_finished']['outcome'] = 'failure'
    addLoading.value = true
    try {
      const result = await addScript(type)
      if (!result) return
      outcome = 'partial'
      if (request.kind === 'mfw-reuse') {
        try {
          const { message: text } = await options.cloneProject(
            result.scriptId,
            request.sourceScriptId
          )
          outcome = 'success'
          if (text) message.success(text)
        } catch (error) {
          const reason = error instanceof Error ? error.message : String(error)
          logger.error(`复用已有脚本的项目失败: ${reason}`)
          message.error(t('core.scripts.toast.reuseFailed', { reason }))
        }
        options.closeDialog()
        navigate(result.scriptId, type)
        return
      }
      if (request.kind === 'general-template') {
        const imported = await options.importTemplate(result.scriptId, request.template)
        if (!imported) {
          outcome = (await deleteScript(result.scriptId)) ? 'failure' : 'partial'
          await options.reloadScripts()
          return
        }
        outcome = 'success'
        message.success(
          t('core.scripts.toast.createdFromTemplate', { name: request.template.displayName })
        )
        await options.reloadScripts()
        options.closeDialog()
        navigate(result.scriptId, 'General')
        return
      }
      outcome = 'success'
      options.closeDialog()
      navigate(result.scriptId, type, result.data)
    } catch (error) {
      logger.error(`创建脚本失败: ${error instanceof Error ? error.message : String(error)}`)
    } finally {
      operation.finish({ create_kind, script_type: analyticsScriptType(type), outcome })
      addLoading.value = false
    }
  }

  const copy = async (script: ScriptListItem) => {
    const operation = beginAnalyticsOperation('script_create_finished')
    let outcome: 'success' | 'failure' = 'failure'
    addLoading.value = true
    copyingScriptId.value = script.id
    try {
      const result = await addScript(script.type, script.id)
      if (result) {
        outcome = 'success'
        await options.reloadScripts()
        message.success(t('core.scripts.toast.copied', { name: script.name }))
      }
    } finally {
      operation.finish({
        create_kind: 'copy',
        script_type: analyticsScriptType(script.type),
        outcome,
      })
      addLoading.value = false
      copyingScriptId.value = null
    }
  }
  return { addLoading, copyingScriptId, submit, copy }
}
