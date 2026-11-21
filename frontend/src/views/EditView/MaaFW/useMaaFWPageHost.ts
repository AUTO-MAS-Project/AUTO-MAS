import {
  defineAsyncComponent,
  onScopeDispose,
  provide,
  readonly,
  ref,
  shallowRef,
  type Component,
} from 'vue'
import { useRoute, useRouter, type RouteRecordRaw } from 'vue-router'
import { isMaaFWFamily, resolveMaaFWAdapter } from '@/plugins/maafwFamily'
import { useScriptApi } from '@/composables/useScriptApi'
import { resolveMaaFWCanonicalLocation, type MaaFWPageKind } from '@/router/maafwRoutes'
import type { ScriptDetail, ScriptType } from '@/types/script'
import { MAAFW_PAGE_HOST_KEY, type MaaFWPageHostContext } from './pageHostContext'

/** 页面种类 → 渲染适配条目 editors 里的哪一页 */
const PAGE_EDITOR = {
  script: 'script',
  setup: 'script',
  userAdd: 'user',
  userEdit: 'user',
} as const satisfies Record<MaaFWPageKind, 'script' | 'user'>

type EditorPart = (typeof PAGE_EDITOR)[MaaFWPageKind]
type LazyPage = Extract<RouteRecordRaw, { component: unknown }>['component']

/** 按需加载的页面：渲染用的异步组件 + 同一个加载函数（读脚本期间预取，首屏不闪） */
interface MaaFWHostPage {
  component: Component
  load: () => Promise<unknown>
}

// editors 里是加载函数（() => import(...)）或现成的组件；判别法照 vue-router 对懒加载路由组件的判断
const isPageLoader = (page: LazyPage): page is () => Promise<Component> =>
  typeof page === 'function' &&
  !('displayName' in page) &&
  !('props' in page) &&
  !('emits' in page) &&
  !('__vccOpts' in page)

/**
 * 按类型与页面缓存的异步组件：模块级，同一类型的同一页始终是同一个组件引用，预取与渲染共用
 * 同一个加载函数。
 */
const PAGE_CACHE = new Map<string, MaaFWHostPage>()

const resolveHostPage = (type: ScriptType | string | null | undefined, part: EditorPart) => {
  const adapter = resolveMaaFWAdapter(type)
  const key = `${adapter.type}:${part}`
  const cached = PAGE_CACHE.get(key)
  if (cached) return cached
  const editor = adapter.editors[part]
  const load = isPageLoader(editor) ? editor : async () => editor
  const page: MaaFWHostPage = { component: defineAsyncComponent(load), load }
  PAGE_CACHE.set(key, page)
  return page
}

/**
 * MaaFW 家族路由的页面宿主：按脚本实际类型选页面（适配条目的 editors）。
 *
 * 1. 读路由的页面种类与参数，读脚本详情，同时预取通用 MFW 页的 chunk；
 * 2. 路由登记的类型与脚本实际类型不符：replace 到实际类型那条线（同一种页面、参数 / query / hash
 *    照带），自己什么都不渲染——路径一变 AppLayout 就整个重建，页面逻辑只在纠正后的实例里跑，
 *    所以加用户的地址写错也只建一个用户；
 * 3. 脚本不存在 / 读取失败 / 不是 MaaFW 家族：照常渲染通用 MFW 页，由页面给出现有的报错；
 * 4. 否则把上下文（脚本类型、页面种类、读到的脚本详情）交给页面，渲染该类型的页面。
 *    托管类型在新建时就定了，导入不换类型，所以页面选定后不再换。
 */
export function useMaaFWPageHost() {
  const logger = window.electronAPI.getLogger('MaaFW 页面宿主')
  const route = useRoute()
  const router = useRouter()
  const { getScript, error: scriptLoadError } = useScriptApi()

  // 宿主实例只对应一个地址（路径一变 AppLayout 就重建），这里取下当时的路由快照
  const mode: MaaFWPageKind = route.meta.maafwPage ?? 'script'
  const part = PAGE_EDITOR[mode]
  const snapshot = {
    meta: route.meta,
    params: { ...route.params },
    query: { ...route.query },
    hash: route.hash,
  }
  const hostPath = route.fullPath
  const scriptIdParam = part === 'script' ? route.params.id : route.params.scriptId
  const scriptId = Array.isArray(scriptIdParam) ? (scriptIdParam[0] ?? '') : (scriptIdParam ?? '')

  // 读到 MaaFW 家族的脚本后换成它的实际类型；读不到时与页面原来一样从通用 MaaFW 起步
  const scriptType = ref<ScriptType>('MaaFW')
  let initialScript: ScriptDetail | null | undefined

  const context: MaaFWPageHostContext = {
    scriptType: readonly(scriptType),
    mode,
    scriptLoadError,
    takeInitialScript: () => {
      const script = initialScript
      initialScript = undefined
      return script
    },
  }
  provide(MAAFW_PAGE_HOST_KEY, context)

  /** 要渲染的页面；还没读到脚本或正在纠正地址时为 null，选定后不再换 */
  const page = shallowRef<Component | null>(null)

  let disposed = false
  onScopeDispose(() => {
    disposed = true
  })

  const prefetch = (entry: MaaFWHostPage) => {
    void (async () => entry.load())().catch(error => {
      logger.warn(`预取页面失败: ${error instanceof Error ? error.message : String(error)}`)
    })
  }

  const show = (script: ScriptDetail | null | undefined) => {
    if (script && isMaaFWFamily(script.type)) scriptType.value = script.type
    initialScript = script
    page.value = resolveHostPage(scriptType.value, part).component
  }

  const load = async () => {
    // 先预取通用 MFW 页（读不到脚本时也渲染它）
    prefetch(resolveHostPage('MaaFW', part))
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

  return { page, scriptType, mode, loaded }
}
