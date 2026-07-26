import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const testDir = dirname(fileURLToPath(import.meta.url))
const readView = (name: string) => readFileSync(resolve(testDir, name), 'utf-8')

describe('游戏与模拟器中心功能保真和视觉契约', () => {
  const indexSource = readView('index.vue')
  const gamesSource = readView('GameInstancesTab.vue')
  const emulatorSource = readView('EmulatorTab.vue')

  it('顶层使用紧凑 segmented control，而不是 card tabs', () => {
    expect(indexSource).toContain('<a-segmented')
    expect(indexSource).not.toContain('type="card"')
    expect(indexSource).toContain('center-segmented')
  })

  it('游戏卡宽内容区为双列瀑布流、窄内容区降为单列，卡片不再被行等高拉伸', () => {
    expect(gamesSource).toContain('container: game-instances / inline-size')
    // 双列瀑布：multi-column 布局，卡片各自保持内容高度并禁止跨列断裂
    expect(gamesSource).toContain('columns: 2')
    expect(gamesSource).toContain('column-gap: var(--v6-space-4)')
    expect(gamesSource).toContain('break-inside: avoid')
    expect(gamesSource).toContain('margin-bottom: var(--v6-space-4)')
    // 窄内容区退回单列堆叠
    expect(gamesSource).toContain('@container game-instances (max-width: 980px)')
    expect(gamesSource).toContain('columns: 1')
    expect(gamesSource).toContain('@container game-instances (max-width: 1180px)')
    expect(gamesSource).toContain('@container game-instances (max-width: 700px)')
    // 旧的三列等高网格已移除：不再有 repeat(3) 与行内 stretch 拉伸
    expect(gamesSource).not.toContain('grid-template-columns: repeat(3, minmax(0, 1fr))')
    expect(gamesSource).not.toContain('align-items: stretch')
    expect(gamesSource).not.toContain('<a-descriptions')
  })

  it('添加游戏使用与新建脚本一致的预设卡片选择弹窗，而非常驻下拉', () => {
    // 工具栏只保留"添加游戏"按钮，点击后打开预设选择弹窗
    expect(gamesSource).toContain('@click="openPresetPicker"')
    expect(gamesSource).toContain('class="preset-picker-modal"')
    // 弹窗内是网格卡片，点选即创建实例，并带 PC/模拟器平台标签
    expect(gamesSource).toContain('class="preset-grid"')
    expect(gamesSource).toContain('@click="onPickPreset(preset.key)"')
    expect(gamesSource).toContain('preset-platform-tag')
    expect(gamesSource).toContain("preset.platform === 'pc' ? 'PC' : '模拟器'")
    // 复用新建脚本弹窗的卡片视觉结构（choice-copy/choice-title/choice-description）
    expect(gamesSource).toContain('class="choice-copy"')
    expect(gamesSource).toContain('class="choice-title"')
    // 旧的常驻预设下拉已移除
    expect(gamesSource).not.toContain('class="preset-select"')
    expect(gamesSource).not.toContain('v-model:value="selectedPreset"')
  })

  it('游戏、模拟器与实例使用下拉，隐藏 preset 锁定字段和 MaaFW 托管入口', () => {
    expect(gamesSource).toContain('class="game-select"')
    expect(gamesSource).toContain('class="full-control"')
    expect(gamesSource).toContain('deviceOptionsFor')
    expect(gamesSource).toContain('isMaaFWManagedProvider')
    expect(gamesSource).not.toContain("saveValue(game.id, 'Info', 'Provider'")
    expect(gamesSource).not.toContain("saveTextField(game.id, 'Data', 'PackageName'")
    expect(gamesSource).not.toContain("saveTextField(game.id, 'Data', 'AdbPath'")
    expect(gamesSource).not.toContain('pickAdbPath')
    expect(gamesSource).not.toContain('<label class="field-label">启动参数</label>')
    expect(gamesSource).not.toContain('<span class="field-label">运行模式</span>')
    expect(gamesSource).not.toContain('<span class="field-label">Provider</span>')
  })

  it('安装更新只在 provider 声明能力后开放，并展示可恢复进度与真实取消', () => {
    expect(gamesSource).toContain("providerSupports(game.id, 'install_or_update')")
    expect(gamesSource).toContain('taskFor(game.id)?.taskStatus')
    expect(gamesSource).toContain('<a-progress')
    expect(gamesSource).toContain('@click="onInstall(game.id)"')
    expect(gamesSource).toContain('@click="onCancel(game.id)"')
    expect(gamesSource).toContain('loadTaskStatus')
    expect(gamesSource).toContain('setInterval(pollRunningTasks')
    expect(gamesSource).toContain('taskErrorFor(game.id)')
    expect(gamesSource).toContain('onRetryTask(game.id)')
    expect(gamesSource).toContain('stateFor(game.id).saving')
    expect(gamesSource).not.toContain('下载完成')
    expect(gamesSource).not.toContain('更新完成')
  })

  it('模拟器页恢复最后一项删除、空设备启动和类型专属配置', () => {
    expect(emulatorSource).toContain('class="emulator-select"')
    expect(emulatorSource).toContain(':options="emulatorSelectOptions"')
    expect(emulatorSource).not.toContain('type="editable-card"')
    expect(emulatorSource).toContain('@confirm="onDeleteEmulator(emulator.uid)"')
    expect(emulatorSource).not.toContain('emulatorIndex.value.length > 1')
    expect(emulatorSource).toContain('@click="onStartDevice(emulator.uid, \'0\')"')
    expect(emulatorSource).toContain("type !== 'mumu'")
    expect(emulatorSource).toContain("type === 'mumu'")
    expect(emulatorSource).toContain(':max="9999"')
    expect(emulatorSource).toContain('savingMap.get(emulator.uid)')
  })

  it('磨砂卡片使用共享 v6 token 并提供低性能/减少动效降级', () => {
    for (const source of [indexSource, gamesSource, emulatorSource]) {
      expect(source).toContain('var(--v6-color-surface)')
      expect(source).toContain('var(--v6-color-border-subtle)')
    }
    // 两个 Tab 自带磨砂卡片，须各自声明降级；index 页头已换用统一
    // MacPageHeader（降级规则内置在组件里），index 自身不再有动效样式
    for (const source of [gamesSource, emulatorSource]) {
      expect(source).toContain('prefers-reduced-motion')
      expect(source).toContain("data-perf-mode='low'")
    }
    expect(indexSource).toContain('<MacPageHeader')
  })
})
