#!/usr/bin/env node
/**
 * Wrapper script to spawn Electron with a normalized development environment.
 *
 * In some environments (CI, IDE terminals, global npm config),
 * ELECTRON_RUN_AS_NODE=1 is persisted, causing electron.exe to run
 * as plain Node.js instead of the Electron runtime. This script
 * explicitly deletes the variable before spawning the Electron CLI. Windows
 * environment keys are case-insensitive, so PATH variants are normalized too.
 *
 * Usage: node scripts/electron-spawn.mjs [-- <extra electron args>]
 */

import { spawn } from 'child_process'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)
const electronPath = require('electron')

const env = { ...process.env }
const inheritedPath = env.PATH || env.Path

for (const key of Object.keys(env)) {
  const normalizedKey = key.toLowerCase()
  if (normalizedKey === 'electron_run_as_node' || normalizedKey === 'path') {
    delete env[key]
  }
}

if (inheritedPath !== undefined) {
  env[process.platform === 'win32' ? 'Path' : 'PATH'] = inheritedPath
}
env.NODE_ENV = 'development'

const args = process.argv.slice(2)

const child = spawn(electronPath, args, {
  stdio: 'inherit',
  env,
  windowsHide: false,
})

child.on('close', (code, signal) => {
  if (code === null) {
    console.error(electronPath, 'exited with signal', signal)
    process.exit(1)
  }
  process.exit(code)
})

const handleSignal = signal => {
  process.on(signal, () => {
    if (!child.killed) child.kill(signal)
  })
}

handleSignal('SIGINT')
handleSignal('SIGTERM')
