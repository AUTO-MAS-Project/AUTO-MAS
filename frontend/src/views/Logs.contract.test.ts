import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const viewSource = readFileSync(fileURLToPath(new URL('./Logs.vue', import.meta.url)), 'utf8')
const toolbarSource = readFileSync(
  fileURLToPath(new URL('./Logs/components/LogToolbar.vue', import.meta.url)),
  'utf8'
)
const listSource = readFileSync(
  fileURLToPath(new URL('./Logs/components/LogLineList.vue', import.meta.url)),
  'utf8'
)
const viewerSource = readFileSync(
  fileURLToPath(new URL('./Logs/useLogViewer.ts', import.meta.url)),
  'utf8'
)

describe('Logs feature fidelity and macOS UI contract', () => {
  it('preserves source switching, refresh, follow, copy and export capabilities', () => {
    expect(toolbarSource).toContain("value: 'app'")
    expect(toolbarSource).toContain("value: 'frontend'")
    expect(toolbarSource).toContain("emit('update:source'")
    expect(toolbarSource).toContain("$emit('refresh')")
    expect(toolbarSource).toContain("$emit('toggle-realtime')")
    expect(toolbarSource).toContain("$emit('toggle-pause')")
    expect(toolbarSource).toContain("$emit('copy')")
    expect(toolbarSource).toContain("$emit('export')")
    expect(viewerSource).toContain('getLogs?.(linesToRead, fileName.value)')
    expect(viewerSource).toContain('startRealtime')
    expect(viewerSource).toContain('stopRealtime')
    expect(viewerSource).toContain('showItemInFolder')
    expect(viewerSource).toContain('navigator.clipboard.writeText')
  })

  it('provides search, level filtering, timestamp highlighting and safe view clearing', () => {
    expect(toolbarSource).toContain('v-model:value="localKeyword"')
    expect(toolbarSource).toContain('v-model:value="localLevel"')
    expect(viewerSource).toContain('LEVEL_PATTERNS')
    expect(listSource).toContain('TIMESTAMP_RE')
    expect(listSource).toContain('LEVEL_RE')
    expect(listSource).toContain('log-line__keyword')
    expect(toolbarSource).toContain('清空视图')
    expect(toolbarSource).toContain('不删除磁盘日志')
    expect(viewerSource).toContain('const clearView')
    expect(viewerSource).not.toContain('clearLogs')
  })

  it('keeps explicit loading, empty, error and reconnecting states', () => {
    expect(viewSource).toContain('<a-spin')
    expect(viewSource).toContain('<EmptyState')
    expect(viewSource).toContain('<ErrorState')
    expect(viewSource).toContain('connectionState ===')
    expect(viewSource).toContain('@click="retry"')
    expect(viewerSource).toContain("connectionState.value = 'disconnected'")
    expect(viewerSource).toContain("connectionState.value = 'reconnecting'")
  })

  it('uses one frosted panel without a framed log list inside it', () => {
    expect(viewSource).toContain('<PageHeader')
    expect(viewSource).toContain('class="logs-panel"')
    expect(viewSource).toMatch(/\.logs-panel\s*\{[^}]*backdrop-filter:\s*blur/s)
    expect(toolbarSource).not.toContain('<h1')
    expect(listSource).toMatch(/\.log-line-list\s*\{[^}]*border:\s*0/s)
    expect(listSource).toMatch(/\.log-line-list\s*\{[^}]*background:\s*transparent/s)
  })
})
