// AUTO-MAS frontend 工具：`yarn openapi` 生成后把 src/api 收拾干净。
//
// 背景：openapi-typescript-codegen 在 Windows 上按 CRLF 写出，而仓库 .gitattributes
// 强制 *.ts eol=lf；且 .oxfmtrc.json 的 ignorePatterns 忽略了 src/api，yarn format
// 也管不到。结果生成一次，git status 就会冒出一大批「只有换行符不同」的已修改文件
// （git diff 内容却为空）。
//
// 生成器不会移除不再使用的模型，先按本次 index.ts 的导出清单删除过期生成模型，
// 再把 src/api 下文本文件的换行符统一成 LF。手写文件不参与过期清理。
// 不做任何 git 操作：换行符归一后 git status 的比较即恢复一致，索引会在下次
// git status/git add 时自行刷新；这里若动索引（如 add/reset）反而会丢掉用户
// 在 src/api 里已暂存的内容。无 git 的环境因此也不受影响。
//
// 用法：node scripts/postprocess-openapi.mjs（由 package.json 的 openapi 脚本串联）

import { readdir, readFile, unlink, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const apiDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'api')
const index = await readFile(join(apiDir, 'index.ts'), 'utf8')
const modelNames = new Set(
  Array.from(index.matchAll(/from ['"]\.\/models\/([^'"]+)['"]/g), match => `${match[1]}.ts`)
)
if (modelNames.size === 0) throw new Error('生成的 index.ts 中没有模型，停止清理')

let removed = 0
const modelsDir = join(apiDir, 'models')
for (const entry of await readdir(modelsDir, { withFileTypes: true })) {
  if (!entry.isFile() || !entry.name.endsWith('.ts') || modelNames.has(entry.name)) continue
  const file = join(modelsDir, entry.name)
  const content = await readFile(file, 'utf8')
  if (!content.startsWith('/* generated using openapi-typescript-codegen')) continue
  await unlink(file)
  removed += 1
}

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) yield* walk(full)
    else if (entry.isFile()) yield full
  }
}

let normalized = 0
for await (const file of walk(apiDir)) {
  const content = await readFile(file, 'utf8')
  if (!content.includes('\r\n')) continue
  await writeFile(file, content.replaceAll('\r\n', '\n'), 'utf8')
  normalized += 1
}
console.log(
  `postprocess-openapi: 清理 ${removed} 个过期模型，${normalized} 个文件换行符已统一为 LF`
)
