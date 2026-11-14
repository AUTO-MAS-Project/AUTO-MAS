import { computed, type ComputedRef } from 'vue'
import { useQueries } from '@tanstack/vue-query'
import { useI18n } from 'vue-i18n'
import { Service, PlanComboxIn, type ComponentHint } from '@/api'
import { requestApi, apiErrorMessage } from '@/utils/apiResult'

type Option = { value: string; label: string }

/** 声明式选项复用 QueryClient；目标和依赖变化时切换查询身份。 */
export function useDeclarativeOptions(
  target: ComputedRef<{
    uid: string
    ui: { hints?: Record<string, ComponentHint[]> }
    [key: string]: unknown
  }>
) {
  // 从配置 UI 声明建立依赖感知的选项查询，统一提供控件选项、加载错误与重试入口。
  const { t } = useI18n()
  const declarations = computed(() =>
    /* 根据当前配置和 UI 提示生成需要动态加载选项的字段声明。 */ Object.entries(
      target.value.ui.hints ?? {}
    ).flatMap(([section, hints]) =>
      /* 收集当前分组中带选项接口的字段，并读取其依赖值。 */ hints
        .filter(
          hint => /* 只保留同时声明字段名称和动态选项接口的控件提示。 */ hint.field && hint.endpoint
        )
        .map(hint => /* 将控件提示转换为字段键、接口地址与当前依赖值，供查询缓存使用。 */ ({
          key: `${section}.${hint.field}`,
          endpoint: hint.endpoint!,
          dependencies: (hint.deps ?? []).map(path =>
            /* 按声明的点分路径读取一个依赖值，供级联下拉框更新查询条件。 */ path
              .split('.')
              .reduce<unknown>(
                (value, part) =>
                  /* 逐层读取依赖路径，遇到不存在的对象时返回空值。 */ value &&
                  typeof value === 'object'
                    ? (value as Record<string, unknown>)[part]
                    : undefined,
                target.value
              )
          ),
        }))
    )
  )
  const queries = useQueries({
    queries: computed(() =>
      /* 按当前字段及依赖生成 Vue Query 配置，使关联字段变化时重新查询选项。 */ declarations.value.map(
        field => /* 为一个字段设置包含配置身份和依赖的缓存键，并绑定选项加载函数。 */ ({
          queryKey: [
            'plugins',
            'field-options',
            target.value.uid,
            field.endpoint,
            field.dependencies,
          ],
          queryFn: async (): Promise<Option[]> => {
            // 按声明的宿主接口加载游戏、设备、模拟器或计划选项，规范化返回值并过滤无效关联项。
            const fallback = t('core.scripts.optionsLoadFailed')
            let response
            switch (field.endpoint) {
              case '/api/plugin/options/games':
                response = await requestApi(
                  () =>
                    /* 调用生成的插件游戏选项接口，复用统一请求错误处理。 */ Service.pluginGameOptionsApiPluginOptionsGamesPost(),
                  fallback
                )
                break
              case '/api/plugin/options/devices': {
                const gameId = field.dependencies[0]
                if (!gameId || gameId === '-') return []
                response = await requestApi(
                  () =>
                    /* 使用当前关联游戏标识查询其设备选项。 */ Service.pluginDeviceOptionsApiPluginOptionsDevicesPost(
                      {
                        gameId: String(gameId),
                      }
                    ),
                  fallback
                )
                break
              }
              case '/api/plugin/options/plans':
                response = await requestApi(
                  () =>
                    /* 查询插件计划配置的可关联选项。 */ Service.pluginPlanOptionsApiPluginOptionsPlansPost(),
                  fallback
                )
                break
              case '/api/info/combox/emulator':
                response = await requestApi(
                  () =>
                    /* 查询宿主已有模拟器选项，供测试插件复用现有模拟器模块。 */ Service.getEmulatorComboxApiInfoComboxEmulatorPost(),
                  fallback
                )
                break
              case '/api/info/combox/emulator/devices': {
                const gameId = field.dependencies[0]
                if (!gameId || gameId === '-') return []
                response = await requestApi(
                  () =>
                    /* 按所选模拟器标识查询其设备实例选项。 */ Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost(
                      {
                        emulatorId: String(gameId),
                      }
                    ),
                  fallback
                )
                break
              }
              case '/api/info/combox/plan':
                response = await requestApi(
                  () =>
                    /* 以通用计划消费者身份读取宿主计划选项。 */ Service.getPlanComboxApiInfoComboxPlanPost(
                      {
                        consumer: PlanComboxIn.consumer.UNIVERSAL,
                      }
                    ),
                  fallback
                )
                break
              default:
                throw new Error(
                  t('core.scripts.unsupportedOptionsEndpoint', { endpoint: field.endpoint })
                )
            }
            return (response.data ?? [])
              .filter(
                item =>
                  /* 移除空标识及接口占位项，避免与前端统一的无关联选项重复。 */ item.value !=
                    null && item.value !== '-'
              )
              .map(
                item => /* 将返回的选项标识规范化为字符串，并为缺少名称的条目使用标识作标签。 */ ({
                  value: String(item.value),
                  label: item.label ?? String(item.value),
                })
              )
          },
        })
      )
    ),
  })
  const queryFor = (section: string, hint: ComponentHint) => {
    // 按配置分组和字段定位其当前选项查询状态。
    const index = declarations.value.findIndex(
      field => /* 在动态字段声明中匹配当前分组与字段键。 */ field.key === `${section}.${hint.field}`
    )
    return queries.value[index]
  }
  const stateFor = (section: string, hint: ComponentHint) => {
    // 将字段查询状态转换为配置控件使用的加载、错误及重试能力。
    const query = queryFor(section, hint)
    return query
      ? {
          error: {
            value: query.error
              ? apiErrorMessage(query.error, t('core.scripts.optionsLoadFailed'))
              : null,
          },
          loading: { value: query.isFetching },
          execute: () => /* 重新请求当前字段的动态选项。 */ query.refetch(),
        }
      : undefined
  }
  const optionsFor = (section: string, hint: ComponentHint): Option[] =>
    /* 返回动态或静态控件选项，动态选项统一添加无关联占位。 */ hint.endpoint
      ? [
          { value: '-', label: t('core.scripts.noAssociation') },
          ...(queryFor(section, hint)?.data ?? []),
        ]
      : (hint.options ?? []).map(
          option => /* 把声明中的静态选项转换为控件可直接使用的字符串标识与标签。 */ ({
            value: String(option.value),
            label: option.label ?? String(option.value),
          })
        )
  return { stateFor, optionsFor }
}
