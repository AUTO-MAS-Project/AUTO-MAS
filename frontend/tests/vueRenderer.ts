import { createRenderer, defineComponent, h, nextTick, type Component } from 'vue'
import { CancelablePromise } from '@/api/core/CancelablePromise'

export function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: Error) => void
  const promise = new CancelablePromise<T>((ok, fail) => {
    resolve = ok
    reject = fail
  })
  return { promise, resolve, reject }
}

export interface TestNode {
  tag: string
  text: string
  props: Record<string, unknown>
  children: TestNode[]
  parent: TestNode | null
  style: { display: string }
}

const node = (tag: string, text = ''): TestNode => ({
  tag,
  text,
  props: {},
  children: [],
  parent: null,
  style: { display: '' },
})
function remove(el: TestNode) {
  if (el.parent) el.parent.children.splice(el.parent.children.indexOf(el), 1)
  el.parent = null
}
const renderer = createRenderer<TestNode, TestNode>({
  createElement: tag => node(tag),
  createText: value => node('#text', value),
  createComment: () => node('#comment'),
  setText: (el, value) => {
    el.text = value
  },
  setElementText: (el, value) => {
    el.children = []
    el.text = value
  },
  patchProp: (el, key, _, value) => {
    el.props[key] = value
  },
  parentNode: el => el.parent,
  nextSibling: el => el.parent?.children[el.parent.children.indexOf(el) + 1] ?? null,
  remove,
  insert(el, parent, anchor) {
    remove(el)
    parent.children.splice(anchor ? parent.children.indexOf(anchor) : parent.children.length, 0, el)
    el.parent = parent
  },
})

export function testView(component: Component) {
  const app = renderer.createApp(component)
  const root = node('root')
  function all(el: TestNode = root): TestNode[] {
    return [el, ...el.children.flatMap(child => all(child))]
  }
  const text = (el: TestNode = root): string => el.text + el.children.map(text).join('')
  const find = (tag: string, label?: string) =>
    all().find(el => el.tag === tag && (label === undefined || text(el).trim() === label))
  function stub(tags: Record<string, string>) {
    for (const [name, tag] of Object.entries(tags))
      app.component(
        name,
        defineComponent(
          (_, { slots }) =>
            () =>
              h(tag, slots.default?.())
        )
      )
  }
  return { app, mount: () => app.mount(root), all, text, find, stub }
}

export async function fire(el: TestNode, event: string, ...values: unknown[]) {
  const handler = el.props[event]
  if (typeof handler !== 'function') throw new Error(`Missing ${event} on ${el.tag}`)
  handler(...values)
  await nextTick()
}
