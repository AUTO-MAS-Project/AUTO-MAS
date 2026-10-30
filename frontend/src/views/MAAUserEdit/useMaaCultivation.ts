import { onScopeDispose, provide, readonly, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Service, type CultivatePreviewOut } from '@/api'
import { useMaaCultivateImportApi } from '@/composables/useMaaCultivateImportApi'
import { useMaaCultivateDataApi } from '@/composables/useMaaCultivateDataApi'
import { cultivateDataRefreshKey } from './cultivateDataRefresh'
import {
  mergeCultivateTargets,
  normalizeCultivateCatalog,
  parseCultivateTargets,
  serializeCultivateTargets,
  type CultivateImportResult,
  type CultivateOperatorCatalogEntry,
} from './cultivateTargets'

interface CultivationOptions {
  scriptId: string
  getUserId: () => string
  task: () => {
    CultivateTargets: string
    CultivateSklandAccount: string
    CultivateSklandUid: string
  }
  isInitializing: () => boolean
  isLocked: () => boolean
  saveTargets: (targets: string) => Promise<boolean>
  trackEdit: <T>(edit: () => Promise<T>) => Promise<T>
}

/** 养成目录、角色绑定与需求预览共用读取代次，导入仍复用编辑页的保存队列。 */
export function useMaaCultivation(options: CultivationOptions) {
  const { scriptId } = options
  const { t } = useI18n()
  const { parseImport } = useMaaCultivateImportApi()
  const dataApi = useMaaCultivateDataApi()
  const logger = window.electronAPI.getLogger('MAA 干员养成')
  // 干员养成选择器目录（一图流全量表，含技能/模组名称目录与可达档位，随快照缓存）
  const cultivateOperatorCatalog = ref<CultivateOperatorCatalogEntry[]>([])

  // 森空岛绑定下拉：合并所有已配置凭据账号组的角色（下拉展开时按需加载）
  const sklandRoleOptions = ref<Array<{ label: string; value: string }>>([])
  const sklandRoleLoading = ref(false)
  const sklandRoleError = ref('')
  const cultivateOperatorOptionsLoading = ref(false)
  const cultivateOperatorOptionsError = ref('')

  // 干员目录（一图流全量表，含技能/模组名称目录与可达档位，随快照缓存；
  // 序列号守卫防绑定变更连发两次加载时的乱序覆盖）
  let cultivateOperatorCatalogSeq = 0

  // 养成需求预览（纯计算不落库；序列号守卫防快速编辑时的乱序覆盖）
  const cultivatePreview = ref<CultivatePreviewOut | null>(null)
  const cultivatePreviewLoading = ref(false)
  const cultivatePreviewError = ref('')
  let cultivatePreviewSeq = 0
  const refreshing = ref(false)
  let disposed = false

  const resetCultivatePreview = () => {
    cultivatePreviewSeq++
    cultivatePreview.value = null
    cultivatePreviewLoading.value = false
    cultivatePreviewError.value = ''
  }
  onScopeDispose(() => {
    disposed = true
    cultivateOperatorCatalogSeq++
    cultivatePreviewSeq++
  })

  const loadCultivateOperatorOptions = async () => {
    const userId = options.getUserId()
    // 绑定变更的两字段保存分属两个 await 周期，watch 会以半绑定/完整状态各
    // 触发一次加载；seq 守卫丢弃乱序返回的过期响应（与预览加载同款）
    const seq = ++cultivateOperatorCatalogSeq
    cultivateOperatorOptionsLoading.value = true
    cultivateOperatorOptionsError.value = ''
    try {
      const response = await Service.getMaaCultivateOperatorsApiScriptsMaaCultivateOperatorsPost({
        script: { scriptId },
        userId,
      })
      if (seq !== cultivateOperatorCatalogSeq) return
      if (response.code !== 200) {
        cultivateOperatorOptionsError.value = response.message || '加载干员目录失败'
        return
      }
      cultivateOperatorCatalog.value = normalizeCultivateCatalog(response.data ?? [])
    } catch (error) {
      if (seq !== cultivateOperatorCatalogSeq) return
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载干员目录失败: ${errorMsg}`)
      cultivateOperatorOptionsError.value = '加载干员目录失败'
    } finally {
      if (seq === cultivateOperatorCatalogSeq) cultivateOperatorOptionsLoading.value = false
    }
  }

  const importCultivateTargets = (
    content: string,
    format: 'clipboard' | 'targets' = 'clipboard'
  ): Promise<CultivateImportResult> =>
    options.trackEdit(async () => {
      const userId = options.getUserId()
      if (!userId || options.isLocked())
        throw new Error(t('core.edit.maaCultivateImportUnavailable'))
      const imported =
        format === 'clipboard'
          ? await parseImport(scriptId, content)
          : { targets: content, data: [], skippedMessages: [] }
      const merged = mergeCultivateTargets(
        parseCultivateTargets(options.task().CultivateTargets),
        parseCultivateTargets(imported.targets)
      )
      const result = { ...merged.result, skipped: imported.skippedMessages }
      if (!result.operatorIds.length) return result
      const saved = await options.saveTargets(serializeCultivateTargets(merged.rows))
      if (!saved) throw new Error(t('core.edit.couldNotSaveUser'))
      // 导入可包含已满级、被选择器过滤的干员，补回其名称和技能目录。
      const additions = normalizeCultivateCatalog(imported.data ?? [])
      const importedIds = new Set(additions.map(item => item.value))
      cultivateOperatorCatalog.value = [
        ...cultivateOperatorCatalog.value.filter(item => !importedIds.has(item.value)),
        ...additions,
      ]
      await loadCultivateOperatorOptions()
      return result
    })

  const loadSklandRoleOptions = async () => {
    // 该端点要遍历所有已配置森空岛凭据的账号组做凭据刷新+角色拉取，代价高；
    // 每次展开任务行都会重新挂载编辑器并触发回显请求，故已加载过就直接复用
    // （要刷新列表：离开编辑页重进，或下拉为空时由展开下拉触发）
    if (sklandRoleOptions.value.length) return
    sklandRoleLoading.value = true
    sklandRoleError.value = ''
    try {
      const response =
        await Service.getMaaCultivateSklandBindingsApiScriptsMaaCultivateSklandBindingsPost()
      if (response.code !== 200) {
        sklandRoleError.value = response.message || '加载绑定角色失败'
        sklandRoleOptions.value = []
        return
      }
      sklandRoleOptions.value = response.data.map(option => ({
        label: option.label,
        value: option.value as string,
      }))
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`加载森空岛绑定角色失败: ${errorMsg}`)
      sklandRoleError.value = '加载绑定角色失败'
      sklandRoleOptions.value = []
    } finally {
      sklandRoleLoading.value = false
    }
  }

  // 绑定变化（绑定↔解绑、或换绑到另一角色）后：选择器目录需按森空岛快照
  // 重新过滤（精 2 干员绑定后恢复可见，解除绑定回到剔精 2 口径），预览也要
  // 按新练度重算——故比较账号|角色的复合值而不只是绑定与否
  watch(
    () =>
      `${options.task()?.CultivateSklandAccount ?? ''}|${options.task()?.CultivateSklandUid ?? ''}`,
    (next, prev) => {
      if (options.isInitializing() || !options.getUserId() || next === prev) return
      loadCultivateOperatorOptions()
      if (options.task()?.CultivateTargets) {
        loadCultivatePreview(options.task().CultivateTargets)
      }
    }
  )

  const loadCultivatePreview = async (targetsJson: string) => {
    if (!parseCultivateTargets(targetsJson).length) {
      resetCultivatePreview()
      return
    }
    const userId = options.getUserId()
    const seq = ++cultivatePreviewSeq
    cultivatePreviewLoading.value = true
    cultivatePreviewError.value = ''
    try {
      const response = await Service.getMaaCultivatePreviewApiScriptsMaaCultivatePreviewPost({
        scriptId,
        userId,
        targets: targetsJson,
      })
      if (seq !== cultivatePreviewSeq) return
      if (response.code !== 200) {
        cultivatePreviewError.value = response.message || '需求计算失败'
        return
      }
      cultivatePreview.value = response
    } catch (error) {
      if (seq !== cultivatePreviewSeq) return
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`养成需求计算失败: ${errorMsg}`)
      cultivatePreviewError.value = '需求计算失败'
    } finally {
      if (seq === cultivatePreviewSeq) cultivatePreviewLoading.value = false
    }
  }

  provide(cultivateDataRefreshKey, {
    refreshing: readonly(refreshing),
    refresh: async () => {
      const userId = options.getUserId()
      if (refreshing.value || !userId || disposed) return 'cancelled'
      refreshing.value = true
      // 作废刷新前的响应；失败仍保留已经显示的目录和预览。
      cultivateOperatorCatalogSeq++
      cultivatePreviewSeq++
      cultivateOperatorOptionsLoading.value = false
      cultivatePreviewLoading.value = false
      try {
        await dataApi.refresh(scriptId)
        if (disposed || userId !== options.getUserId()) return 'cancelled'
        await Promise.all([
          loadCultivateOperatorOptions(),
          loadCultivatePreview(options.task().CultivateTargets),
        ])
        if (disposed || userId !== options.getUserId()) return 'cancelled'
        return cultivateOperatorOptionsError.value || cultivatePreviewError.value
          ? 'partial'
          : 'success'
      } finally {
        refreshing.value = false
      }
    },
  })

  return {
    cultivateOperatorCatalog,
    cultivateOperatorOptionsLoading,
    cultivateOperatorOptionsError,
    sklandRoleOptions,
    sklandRoleLoading,
    sklandRoleError,
    cultivatePreview,
    cultivatePreviewLoading,
    cultivatePreviewError,
    loadCultivateOperatorOptions,
    loadSklandRoleOptions,
    loadCultivatePreview,
    importCultivateTargets,
    resetCultivatePreview,
  }
}
