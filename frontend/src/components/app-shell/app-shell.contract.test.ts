import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const componentDir = __dirname

const readComponent = (name: string): string => {
  return readFileSync(resolve(componentDir, name), 'utf-8')
}

const readParentComponent = (name: string): string => {
  return readFileSync(resolve(componentDir, '..', name), 'utf-8')
}

describe('App Shell 组件契约检查', () => {
  describe('TitleBar.vue 旧版功能保真', () => {
    const source = readParentComponent('TitleBar.vue')

    it('保留最小化、最大化/还原与关闭确认链路', () => {
      expect(source).toContain('window.electronAPI?.windowMinimize()')
      expect(source).toContain('window.electronAPI?.windowMaximize()')
      expect(source).toContain('window.electronAPI?.windowIsMaximized()')
      expect(source).toContain('hasRunningTasks()')
      expect(source).toContain("title: '确认关闭'")
      expect(source).toContain('await closeApp()')
    })

    it('保留应用更新、下载进度与后端更新入口', () => {
      expect(source).toContain('downloadHint')
      expect(source).toContain('showUpdateModal')
      expect(source).toContain('handleBackendUpdateClick')
      expect(source).toContain("sessionStorage.setItem('forceBackendUpdate', 'true')")
      expect(source).toContain("router.push('/initialization')")
    })

    it('把隐藏关闭键和窗口事件原样传给拆分后的控制组件', () => {
      expect(source).toContain(':hide-close-button="hideCloseButton"')
      expect(source).toContain('@minimize="minimizeWindow"')
      expect(source).toContain('@toggle-maximize="toggleMaximize"')
      expect(source).toContain('@close="closeWindow"')
    })

    it('在原生标题栏持续显示当前构建版本', () => {
      expect(source).toContain('import.meta.env.VITE_APP_VERSION')
      expect(source).toContain('`AUTO-MAS · ${appVersion}`')
    })
  })

  describe('AppSider.vue', () => {
    const source = readComponent('AppSider.vue')

    it('使用 script setup lang="ts" 与 scoped styles', () => {
      expect(source).toContain('<script setup lang="ts">')
      expect(source).toContain('<style scoped>')
    })

    it('声明导航 role 与 aria-label', () => {
      expect(source).toContain('role="navigation"')
      expect(source).toContain('aria-label="应用侧边导航"')
    })

    it('折叠按钮具备 aria-label、aria-expanded、aria-controls', () => {
      expect(source).toContain(":aria-label=\"collapsed ? '展开侧边栏' : '折叠侧边栏'\"")
      expect(source).toContain(':aria-expanded="!collapsed"')
      expect(source).toContain('aria-controls="app-sider"')
    })

    it('支持 Ctrl+B / Cmd+B 键盘快捷键', () => {
      expect(source).toContain("event.key.toLowerCase() === 'b'")
      expect(source).toContain('event.ctrlKey || event.metaKey')
    })

    it('使用 v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
    })

    it('尊重 prefers-reduced-motion', () => {
      expect(source).toContain('prefers-reduced-motion')
    })
  })

  describe('AppSiderMenu.vue', () => {
    const source = readComponent('AppSiderMenu.vue')

    it('使用 script setup lang="ts" 与 scoped styles', () => {
      expect(source).toContain('<script setup lang="ts">')
      expect(source).toContain('<style scoped>')
    })

    it('包裹在 nav 元素中并具备 aria-label', () => {
      expect(source).toContain('<nav')
      expect(source).toContain(':aria-label="sectionLabel')
    })

    it('使用 Ant Design Vue Menu 并支持折叠', () => {
      expect(source).toContain('<a-menu')
      expect(source).toContain(':inline-collapsed="collapsed"')
    })

    it('为菜单项提供焦点环', () => {
      expect(source).toContain('.ant-menu-item:focus-visible')
    })

    it('尊重 prefers-reduced-motion', () => {
      expect(source).toContain('prefers-reduced-motion')
    })
  })

  describe('AppContentArea.vue', () => {
    const source = readComponent('AppContentArea.vue')

    it('主内容区具备可聚焦的 id 与 aria-label', () => {
      expect(source).toContain('id="app-main-content"')
      expect(source).toContain('aria-label="主内容区"')
      expect(source).toContain('tabindex="-1"')
    })

    it('使用 v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
    })

    it('尊重 prefers-reduced-motion', () => {
      expect(source).toContain('prefers-reduced-motion')
    })
  })

  describe('AppBackgroundLayer.vue', () => {
    const source = readComponent('AppBackgroundLayer.vue')

    it('背景层标记为 aria-hidden', () => {
      expect(source).toContain('aria-hidden="true"')
    })

    it('使用 v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
    })
  })

  describe('TitleBarBrand.vue', () => {
    const source = readComponent('TitleBarBrand.vue')

    it('包含应用标识 aria-label', () => {
      expect(source).toContain('aria-label="AUTO-MAS 应用标识"')
    })

    it('版本文本具备 aria-label', () => {
      expect(source).toContain('aria-label="当前版本"')
    })

    it('保留拖拽区域', () => {
      expect(source).toContain('-webkit-app-region: drag')
    })
  })

  describe('TitleBarStatus.vue', () => {
    const source = readComponent('TitleBarStatus.vue')

    it('使用 role="status" 与 aria-live', () => {
      expect(source).toContain('role="status"')
      expect(source).toContain('aria-live="polite"')
    })

    it('可点击更新提示具备 role="button"、tabindex 与键盘事件', () => {
      expect(source).toContain('role="button"')
      expect(source).toContain('tabindex="0"')
      expect(source).toContain('@keydown.enter.prevent')
      expect(source).toContain('@keydown.space.prevent')
    })

    it('使用 v6 design tokens', () => {
      expect(source).toContain('var(--v6-')
    })
  })

  describe('TitleBarControls.vue', () => {
    const source = readComponent('TitleBarControls.vue')

    it('窗口控制按钮具备 aria-label', () => {
      expect(source).toContain('aria-label="最小化"')
      expect(source).toContain(':aria-label="maximizeLabel"')
      expect(source).toContain('aria-label="关闭"')
    })

    it('按钮禁用拖拽并具备焦点环', () => {
      expect(source).toContain('-webkit-app-region: no-drag')
      expect(source).toContain('.control-button:focus')
      expect(source).toContain(':focus-visible')
      expect(source).toContain('box-shadow: var(--v6-focus-ring-inset)')
      expect(source).not.toContain('box-shadow: var(--v6-focus-ring)')
    })

    it('使用右侧紧凑磨砂分组与 traffic-light 语义色', () => {
      expect(source).toContain('role="group"')
      expect(source).toContain('border-radius: 999px')
      expect(source).toContain('backdrop-filter: blur(12px)')
      expect(source).toContain('var(--v6-color-warning)')
      expect(source).toContain('var(--v6-color-success)')
      expect(source).toContain('var(--v6-color-error)')
      expect(source).not.toContain('#e81123')
      expect(source).not.toContain('width: 46px')
    })

    it('尊重 prefers-reduced-motion', () => {
      expect(source).toContain('prefers-reduced-motion')
    })
  })
})
