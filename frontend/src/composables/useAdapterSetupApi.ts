import { Service, OknteService } from '@/api'
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
