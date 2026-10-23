import { translate as t } from '@/i18n'
import { Service, BetterGiService, OknteService } from '@/api'
import { apiOutcome, observeFeature } from '@/utils/featureAnalytics'

/** 专项独有的导入、保存和实例入口；读接口继承原客户端，不增加观测。 */
export class AdapterSetupService extends Service {
  static override importInfrastructureApiScriptsUserInfrastructurePost = (
    ...args: Parameters<typeof Service.importInfrastructureApiScriptsUserInfrastructurePost>
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'MAA', operation_kind: 'import', engine_kind: 'unknown' },
      () => Service.importInfrastructureApiScriptsUserInfrastructurePost(...args),
      apiOutcome
    )
  static override setInfrastPlanSelectApiScriptsUserInfrastructurePlanSelectPost = (
    ...args: Parameters<
      typeof Service.setInfrastPlanSelectApiScriptsUserInfrastructurePlanSelectPost
    >
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'MAA', operation_kind: 'save', engine_kind: 'unknown' },
      () => Service.setInfrastPlanSelectApiScriptsUserInfrastructurePlanSelectPost(...args),
      apiOutcome
    )
  static override importZzzodConfigApiApiScriptsZzzodImportPost = (
    ...args: Parameters<typeof Service.importZzzodConfigApiApiScriptsZzzodImportPost>
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'ZzzOd', operation_kind: 'import', engine_kind: 'unknown' },
      () => Service.importZzzodConfigApiApiScriptsZzzodImportPost(...args),
      apiOutcome
    )
  static override saveZzzodNativeConfigApiApiScriptsZzzodNativeConfigSavePost = (
    ...args: Parameters<typeof Service.saveZzzodNativeConfigApiApiScriptsZzzodNativeConfigSavePost>
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'ZzzOd', operation_kind: 'save', engine_kind: 'unknown' },
      () => Service.saveZzzodNativeConfigApiApiScriptsZzzodNativeConfigSavePost(...args),
      apiOutcome
    )
  static override saveZzzodAppConfigApiApiScriptsZzzodAppConfigSavePost = (
    ...args: Parameters<typeof Service.saveZzzodAppConfigApiApiScriptsZzzodAppConfigSavePost>
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'ZzzOd', operation_kind: 'save', engine_kind: 'unknown' },
      () => Service.saveZzzodAppConfigApiApiScriptsZzzodAppConfigSavePost(...args),
      apiOutcome
    )
  static override addZzzodInstanceApiApiScriptsZzzodInstancesAddPost = (
    ...args: Parameters<typeof Service.addZzzodInstanceApiApiScriptsZzzodInstancesAddPost>
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'ZzzOd', operation_kind: 'instance_add', engine_kind: 'unknown' },
      () => Service.addZzzodInstanceApiApiScriptsZzzodInstancesAddPost(...args),
      apiOutcome
    )
  static override deleteZzzodInstanceApiApiScriptsZzzodInstancesDeletePost = (
    ...args: Parameters<typeof Service.deleteZzzodInstanceApiApiScriptsZzzodInstancesDeletePost>
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'ZzzOd', operation_kind: 'instance_delete', engine_kind: 'unknown' },
      () => Service.deleteZzzodInstanceApiApiScriptsZzzodInstancesDeletePost(...args),
      apiOutcome
    )
  static override cleanZzzodSlotsApiApiScriptsZzzodSlotsCleanPost = (
    ...args: Parameters<typeof Service.cleanZzzodSlotsApiApiScriptsZzzodSlotsCleanPost>
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'ZzzOd', operation_kind: 'instance_delete', engine_kind: 'unknown' },
      () => Service.cleanZzzodSlotsApiApiScriptsZzzodSlotsCleanPost(...args),
      apiOutcome
    )
  static override clearZzzodRecycleApiApiScriptsZzzodRecycleClearPost = (
    ...args: Parameters<typeof Service.clearZzzodRecycleApiApiScriptsZzzodRecycleClearPost>
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'ZzzOd', operation_kind: 'instance_delete', engine_kind: 'unknown' },
      () => Service.clearZzzodRecycleApiApiScriptsZzzodRecycleClearPost(...args),
      apiOutcome
    )
  static override restoreZzzodRecycleApiApiScriptsZzzodRecycleRestorePost = (
    ...args: Parameters<typeof Service.restoreZzzodRecycleApiApiScriptsZzzodRecycleRestorePost>
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'ZzzOd', operation_kind: 'import', engine_kind: 'unknown' },
      () => Service.restoreZzzodRecycleApiApiScriptsZzzodRecycleRestorePost(...args),
      apiOutcome
    )
  static override parseMaaCultivateImportApiScriptsMaaCultivateImportPost = (
    ...args: Parameters<typeof Service.parseMaaCultivateImportApiScriptsMaaCultivateImportPost>
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'MAA', operation_kind: 'preview', engine_kind: 'unknown' },
      () => Service.parseMaaCultivateImportApiScriptsMaaCultivateImportPost(...args),
      apiOutcome
    )
}

export class BetterGISetupService extends BetterGiService {
  static override saveBettergiScriptGroupApiApiScriptsBettergiScriptGroupSavePost = (
    ...args: Parameters<
      typeof BetterGiService.saveBettergiScriptGroupApiApiScriptsBettergiScriptGroupSavePost
    >
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'BetterGI', operation_kind: 'save', engine_kind: 'unknown' },
      () =>
        BetterGiService.saveBettergiScriptGroupApiApiScriptsBettergiScriptGroupSavePost(...args),
      apiOutcome
    )
}

export class OkNteSetupService extends OknteService {
  static override batchUpdateOknteConfigsApiScriptsOknteConfigsBatchUpdatePost = (
    ...args: Parameters<
      typeof OknteService.batchUpdateOknteConfigsApiScriptsOknteConfigsBatchUpdatePost
    >
  ) =>
    observeFeature(
      'adapter_setup_finished',
      { script_type: 'OkNte', operation_kind: 'save', engine_kind: 'unknown' },
      () => OknteService.batchUpdateOknteConfigsApiScriptsOknteConfigsBatchUpdatePost(...args),
      apiOutcome
    )
}

/** 导入实例后的界面刷新仍由用户页负责。 */
export async function importZzzodInstance(
  input: Parameters<typeof Service.importZzzodConfigApiApiScriptsZzzodImportPost>[0]
) {
  const result = await AdapterSetupService.importZzzodConfigApiApiScriptsZzzodImportPost(input)
  if (result.code !== 200) throw new Error(result.message || t('edit.zzzodImportFailed'))
}
