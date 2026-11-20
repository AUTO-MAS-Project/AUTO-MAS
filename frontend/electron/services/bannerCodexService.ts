import { spawn } from 'node:child_process'
import { mkdtemp, rmdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

export type BannerCodexResult =
  | { status: 'ok'; analysis: string }
  | { status: 'unavailable' | 'failed' | 'busy' }

const MAX_PROMPT_BYTES = 48 * 1024
const MAX_EVENT_BYTES = 1024 * 1024
const ANALYSIS_TIMEOUT_MS = 180_000
let active: AbortController | undefined

function finalAnalysis(events: string): string | undefined {
  let analysis: string | undefined
  let completed = false
  for (const line of events.split('\n')) {
    if (!line.trim()) continue
    const event = JSON.parse(line)
    if (
      event.type === 'item.completed' &&
      event.item?.type === 'agent_message' &&
      typeof event.item.text === 'string'
    ) {
      analysis = event.item.text.trim()
    }
    if (event.type === 'turn.completed') completed = true
  }
  return completed ? analysis : undefined
}

export async function analyzeBannerWithCodex(prompt: unknown): Promise<BannerCodexResult> {
  if (
    typeof prompt !== 'string' ||
    !prompt.trim() ||
    Buffer.byteLength(prompt) > MAX_PROMPT_BYTES
  ) {
    return { status: 'failed' }
  }
  if (active) return { status: 'busy' }
  const controller = new AbortController()
  active = controller
  let workspace: string | undefined
  try {
    workspace = await mkdtemp(join(tmpdir(), 'auto-mas-banner-codex-'))
    const cwd = workspace
    return await new Promise<BannerCodexResult>(resolve => {
      const cli = process.platform === 'win32' ? 'codex.exe' : 'codex'
      const child = spawn(
        cli,
        [
          '--ask-for-approval',
          'never',
          'exec',
          '--sandbox',
          'read-only',
          '--skip-git-repo-check',
          '--ephemeral',
          '--ignore-user-config',
          '--ignore-rules',
          '--json',
          '-',
        ],
        {
          cwd,
          shell: false,
          windowsHide: true,
          stdio: ['pipe', 'pipe', 'ignore'],
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(ANALYSIS_TIMEOUT_MS)]),
        }
      )
      let output = ''
      let overflow = false
      child.stdout.setEncoding('utf8')
      child.stdout.on('data', (chunk: string) => {
        if (overflow) return
        if (Buffer.byteLength(output) + Buffer.byteLength(chunk) > MAX_EVENT_BYTES) {
          overflow = true
          controller.abort()
          return
        }
        output += chunk
      })
      // The executable may exit before reading stdin when it cannot load its login.
      child.stdin.on('error', () => undefined)
      child.on('error', (error: NodeJS.ErrnoException) => {
        resolve({ status: error.code === 'ENOENT' ? 'unavailable' : 'failed' })
      })
      child.on('close', code => {
        try {
          const analysis = code === 0 && !overflow ? finalAnalysis(output) : undefined
          resolve(analysis ? { status: 'ok', analysis } : { status: 'failed' })
        } catch {
          resolve({ status: 'failed' })
        }
      })
      // Use stdin so the reviewed prompt never appears in a process command line.
      child.stdin.end(prompt, 'utf8')
    })
  } catch {
    return { status: 'failed' }
  } finally {
    if (workspace) await rmdir(workspace).catch(() => undefined)
    active = undefined
  }
}

export function stopBannerCodexAnalysis(): void {
  active?.abort()
}
