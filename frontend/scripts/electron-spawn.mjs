#!/usr/bin/env node
/**
 * Wrapper script to spawn Electron with ELECTRON_RUN_AS_NODE unset.
 *
 * In some environments (CI, IDE terminals, global npm config),
 * ELECTRON_RUN_AS_NODE=1 is persisted, causing electron.exe to run
 * as plain Node.js instead of the Electron runtime. This script
 * explicitly deletes the variable before spawning the Electron CLI.
 *
 * Usage: node scripts/electron-spawn.mjs [-- <extra electron args>]
 */

import { spawn } from 'child_process'
import { createRequire } from 'module'

const require = createRequire(import.meta.url)
const electronPath = require('electron')

const env = { ...process.env }
delete env.ELECTRON_RUN_AS_NODE

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
