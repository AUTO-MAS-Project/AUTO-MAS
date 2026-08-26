# CSS Variable Audit

Detects `var(--x)` references in frontend code that have no reachable matching
definition. A definition counts only when the exact literal name appears in one
of these forms:

- CSS declaration: `--name: value`
- Style binding / object key: `'--name': value` or `"--name": value`
- Runtime injection: `setProperty('--name', ...)`

Dynamic names built with template literals are invisible to this audit; keep
`setProperty` names literal (see Theme And Dark Mode rule 5). Definitions inside
comments do not count. A selector-local or scoped definition satisfies only
references in the same file. Only `:root` definitions and root injection from
`useTheme.ts` count as shared across files.

## Scope

Run from the repository root. Scans `frontend/src/**/*.{vue,ts,css}` plus
`frontend/index.html`.

## Script (PowerShell 7)

```powershell
$ErrorActionPreference = 'Stop'
$root = "frontend"
$files = @(Get-ChildItem -Path "$root/src" -Recurse -Include *.vue,*.ts,*.css -File)
if (Test-Path "$root/index.html") { $files += Get-Item "$root/index.html" }

$globalDefined = [System.Collections.Generic.HashSet[string]]::new()
$definedByFile = @{}
$usage = @{}

function Remove-CommentsPreservingLines([string]$text) {
  $withoutBlocks = [regex]::Replace(
    $text,
    '(?s)/\*.*?\*/|<!--.*?-->',
    { param($match) [regex]::Replace($match.Value, '[^\r\n]', ' ') }
  )
  return [regex]::Replace($withoutBlocks, '(?m)(?<!:)//.*$', '')
}

function Add-Definitions([string]$text, [System.Collections.Generic.HashSet[string]]$target) {
  foreach ($m in [regex]::Matches($text, '(?<![\w-])(--[a-zA-Z][\w-]*)\s*:')) { [void]$target.Add($m.Groups[1].Value) }
  foreach ($m in [regex]::Matches($text, '[''"](--[\w-]+)[''"]\s*:')) { [void]$target.Add($m.Groups[1].Value) }
  foreach ($m in [regex]::Matches($text, 'setProperty\(\s*["''](--[\w-]+)')) { [void]$target.Add($m.Groups[1].Value) }
}

function Add-RootDefinitions([string]$text, [System.Collections.Generic.HashSet[string]]$target) {
  foreach ($m in [regex]::Matches($text, '(?is):root(?:\.[\w-]+)*\s*\{([^{}]*)\}')) {
    Add-Definitions $m.Groups[1].Value $target
  }
}

foreach ($f in $files) {
  $text = Remove-CommentsPreservingLines (Get-Content -LiteralPath $f.FullName -Raw)
  $localDefined = [System.Collections.Generic.HashSet[string]]::new()
  Add-Definitions $text $localDefined
  $definedByFile[$f.FullName] = $localDefined

  if ($f.Extension -in '.css', '.html') {
    Add-RootDefinitions $text $globalDefined
  }
  elseif ($f.Extension -eq '.vue') {
    foreach ($m in [regex]::Matches($text, '(?is)<style(?![^>]*\bscoped\b)[^>]*>(.*?)</style>')) {
      Add-RootDefinitions $m.Groups[1].Value $globalDefined
    }
  }

  if ($f.FullName -eq (Join-Path (Get-Location) 'frontend/src/composables/useTheme.ts')) {
    foreach ($m in [regex]::Matches($text, 'setProperty\(\s*["''](--[\w-]+)')) {
      [void]$globalDefined.Add($m.Groups[1].Value)
    }
  }
}

foreach ($f in $files) {
  $text = Remove-CommentsPreservingLines (Get-Content -LiteralPath $f.FullName -Raw)
  $lines = [regex]::Split($text, '\r?\n')
  for ($i = 0; $i -lt $lines.Count; $i++) {
    foreach ($m in [regex]::Matches($lines[$i], 'var\(\s*(--[\w-]+)')) {
      $name = $m.Groups[1].Value
      if (-not $globalDefined.Contains($name) -and -not $definedByFile[$f.FullName].Contains($name)) {
        $loc = "$($f.FullName.Substring((Get-Location).Path.Length + 1)):$($i + 1)"
        if (-not $usage.ContainsKey($name)) { $usage[$name] = [System.Collections.Generic.List[string]]::new() }
        $usage[$name].Add($loc)
      }
    }
  }
}

if ($usage.Count -eq 0) { Write-Output "NO_UNDEFINED_VARS" }
else {
  Write-Output "UNDEFINED VARIABLES FOUND: $($usage.Count)"
  foreach ($k in $usage.Keys | Sort-Object) {
    Write-Output "== $k ($($usage[$k].Count) refs) =="
    $usage[$k] | Select-Object -First 5 | ForEach-Object { Write-Output "   $_" }
  }
  exit 1
}
```

## Interpreting Results

1. `NO_UNDEFINED_VARS` is the expected passing state.
2. For each reported variable, prefer renaming the usage to an existing token over
   deleting the declaration.
3. For a missing `--ant-*` variable, add a literal `setProperty` definition in
   `useTheme.updateCSSVariables()` whose value comes from the matching
   `antTokens.<token>`. The `antTokens` object must use the same algorithm and seed
   as `ConfigProvider`; never hand-write an approximation of an Ant Design token.
4. If Ant Design has no matching token, use a project-specific `--app-*` name and
   derive its theme-aware value in `useTheme.ts`.
5. A reference that carries its own fallback (`var(--missing, #fff)`) still fails the
   audit intent: the fallback silently hides the broken token and blocks theming.

## Related Dark Mode Check

The same audit pass should confirm `prefers-color-scheme` appears only inside
`src/composables/useTheme.ts`:

```powershell
$hits = @(rg -n "prefers-color-scheme" frontend/src --glob "!**/composables/useTheme.ts")
if ($LASTEXITCODE -gt 1) { exit $LASTEXITCODE }
if ($hits.Count -eq 0) { Write-Output "NO_EXTERNAL_PREFERS_COLOR_SCHEME" }
else { $hits; exit 1 }
```

Any hit outside `useTheme.ts` is a wrong dark-mode detection source (see
Theme And Dark Mode rules).
