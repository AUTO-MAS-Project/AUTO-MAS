import { computed, onScopeDispose, provide, ref, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  MAAFW_PAGE_PART,
  defineMaaFWLazyComponent,
  type MaaFWLazyComponent,
  type MaaFWPageKind,
  type MaaFWPagePart,
} from '@/composables/maafwFlavorTypes'
import { isMaaFWFamily, resolveMaaFWFlavor } from '@/composables/useMaaFWFlavor'
import { useScriptApi } from '@/composables/useScriptApi'
import { resolveMaaFWCanonicalLocation } from '@/router/maafwFlavorRoutes'
import type { ScriptDetail, ScriptType } from '@/types/script'
import { MAAFW_PAGE_HOST_KEY, type MaaFWPageHostContext } from './pageHostContext'

/**
 * MFW 的默认页面：模块级常量，同一个异步组件引用——类型在默认页之间变（MaaFW ↔ 没有整页替换的
 * 特调）时宿主渲染的还是同一个组件，页面不重建，引导进度不丢。
 */
export const MAAFW_DEFAULT_PAGES: Record<MaaFWPagePart, MaaFWLazyComponent> = {
  scriptPage: defineMaaFWLazyComponent(() => import('../Script/MaaFWScriptEdit.vue')),
  userPage: defineMaaFWLazyComponent(() => import('../User/MaaFWUserEdit.vue')),
}

/**
 * MaaFW 家族路由的页面宿主：按脚本实际类型选页面。
 *
 * 1. 读路由的页面种类与参数，读脚本详情，同时预取默认页的 chunk；
 * 2. 路由登记的类型与脚本实际类型不符：replace 到实际类型那条线（同一种页面、参数 / query / hash
 *    照带），自己什么都不渲染——路径一变 AppLayout 就整个重建，页面逻辑只在纠正后的实例里跑，
 *    所以加用户的地址写错也只建一个用户；
 * 3. 脚本不存在 / 读取失败 / 不是 MaaFW 家族：照常渲染默认页，由页面给出现有的报错；
 * 4. 否则把上下文（脚本类型、页面种类、引导步骤、读到的脚本详情）交给页面，渲染该类型的整页替换，
 *    没有就渲染默认页。之后类型变了（导入后后端换类型，页面写回 scriptType）就地换页面，不改地址。
 */
export function useMaaFWPageHost(
  pages: Record<MaaFWPagePart, MaaFWLazyComponent> = MAAFW_DEFAULT_PAGES
) {
  const logger = window.electronAPI.getLogger('MaaFW 页面宿主')
  const route = useRoute()
  const router = useRouter()
  const { getScript } = useScriptApi()

  // 宿主实例只对应一个地址（路径一变 AppLayout 就重建），这里取下当时的路由快照
  const mode: MaaFWPageKind = route.meta.maafwPage ?? 'script'
  const part = MAAFW_PAGE_PART[mode]
  const snapshot = {
    meta: route.meta,
    params: { ...route.params },
    query: { ...route.query },
    hash: route.hash,
  }
  const hostPath = route.fullPath
  const scriptIdParam = part === 'scriptPage' ? route.params.id : route.params.scriptId
  const scriptId = Array.isArray(scriptIdParam) ? (scriptIdParam[0] ?? '') : (scriptIdParam ?? '')

  // 读到 MaaFW 家族的脚本后换成它的实际类型；读不到时与页面原来一样从通用 MaaFW 起步
  const scriptType = ref<ScriptType>('MaaFW')
  const wizardStep = ref(0)
  const ready = ref(false)
  let initialScript: ScriptDetail | null | undefined

  const context: MaaFWPageHostContext = {
    scriptType,
    mode,
    wizardStep,
    takeInitialScript: () => {
      const script = initialScript
      initialScript = undefined
      return script
    },
  }
  provide(MAAFW_PAGE_HOST_KEY, context)

  /** 要渲染的页面；还没读到脚本或正在纠正地址时为 null */
  const page = computed<Component | null>(() => {
    if (!ready.value) return null
    return resolveMaaFWFlavor(scriptType.value)[part].page?.component ?? pages[part].component
  })

  let disposed = false
  onScopeDispose(() => {
    disposed = true
  })

  const prefetch = (entry: MaaFWLazyComponent | null | undefined) => {
    if (!entry) return
    void (async () => entry.load())().catch(error => {
      logger.warn(`预取页面失败: ${error instanceof Error ? error.message : String(error)}`)
    })
  }

  const show = (script: ScriptDetail | null | undefined) => {
    if (script && isMaaFWFamily(script.type)) {
      scriptType.value = script.type
      prefetch(resolveMaaFWFlavor(script.type)[part].page)
    }
    initialScript = script
    ready.value = true
  }

  const load = async () => {
    prefetch(pages[part])
    let script: ScriptDetail | null | undefined
    try {
      script = await getScript(scriptId)
    } catch (error) {
      // getScript 自己兜住了请求错误（返回 null）；走到这里的交给页面自己再读一次
      logger.warn(`读取脚本详情失败: ${error instanceof Error ? error.message : String(error)}`)
      script = undefined
    }
    if (disposed) return

    const target = script ? resolveMaaFWCanonicalLocation(snapshot, script.type) : null
    if (target) {
      logger.info(
        `路由登记的类型 ${String(snapshot.meta.scriptType)} 与脚本实际类型 ${script!.type} 不符，纠正到 ${target.name}`
      )
      let failure: unknown
      try {
        failure = await router.replace(target)
      } catch (error) {
        failure = error
      }
      // 纠正没走成（导航被拦 / 出错）而且还停在这个地址：按实际类型照常渲染，别留一页空白。
      // 已经去了别处（被别的导航顶掉）就什么都不做，这个实例马上会被卸掉
      if (failure && !disposed && router.currentRoute.value.fullPath === hostPath) {
        logger.warn(`纠正路由失败: ${failure instanceof Error ? failure.message : String(failure)}`)
        show(script)
      }
      return
    }
    show(script)
  }

  const loaded = load()

  return { page, scriptType, wizardStep, mode, loaded }
}
