<#
.SYNOPSIS
    Очистка мусора в проекте XTTS Studio - версия с карантином.

.DESCRIPTION
    В отличие от прямого удаления, скрипт работает в 4 стадии, каждая из
    которых фиксируется в manifest.json (чекпоинт), чтобы при сбое/закрытии
    терминала можно было понять, на чём остановились, и продолжить или
    откатить:

      SCANNED     -> найдены кандидаты на удаление (ничего не тронуто)
      QUARANTINED -> кандидаты перемещены в tools\_quarantine\<timestamp>\
                     с сохранением относительных путей (для точного restore)
      VERIFIED    -> прогнана проверка работоспособности (авто и/или ручная)
      RESOLVED    -> пользователь подтвердил: либо окончательно удалено,
                     либо восстановлено обратно

    Что чистит (перемещает в карантин):
      1. Папки __pycache__ и .pytest_cache (везде в проекте, рекурсивно).
      2. "Битые" 0-байтовые файлы с безопасными расширениями
         (.whl, .tmp, .log, .bak, .part, .crdownload, .old) - везде в проекте.

    НЕ трогает: word_rules_backups\, .git\, и 0-байтовые файлы с прочими
    расширениями (только показывает как "требует внимания").

.NOTES
    Скрипт лежит в tools\, корень проекта - на уровень выше ($RootDir).
    Восстановить конкретную карантинную сессию вручную можно скриптом
    restore_quarantine.ps1 (на случай если эта сессия была прервана).
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir   = Split-Path -Parent $ScriptDir
$QuarantineRoot = Join-Path $ScriptDir "_quarantine"

$CacheDirNames   = @('__pycache__', '.pytest_cache')
$ExcludeDirNames = @('word_rules_backups', '.git', '_quarantine')
$ZeroByteSafeExt = @('.whl', '.tmp', '.log', '.bak', '.part', '.crdownload', '.old')

function Format-Size([long]$bytes) {
    if ($bytes -lt 1KB) { return "$bytes B" }
    elseif ($bytes -lt 1MB) { return "{0:N2} KB" -f ($bytes / 1KB) }
    elseif ($bytes -lt 1GB) { return "{0:N2} MB" -f ($bytes / 1MB) }
    else { return "{0:N2} GB" -f ($bytes / 1GB) }
}

function Test-Excluded([string]$fullPath) {
    $rel = $fullPath.Substring($RootDir.Length).TrimStart('\')
    $parts = $rel -split '\\'
    foreach ($ex in $ExcludeDirNames) {
        if ($parts -contains $ex) { return $true }
    }
    return $false
}

function Get-DirSize([string]$path) {
    $size = (Get-ChildItem -LiteralPath $path -Recurse -Force -File -ErrorAction SilentlyContinue |
             Measure-Object -Property Length -Sum).Sum
    if ($null -eq $size) { return 0 }
    return $size
}

function Write-Manifest($batchDir, $stage, $items, $extra = @{}) {
    $manifest = @{
        stage   = $stage
        created = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        items   = $items
    }
    foreach ($k in $extra.Keys) { $manifest[$k] = $extra[$k] }
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $batchDir "manifest.json") -Encoding UTF8
}

function Restore-Batch($batchDir, $manifest) {
    $ok = 0; $fail = 0
    foreach ($item in $manifest.items) {
        try {
            $destDir = Split-Path -Parent $item.original
            if (-not (Test-Path -LiteralPath $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            Move-Item -LiteralPath $item.quarantine -Destination $item.original -Force -ErrorAction Stop
            $ok++
        } catch {
            Write-Host "  [ошибка] не удалось восстановить $($item.original): $_" -ForegroundColor Red
            $fail++
        }
    }
    return @{ ok = $ok; fail = $fail }
}

function Purge-Batch($batchDir) {
    Remove-Item -LiteralPath $batchDir -Recurse -Force -ErrorAction SilentlyContinue
}

# -- Проверка незавершённых карантинных сессий (checkpoint / resume) -----
if (Test-Path -LiteralPath $QuarantineRoot) {
    $pending = Get-ChildItem -LiteralPath $QuarantineRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path (Join-Path $_.FullName "manifest.json") } |
        Where-Object {
            $m = Get-Content (Join-Path $_.FullName "manifest.json") -Raw | ConvertFrom-Json
            $m.stage -ne 'RESOLVED'
        }

    foreach ($batch in $pending) {
        $manifestPath = Join-Path $batch.FullName "manifest.json"
        $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json

        Write-Host "`n[!] Найдена незавершённая карантинная сессия: $($batch.Name)" -ForegroundColor Yellow
        Write-Host "    Стадия: $($manifest.stage), создана: $($manifest.created), объектов: $($manifest.items.Count)"
        Write-Host "    r - восстановить исходное состояние (откатить карантин)"
        Write-Host "    c - продолжить (перейти к проверке/подтверждению)"
        Write-Host "    d - удалить окончательно (я уже всё проверил раньше)"
        $choice = Read-Host "Выбор (r/c/d)"

        switch ($choice.ToLower()) {
            'r' {
                $res = Restore-Batch $batch.FullName $manifest
                Write-Host "Восстановлено: $($res.ok), ошибок: $($res.fail)."
                Purge-Batch $batch.FullName
            }
            'd' {
                Purge-Batch $batch.FullName
                Write-Host "Карантинная сессия окончательно удалена."
            }
            default {
                # 'c' - переходим ниже к стадии VERIFY/DECISION для этой же сессии
                Write-Host "Продолжаю обработку сессии $($batch.Name)..."
                $global:ResumeBatchDir = $batch.FullName
                $global:ResumeManifest = $manifest
            }
        }
    }
}

function Run-VerifyAndDecide($batchDir, $manifest) {
    Write-Host "`n$('=' * 70)"
    Write-Host "СТАДИЯ: ПРОВЕРКА РАБОТОСПОСОБНОСТИ"
    Write-Host ("=" * 70)

    $auto = Read-Host "Запустить автоматическую проверку (RUN_TESTS.bat real) сейчас? (y/n)"
    $verifyPassed = $null
    if ($auto.ToLower() -eq 'y') {
        $runTests = Join-Path $RootDir "test\RUN_TESTS.bat"
        if (Test-Path -LiteralPath $runTests) {
            & cmd /c "`"$runTests`" real"
            $verifyPassed = ($LASTEXITCODE -eq 0)
            if ($verifyPassed) {
                Write-Host "`n[OK] Автоматическая проверка пройдена." -ForegroundColor Green
            } else {
                Write-Host "`n[FAIL] Автоматическая проверка нашла проблемы (см. вывод выше)." -ForegroundColor Red
            }
        } else {
            Write-Host "[!] Не найден $runTests - пропускаю автопроверку." -ForegroundColor Yellow
        }
    } else {
        Write-Host "Пропущено. Запусти и проверь проект вручную, затем вернись сюда."
    }

    Write-Manifest $batchDir "VERIFIED" $manifest.items @{ verify_passed = $verifyPassed }

    Write-Host "`n$('=' * 70)"
    Write-Host "СТАДИЯ: РЕШЕНИЕ"
    Write-Host ("=" * 70)
    Write-Host "Карантин: $batchDir"
    Write-Host "Всё работает нормально?"
    Write-Host "  y - да, окончательно удалить карантин"
    Write-Host "  n - нет, восстановить файлы обратно"
    $decision = Read-Host "Выбор (y/n)"

    if ($decision.ToLower() -eq 'y') {
        Purge-Batch $batchDir
        Write-Host "Карантин окончательно удалён."
    } else {
        $res = Restore-Batch $batchDir $manifest
        Write-Host "Восстановлено: $($res.ok), ошибок: $($res.fail)."
        Purge-Batch $batchDir
        Write-Host "Файлы возвращены на исходные места."
    }
}

if ($global:ResumeBatchDir) {
    Run-VerifyAndDecide $global:ResumeBatchDir $global:ResumeManifest
    Write-Host "`nГотово."
    exit 0
}

# -- Новый прогон: SCAN -----------------------------------------------
if (-not (Test-Path -LiteralPath $RootDir)) {
    Write-Host "[!] Корень проекта не найден: $RootDir" -ForegroundColor Red
    exit 1
}

Write-Host "Сканирую проект: $RootDir`n"

$allDirs = Get-ChildItem -LiteralPath $RootDir -Recurse -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object { -not (Test-Excluded $_.FullName) }

$cacheDirs = $allDirs | Where-Object { $CacheDirNames -contains $_.Name }
$cacheInfo = @()
$totalSize = 0
foreach ($d in $cacheDirs) {
    $sz = Get-DirSize $d.FullName
    $cacheInfo += [PSCustomObject]@{ Path = $d.FullName; Size = $sz; Type = 'dir' }
    $totalSize += $sz
}

$allFiles = Get-ChildItem -LiteralPath $RootDir -Recurse -Force -File -ErrorAction SilentlyContinue |
    Where-Object { -not (Test-Excluded $_.FullName) }

$zeroFiles = $allFiles | Where-Object { $_.Length -eq 0 -and $ZeroByteSafeExt -contains $_.Extension.ToLower() }
$suspiciousZero = $allFiles | Where-Object { $_.Length -eq 0 -and $ZeroByteSafeExt -notcontains $_.Extension.ToLower() }

Write-Host ("=" * 70)
Write-Host "СТАДИЯ: SCAN (dry-run)"
Write-Host ("=" * 70)

if ($cacheInfo.Count -gt 0) {
    Write-Host "`n[Кэш-папки] ($($cacheInfo.Count)):"
    foreach ($c in $cacheInfo) { Write-Host "  - $($c.Path)  ($(Format-Size $c.Size))" }
} else {
    Write-Host "`n[Кэш-папки] не найдено."
}

if ($zeroFiles.Count -gt 0) {
    Write-Host "`n[0-байтовые файлы, безопасные расширения] ($($zeroFiles.Count)):"
    foreach ($f in $zeroFiles) { Write-Host "  - $($f.FullName)" }
} else {
    Write-Host "`n[0-байтовые файлы, безопасные расширения] не найдено."
}

if ($suspiciousZero.Count -gt 0) {
    Write-Host "`n[!] 0-байтовые файлы с необычным расширением - не трогаем ($($suspiciousZero.Count)):" -ForegroundColor Yellow
    foreach ($f in $suspiciousZero) { Write-Host "  - $($f.FullName)" }
}

Write-Host "`n$('-' * 70)"
Write-Host "Итого будет перемещено в карантин: $(Format-Size $totalSize)"
Write-Host ("-" * 70)

if ($cacheInfo.Count -eq 0 -and $zeroFiles.Count -eq 0) {
    Write-Host "`nМусора не найдено. Ничего делать не нужно."
    exit 0
}

Write-Host ""
$answer = Read-Host "Переместить в карантин (не удаляя окончательно)? (y/n)"
if ($answer.ToLower() -ne 'y') {
    Write-Host "Отменено, ничего не тронуто."
    exit 0
}

# -- СТАДИЯ: QUARANTINE ------------------------------------------------
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$batchDir = Join-Path $QuarantineRoot $timestamp
New-Item -ItemType Directory -Path $batchDir -Force | Out-Null

$items = @()
$candidates = @()
foreach ($c in $cacheInfo) { $candidates += $c.Path }
foreach ($f in $zeroFiles) { $candidates += $f.FullName }

foreach ($srcPath in $candidates) {
    $rel = $srcPath.Substring($RootDir.Length).TrimStart('\')
    $destPath = Join-Path $batchDir $rel
    $destParent = Split-Path -Parent $destPath
    if (-not (Test-Path -LiteralPath $destParent)) {
        New-Item -ItemType Directory -Path $destParent -Force | Out-Null
    }
    try {
        Move-Item -LiteralPath $srcPath -Destination $destPath -Force -ErrorAction Stop
        $items += @{ original = $srcPath; quarantine = $destPath }
    } catch {
        Write-Host "  [ошибка] не удалось переместить $srcPath : $_" -ForegroundColor Red
    }
}

Write-Manifest $batchDir "QUARANTINED" $items @{ total_size = $totalSize }
Write-Host "`nПеремещено в карантин: $($items.Count) объект(ов) -> $batchDir"

# -- СТАДИЯ: VERIFY + РЕШЕНИЕ -----------------------------------------
$manifestObj = [PSCustomObject]@{ items = $items }
Run-VerifyAndDecide $batchDir $manifestObj

Write-Host "`nГотово."
