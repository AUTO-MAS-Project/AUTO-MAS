import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const queuePageSource = readFileSync(
  fileURLToPath(new URL('../index.vue', import.meta.url)),
  'utf8'
)

describe('queue creation flow contract', () => {
  it('requires choosing normal or cycle queue before creation', () => {
    expect(queuePageSource).toContain('title="选择队列类型"')
    expect(queuePageSource).toContain('value="normal"')
    expect(queuePageSource).toContain('value="cycle"')
    expect(queuePageSource).toContain("handleAddQueue(selectedQueueType.value === 'cycle')")
  })

  it('does not create a queue directly from the page button', () => {
    expect(queuePageSource).toContain('@click="openQueueCreateDialog"')
    expect(queuePageSource).not.toContain('@click="handleAddQueue"')
  })
})
