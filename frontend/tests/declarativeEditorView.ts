import { defineComponent, h } from 'vue'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { VueQueryPlugin, type QueryClient } from '@tanstack/vue-query'
import { genericEditorRoutes } from '@/router/scriptEditorRoutes'
import { fire, testView } from './vueRenderer'

/** 走真实路由、表单和锁，AntD 控件在 Node 渲染器中保留插槽和事件。 */
export async function editorView(path: string, client: QueryClient) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...genericEditorRoutes,
      { path: '/scripts', name: 'Scripts', component: { render: () => null } },
    ],
  })
  await router.push(path)
  const view = testView(defineComponent(() => () => h(RouterView)))
  view.stub({
    ABreadcrumb: 'nav',
    ABreadcrumbItem: 'span',
    AButton: 'button',
    ASteps: 'steps',
    AInput: 'input',
    AInputNumber: 'input',
    ASelect: 'select',
    AFlex: 'div',
    ASpace: 'div',
    ASpin: 'div',
    AAlert: 'aside',
  })
  view.app
    .use(router)
    .use(VueQueryPlugin, { queryClient: client })
    .use(
      createI18n({
        legacy: false,
        locale: 'en',
        missingWarn: false,
        fallbackWarn: false,
      })
    )
  const click = (label: string) => fire(view.find('button', label)!, 'onClick')
  return { ...view, router, click }
}
