// 页面宿主（MaaFWPageHost）交给页面的上下文。单独成文件：页面的编排层要取它，而宿主模块
// 会按需引入页面，放在一起就成环了。
import { hasInjectionContext, inject, type InjectionKey, type Ref } from 'vue'
import type { MaaFWPageKind } from '@/router/maafwRoutes'
import type { ScriptDetail, ScriptType } from '@/types/script'

export interface MaaFWPageHostContext {
  /**
   * 宿主读到的脚本类型，宿主按它选了渲染哪个页面。托管类型在新建时就定了（导入不换类型），
   * 页面只读它作初值。
   */
  scriptType: Readonly<Ref<ScriptType>>
  /** 页面种类（路由 meta.maafwPage）：脚本页看它是不是引导 */
  mode: MaaFWPageKind
  /** 宿主初次读取已提示的失败；子页不为同一次失败重复弹出提示。 */
  scriptLoadError: Readonly<Ref<string | null>>
  /**
   * 宿主已经读到的脚本详情，只交给第一个来取的页面（之后返回 undefined）：
   * - 脚本详情：直接用，不再请求一次；
   * - null：读过了但没读到（脚本不存在或读取失败，getScript 已经提示过），按页面现有的报错处理；
   * - undefined：宿主没有可交的，页面自己去读。
   */
  takeInitialScript: () => ScriptDetail | null | undefined
}

export const MAAFW_PAGE_HOST_KEY: InjectionKey<MaaFWPageHostContext> = Symbol('MaaFWPageHost')

/** 页面里取宿主上下文；不在宿主里（单测直接调编排层）时为 null，页面按自己读路由的老办法走 */
export const useMaaFWPageHostContext = (): MaaFWPageHostContext | null =>
  hasInjectionContext() ? inject(MAAFW_PAGE_HOST_KEY, null) : null
