import { access, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, expect, it, vi } from 'vite-plus/test'
import { UpdateMaterial, recoverUpdateMaterials } from './updateStaging'

const native = vi.hoisted(() => ({ processes: vi.fn() }))
vi.mock('./logger', () => ({ getLogger: () => ({ warn: vi.fn() }) }))
vi.mock('node:child_process', () => ({
  execFile: (
    _file: string,
    _args: string[],
    _options: unknown,
    callback: (error: Error | null, output?: string) => void
  ) => {
    // 仅控制系统进程清单，记录读写与目录回收均执行生产实现。
    try {
      callback(null, JSON.stringify(native.processes()))
    } catch (error) {
      callback(error as Error)
    }
  },
}))

const frontend = {
  pid: process.pid,
  name: 'frontend.exe',
  started: 'front-start',
  executable: process.execPath,
  command: 'frontend',
}
const roots: string[] = []
afterEach(async () => {
  // 删除本用例的隔离根，不接触用户暂存目录。
  await Promise.all(roots.splice(0).map(root => rm(root, { recursive: true, force: true })))
  vi.clearAllMocks()
})

it('可用材料在原前端存活时保留，进程退出或 PID 被复用后回收', async () => {
  const root = await mkdtemp(join(tmpdir(), 'mas-stage-'))
  roots.push(root)
  native.processes.mockReturnValue([frontend])
  const material = await UpdateMaterial.create(root, 'runtime', 'v1.0.0')
  const file = join(material.directory, 'runtime.exe')
  await writeFile(file, 'runtime')
  await material.setPhase('ready')
  await recoverUpdateMaterials(root)
  expect(await readFile(file, 'utf8')).toBe('runtime')
  native.processes.mockReturnValue([{ ...frontend, started: 'reused-pid' }])
  await recoverUpdateMaterials(root)
  await expect(access(material.directory)).rejects.toMatchObject({ code: 'ENOENT' })
  await material.dispose()
})

it.each([true, false])('安装交接在 PID 记录%s时保留真实安装进程，结束后才删除', async recorded => {
  const root = await mkdtemp(join(tmpdir(), 'mas-handoff-'))
  roots.push(root)
  native.processes.mockReturnValue([frontend])
  const material = await UpdateMaterial.create(root, 'package', 'v5.9.0')
  await material.setPhase('ready')
  await material.setPhase('handoff')
  const loader = {
    pid: 8765,
    name: 'AUTO-MAS-Setup.exe',
    started: 'setup-start',
    executable: join(material.directory, 'AUTO-MAS-Setup.exe'),
    command: 'setup',
  }
  native.processes.mockReturnValue([frontend, loader])
  if (recorded) await material.recordInstaller(loader.pid)
  // 模拟旧前端退出，新前端在实际安装进程仍运行时启动；加载器即使异常退出也不能误删。
  const engine = {
    pid: 8766,
    name: 'setup.tmp',
    started: 'engine-start',
    executable: 'C:\\Temp\\setup.tmp',
    command: `/SL5="${loader.executable}"`,
  }
  native.processes.mockReturnValue([engine])
  await material.dispose()
  await material.installerExited()
  await recoverUpdateMaterials(root)
  await expect(access(material.directory)).resolves.toBeUndefined()
  native.processes.mockReturnValue([])
  if (recorded) await material.installerExited()
  else await recoverUpdateMaterials(root)
  await expect(access(material.directory)).rejects.toMatchObject({ code: 'ENOENT' })
})

it('进程查询失败或安装进程命令不可读时保留材料，后续可确认结束再回收', async () => {
  const root = await mkdtemp(join(tmpdir(), 'mas-unknown-'))
  roots.push(root)
  native.processes.mockReturnValue([frontend])
  const material = await UpdateMaterial.create(root, 'package', 'v5.9.0')
  await material.setPhase('handoff')
  native.processes.mockImplementation(() => {
    throw new Error('process query denied')
  })
  await recoverUpdateMaterials(root)
  await expect(access(material.directory)).resolves.toBeUndefined()
  native.processes.mockReturnValue([
    { pid: 11, name: 'setup.tmp', started: 'unknown', executable: null, command: null },
  ])
  await recoverUpdateMaterials(root)
  await expect(access(material.directory)).resolves.toBeUndefined()
  native.processes.mockReturnValue([])
  await recoverUpdateMaterials(root)
  await expect(access(material.directory)).rejects.toMatchObject({ code: 'ENOENT' })
})
