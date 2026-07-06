<#
.SYNOPSIS
    Просмотр и ручное восстановление карантинных сессий cleanup_project.ps1.

.DESCRIPTION
    cleanup_project.ps1 сам предлагает обработать незавершённую сессию при
    следующем запуске. Этот скрипт — на случай, если нужно посмотреть или
    восстановить карантин отдельно, без запуска полного цикла очистки
    (например, спустя время, или если что-то пошло не так и хочется
    разобраться руками).

.NOTES
    Запуск: powershell -ExecutionPolicy Bypass -File restore_quarantine.ps1
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$QuarantineRoot = Join-Path $ScriptDir "_quarantine"

if (-not (Test-Path -LiteralPath $QuarantineRoot)) {
    Write-Host "Карантин пуст — папка $QuarantineRoot не найдена."
    exit 0
}

$batches = Get-ChildItem -LiteralPath $QuarantineRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "manifest.json") } |
    Sort-Object Name -Descending

if (-not $batches -or $batches.Count -eq 0) {
    Write-Host "Карантинных сессий не найдено."
    exit 0
}

Write-Host "Карантинные сессии (новые сверху):`n"
$i = 0
$table = @()
foreach ($b in $batches) {
    $m = Get-Content (Join-Path $b.FullName "manifest.json") -Raw | ConvertFrom-Json
    $table += [PSCustomObject]@{
        Index   = $i
        Name    = $b.Name
        Stage   = $m.stage
        Created = $m.created
        Items   = $m.items.Count
    }
    $i++
}
$table | Format-Table -AutoSize

$idxInput = Read-Host "`nНомер сессии для действия (Enter — выход)"
if ([string]::IsNullOrWhiteSpace($idxInput)) { exit 0 }

$idx = 0
if (-not [int]::TryParse($idxInput, [ref]$idx) -or $idx -lt 0 -or $idx -ge $batches.Count) {
    Write-Host "Некорректный номер."
    exit 1
}

$batch = $batches[$idx]
$manifestPath = Join-Path $batch.FullName "manifest.json"
$manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json

Write-Host "`nСессия: $($batch.Name), стадия: $($manifest.stage), объектов: $($manifest.items.Count)"
Write-Host "Содержимое:"
foreach ($item in $manifest.items) {
    Write-Host "  - $($item.original)"
}

Write-Host "`n  r - восстановить всё обратно на исходные места"
Write-Host "  d - удалить окончательно (без возможности восстановления)"
$choice = Read-Host "Выбор (r/d, Enter — отмена)"

switch ($choice.ToLower()) {
    'r' {
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
        Remove-Item -LiteralPath $batch.FullName -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "`nВосстановлено: $ok, ошибок: $fail."
    }
    'd' {
        Remove-Item -LiteralPath $batch.FullName -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "`nСессия окончательно удалена."
    }
    default {
        Write-Host "Отменено."
    }
}
