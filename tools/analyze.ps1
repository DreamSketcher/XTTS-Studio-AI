#Requires -Version 5.1

# ============================================================
#  Project Structure Analyzer v3.3
#  Place: tools/analyze.ps1
#  Run  : powershell -ExecutionPolicy Bypass -File tools\analyze.ps1
# ============================================================

param(
    [string]$TargetDir
)

# --- Wrap everything so the window never closes silently ---
try {

# --- Auto-detect project root ---
if (-not $TargetDir) {
    try {
        $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
        if ($scriptDir -match '[\\/]tools$') {
            $TargetDir = Split-Path -Parent $scriptDir
        } else {
            $TargetDir = (Get-Location).Path
        }
    } catch {
        $TargetDir = (Get-Location).Path
    }
}

# --- Safe console setup ---
try { $Host.UI.RawUI.WindowTitle = "Project Analyzer v3.3" } catch { }
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$ProgressPreference = 'SilentlyContinue'

# ============================================================
#  GLOBAL SETTINGS
# ============================================================

$script:DefaultExcludes = @(
    'node_modules', '.git', '__pycache__', '.venv', 'venv', 'env',
    '.idea', '.vs', '.vscode', 'dist', 'build', 'target', 'bin', 'obj',
    '.next', '.nuxt', '.cache', 'coverage', '.tox', '.mypy_cache',
    '.pytest_cache', '.gradle', '.dart_tool', '.pub-cache', 'vendor',
    'packages', '.svn', '.hg'
)

$script:UserExcludes = [System.Collections.ArrayList]@()
$script:ExcludeFile = Join-Path $env:TEMP "proj_excludes.json"

if (Test-Path $script:ExcludeFile) {
    try {
        $saved = Get-Content $script:ExcludeFile -Raw | ConvertFrom-Json
        if ($saved) { $script:UserExcludes = [System.Collections.ArrayList]@($saved) }
    } catch { }
}

# ============================================================
#  COLORS
# ============================================================

$Colors = @{
    Title     = 'Cyan'
    Success   = 'Green'
    Warning   = 'Yellow'
    Error     = 'Red'
    Info      = 'White'
    Muted     = 'DarkGray'
    Accent    = 'Magenta'
    Number    = 'Yellow'
    Path      = 'DarkCyan'
    Progress  = 'Green'
}

# ============================================================
#  HELPERS
# ============================================================

function Write-Title {
    param([string]$Text)
    $line = '=' * ($Text.Length + 4)
    Write-Host ""
    Write-Host "  $line" -ForegroundColor $Colors.Title
    Write-Host "    $Text" -ForegroundColor $Colors.Title
    Write-Host "  $line" -ForegroundColor $Colors.Title
    Write-Host ""
}

function Write-Section {
    param([string]$Text)
    $pad  = [Math]::Max(2, 50 - $Text.Length)
    $line = '-' * $pad
    Write-Host ""
    Write-Host "  --- $Text $line" -ForegroundColor $Colors.Accent
}

function Write-Step {
    param([int]$Current, [int]$Total, [string]$Text)
    Write-Host ""
    Write-Host "  SHAG $Current/$Total  " -NoNewline -ForegroundColor $Colors.Number
    Write-Host $Text -ForegroundColor $Colors.Info
    Write-Host "  " + ('-' * 50) -ForegroundColor $Colors.Muted
}

function Format-FileSize {
    param([long]$Bytes)
    if ($Bytes -ge 1GB) { return "{0:N2} GB" -f ($Bytes / 1GB) }
    if ($Bytes -ge 1MB) { return "{0:N2} MB" -f ($Bytes / 1MB) }
    if ($Bytes -ge 1KB) { return "{0:N2} KB" -f ($Bytes / 1KB) }
    return "$Bytes B"
}

function Test-IsExcluded {
    param([string]$Name)
    if ($script:DefaultExcludes -contains $Name) { return $true }
    if ($script:UserExcludes   -contains $Name) { return $true }
    return $false
}

function Save-UserExcludes {
    try { $script:UserExcludes | ConvertTo-Json | Set-Content $script:ExcludeFile -Force } catch { }
}

function Write-ProgressBar {
    param([int]$Current, [int]$Total, [string]$Status = "", [int]$Width = 30)
    if ($Total -le 0) { $percent = 0 } else { $percent = [math]::Floor(($Current / $Total) * 100) }
    $filled = [math]::Floor(($percent / 100) * $Width)
    $empty  = $Width - $filled
    if ($filled -lt 0) { $filled = 0 }; if ($empty -lt 0) { $empty = 0 }
    $bar  = "█" * $filled + "░" * $empty
    Write-Host "`r  [$bar] $percent% $Status" -NoNewline -ForegroundColor $Colors.Progress
}

function Write-ProgressDone {
    param([string]$Text)
    Write-Host "`r  [$('█' * 30)] 100% $Text" -ForegroundColor $Colors.Success
}

function Draw-Histogram {
    param([string]$Label, [int]$Value, [int]$MaxValue, [int]$Width = 28)
    if ($MaxValue -le 0) { $MaxValue = 1 }
    $filled = [math]::Floor(($Value / $MaxValue) * $Width)
    if ($Value -gt 0 -and $filled -eq 0) { $filled = 1 }
    if ($filled -lt 0) { $filled = 0 }
    $empty = $Width - $filled
    if ($empty -lt 0) { $empty = 0 }
    $bar = "█" * $filled + "░" * $empty
    Write-Host "  |  $($Label.PadRight(16))" -NoNewline -ForegroundColor $Colors.Info
    Write-Host $bar -NoNewline -ForegroundColor $Colors.Progress
    Write-Host " $($Value.ToString().PadLeft(5))" -ForegroundColor $Colors.Number
}

# ============================================================
#  MAIN MENU
# ============================================================

function Show-MainMenu {
    while ($true) {
        try { Clear-Host } catch { Write-Host "" }

        Write-Title "PROJECT STRUCTURE ANALYZER v3.3"

        Write-Host "  Target: " -NoNewline
        Write-Host $TargetDir -ForegroundColor $Colors.Path
        Write-Host ""

        Write-Host "  [1]  Poverkhnostny analiz   (koren)"           -ForegroundColor $Colors.Info
        Write-Host "  [2]  Polny analiz proekta   (rekursivno)"     -ForegroundColor $Colors.Info
        Write-Host "  [3]  Dobavit v isklyucheniya"                 -ForegroundColor $Colors.Info
        Write-Host "  [4]  Udalit iz isklyucheniy"                  -ForegroundColor $Colors.Info
        Write-Host "  [5]  Pokazat isklyucheniya"                   -ForegroundColor $Colors.Info
        Write-Host "  [6]  Derevo proekta"                          -ForegroundColor $Colors.Info
        Write-Host "  [7]  Eksport otchyota"                        -ForegroundColor $Colors.Info
        Write-Host "  [0]  Vykhod"                                  -ForegroundColor $Colors.Error
        Write-Host ""

        $choice = Read-Host "  Vyberite deystvie"

        switch ($choice) {
            "1" { Invoke-SurfaceAnalysis }
            "2" { Invoke-FullAnalysis }
            "3" { Invoke-AddExclusion }
            "4" { Invoke-RemoveExclusion }
            "5" { Show-Exclusions }
            "6" { Show-ProjectTree }
            "7" { Export-Report }
            "0" { return }
        }
    }
}

# ============================================================
#  1. SURFACE ANALYSIS
# ============================================================

function Invoke-SurfaceAnalysis {
    try { Clear-Host } catch { }
    Write-Title "POVERKHNOSTNY ANALIZ"

    Write-Host "  Skaniruyu kornevuyu direktoriyu..." -ForegroundColor $Colors.Info
    Write-Host ""

    $items = [System.Collections.ArrayList]@()

    # --- Folders ---
    try { $dirs = @(Get-ChildItem -Path $TargetDir -Directory -ErrorAction SilentlyContinue) } catch { $dirs = @() }
    $i = 0
    foreach ($dir in $dirs) {
        $i++
        Write-Host "  Skan: papka $i/$($dirs.Count)..." -NoNewline

        try {
            $fileCount = @(Get-ChildItem -Path $dir.FullName -File -Recurse -ErrorAction SilentlyContinue).Count
        } catch { $fileCount = 0 }

        [void]$items.Add([PSCustomObject]@{
            Num        = $items.Count + 1
            Name       = $dir.Name
            Type       = "PAPKA"
            Info       = "$fileCount faylov"
            FullPath   = $dir.FullName
            IsExcluded = Test-IsExcluded $dir.Name
        })
        Write-Host " OK" -ForegroundColor $Colors.Success
    }

    # --- Files ---
    try { $files = @(Get-ChildItem -Path $TargetDir -File -ErrorAction SilentlyContinue) } catch { $files = @() }
    $j = 0
    foreach ($file in $files) {
        $j++
        Write-Host "  Skan: fayl $j/$($files.Count)..." -NoNewline

        [void]$items.Add([PSCustomObject]@{
            Num        = $items.Count + 1
            Name       = $file.Name
            Type       = "FAYL"
            Info       = Format-FileSize $file.Length
            FullPath   = $file.FullName
            IsExcluded = Test-IsExcluded $file.Name
        })
        Write-Host " OK" -ForegroundColor $Colors.Success
    }

    Write-Host ""
    Write-Host "  Papok: $($dirs.Count), Faylov: $($files.Count)" -ForegroundColor $Colors.Success
    Write-Host ""

    Write-Section "SODERZHIMOE KORNYA"
    Write-Host ""

    # --- Table ---
    $fmt = "  {0,-4} {1,-8} {2,-8} {3,-34} {4}"
    Write-Host ($fmt -f "N", "Status", "Tip", "Imya", "Info") -ForegroundColor $Colors.Muted
    Write-Host "  " + ('-' * 62) -ForegroundColor $Colors.Muted

    foreach ($item in $items) {
        $status  = if ($item.IsExcluded) { "[ISK]" } else { "     " }
        $sc      = if ($item.IsExcluded) { $Colors.Warning } else { $Colors.Muted }
        $name    = if ($item.Type -eq "PAPKA") { "$($item.Name)/" } else { $item.Name }
        if ($name.Length -gt 33) { $name = $name.Substring(0, 30) + "..." }

        Write-Host ($fmt -f $item.Num, $status, $item.Type, $name, $item.Info) -ForegroundColor $Colors.Info
    }

    Write-Host ""
    Write-Host "  Vsego: $($items.Count) elementov ($($dirs.Count) papok, $($files.Count) faylov)" -ForegroundColor $Colors.Muted
    Write-Host ""
    Read-Host "  Nazhmite Enter dlya prodolzheniya"
}

# ============================================================
#  2. FULL ANALYSIS
# ============================================================

function Invoke-FullAnalysis {
    try { Clear-Host } catch { }
    Write-Title "POLNY ANALIZ PROEKTA"

    # --- STEP 1: Index ---
    Write-Step 1 6 "Indeksatsiya faylov"
    Write-ProgressBar 0 100 "Poisk..."
    try {
        $allFiles = @(Get-ChildItem -Path $TargetDir -File -Recurse -ErrorAction SilentlyContinue)
    } catch { $allFiles = @() }
    $rawTotal = $allFiles.Count
    Write-ProgressDone "Naydeno $rawTotal faylov"

    # --- STEP 2: Filter ---
    Write-Step 2 6 "Primenenie filtrov"
    $allExcludes   = $script:DefaultExcludes + $script:UserExcludes
    $filteredFiles = [System.Collections.ArrayList]@()
    $idx = 0

    foreach ($file in $allFiles) {
        $idx++
        if ($idx % 50 -eq 0) { Write-ProgressBar $idx $rawTotal "Filtratsiya..." }

        $excluded     = $false
        $relativePath = ""
        try { $relativePath = $file.FullName.Replace($TargetDir, "") } catch { }

        foreach ($excl in $allExcludes) {
            if ($relativePath -like "*\$excl\*" -or $relativePath -like "*\$excl" -or $file.Name -eq $excl) {
                $excluded = $true
                break
            }
        }
        if (-not $excluded) { [void]$filteredFiles.Add($file) }
    }

    $filteredOut = $rawTotal - $filteredFiles.Count
    Write-ProgressDone "Otfiltrovano $filteredOut, ostalos $($filteredFiles.Count)"

    # --- STEP 3: Sizes ---
    Write-Step 3 6 "Podschyot razmerov"
    $totalSize = 0L
    $idx = 0
    foreach ($file in $filteredFiles) {
        $idx++
        $totalSize += $file.Length
        if ($idx % 100 -eq 0) { Write-ProgressBar $idx $filteredFiles.Count "$idx/$($filteredFiles.Count)" }
    }
    Write-ProgressDone "Obshchiy razmer: $(Format-FileSize $totalSize)"

    # --- STEP 4: Categorize ---
    Write-Step 4 6 "Kategorizatsiya faylov"

    $categories = @{
        Kod      = @('.py','.js','.ts','.java','.c','.cpp','.h','.hpp','.cs','.go','.rs','.rb','.php','.swift','.kt','.lua','.sh','.bat','.cmd','.ps1','.pl','.r','.m','.vb','.pas','.scala','.ex','.exs','.clj','.hs')
        Web      = @('.html','.htm','.css','.scss','.sass','.less','.jsx','.tsx','.vue','.svelte','.astro','.ejs','.pug','.hbs')
        Dannye   = @('.json','.xml','.yaml','.yml','.toml','.ini','.cfg','.conf','.env','.csv','.sql','.graphql','.proto','.lock')
        Dok      = @('.md','.txt','.rst','.doc','.docx','.pdf','.rtf','.tex','.adoc','.log','.readme')
        Izobr    = @('.png','.jpg','.jpeg','.gif','.svg','.ico','.bmp','.webp','.avif','.tiff','.psd','.ai')
        Shrift   = @('.ttf','.otf','.woff','.woff2','.eot')
        Arkhiv   = @('.zip','.rar','.7z','.tar','.gz','.bz2','.xz','.tgz')
    }

    $catCounts = @{ Kod = 0; Web = 0; Dannye = 0; Dok = 0; Izobr = 0; Shrift = 0; Arkhiv = 0; Prochee = 0 }
    $idx = 0

    foreach ($file in $filteredFiles) {
        $idx++
        if ($idx % 50 -eq 0) { Write-ProgressBar $idx $filteredFiles.Count "$idx/$($filteredFiles.Count)" }

        $ext   = $file.Extension.ToLower()
        $found = $false

        foreach ($cat in $categories.Keys) {
            if ($categories[$cat] -contains $ext) { $catCounts[$cat]++; $found = $true; break }
        }
        if (-not $found) { $catCounts['Prochee']++ }
    }
    Write-ProgressDone "Kategorizirovano $($filteredFiles.Count) faylov"

    # --- STEP 5: Extensions ---
    Write-Step 5 6 "Analiz rasshireniy"
    try {
        $extensions = $filteredFiles | Group-Object Extension | Sort-Object Count -Descending | Select-Object -First 20
    } catch { $extensions = @() }
    Write-ProgressDone "Rasshireniya podschitany"

    # --- STEP 6: Big files ---
    Write-Step 6 6 "Poisk bolshikh faylov"
    try {
        $bigFiles = $filteredFiles | Sort-Object Length -Descending | Select-Object -First 10
    } catch { $bigFiles = @() }
    Write-ProgressDone "Top faylov gotov"

    # ========================================================
    #  RESULTS
    # ========================================================

    Write-Host ""
    Write-Title "REZULTATY ANALIZA"

    # --- General ---
    Write-Section "OBSHCHAYA STATISTIKA"
    Write-Host "  |  Vsego faylov (do filtra):  $rawTotal" -ForegroundColor $Colors.Info
    Write-Host "  |  Faylov (posle filtra):     $($filteredFiles.Count)" -ForegroundColor $Colors.Number
    Write-Host "  |  Otfiltrovano:               $filteredOut" -ForegroundColor $Colors.Warning
    Write-Host "  |  Obshchiy razmer:            $(Format-FileSize $totalSize)" -ForegroundColor $Colors.Success
    Write-Host ""

    # --- Categories ---
    Write-Section "KATEGORII FAYLOV"
    $maxCat = 1
    foreach ($v in $catCounts.Values) { if ($v -gt $maxCat) { $maxCat = $v } }

    Draw-Histogram "Iskhodny kod"     $catCounts['Kod']      $maxCat
    Draw-Histogram "Web-fayly"        $catCounts['Web']      $maxCat
    Draw-Histogram "Konfigi / Dannye" $catCounts['Dannye']   $maxCat
    Draw-Histogram "Dokumentatsiya"   $catCounts['Dok']      $maxCat
    Draw-Histogram "Izobrazheniya"    $catCounts['Izobr']    $maxCat
    Draw-Histogram "Shrifty"          $catCounts['Shrift']   $maxCat
    Draw-Histogram "Arkhivy"          $catCounts['Arkhiv']   $maxCat
    Draw-Histogram "Prochee"          $catCounts['Prochee']  $maxCat
    Write-Host ""

    # --- Extensions ---
    Write-Section "TOP RASSHIRENIY"
    foreach ($ext in $extensions) {
        $n = if ($ext.Name) { $ext.Name } else { "[bez rassh.]" }
        Write-Host "  |  $($n.PadRight(15)) $($ext.Count)" -ForegroundColor $Colors.Accent
    }
    Write-Host ""

    # --- Project type ---
    Write-Section "TIP PROEKTA"
    $pt = Detect-ProjectType
    Write-Host "  |  Tip: $($pt.Type)" -ForegroundColor $Colors.Success
    if ($pt.PackageManager) {
        Write-Host "  |  Paket-menedzher: $($pt.PackageManager)" -ForegroundColor $Colors.Accent
    }
    Write-Host "  |  Obnaruzhennye markery:" -ForegroundColor $Colors.Muted
    foreach ($m in $pt.Markers) {
        Write-Host "  |   + $m" -ForegroundColor $Colors.Info
    }
    Write-Host ""

    # --- Big files ---
    Write-Section "TOP-10 BOLSHIKH FAYLOV"
    $rank = 0
    foreach ($file in $bigFiles) {
        $rank++
        try { $rel = $file.FullName.Replace($TargetDir, "").TrimStart('\') } catch { $rel = $file.Name }
        Write-Host "  |  $rank. $((Format-FileSize $file.Length).PadLeft(10))  $rel" -ForegroundColor $Colors.Path
    }
    Write-Host ""

    Write-Host "  Analiz zavershyon!" -ForegroundColor $Colors.Success
    Write-Host ""
    Read-Host "  Nazhmite Enter dlya prodolzheniya"
}

# ============================================================
#  PROJECT TYPE
# ============================================================

function Detect-ProjectType {
    $result = @{ Type = "Neopredelyon"; PackageManager = $null; Markers = @() }

    $markers = @(
        @{ File = "package.json";        Type = "Node.js" },
        @{ File = "package-lock.json";   PM   = "npm" },
        @{ File = "yarn.lock";           PM   = "yarn" },
        @{ File = "pnpm-lock.yaml";      PM   = "pnpm" },
        @{ File = "tsconfig.json";       Marker = "tsconfig.json (TypeScript)" },
        @{ File = "requirements.txt";    Type = "Python"; Marker = "requirements.txt" },
        @{ File = "pyproject.toml";      Type = "Python"; Marker = "pyproject.toml" },
        @{ File = "setup.py";            Marker = "setup.py" },
        @{ File = "Pipfile";             Marker = "Pipfile" },
        @{ File = "manage.py";           Type = "Django (Python)" },
        @{ File = "pom.xml";             Type = "Java (Maven)" },
        @{ File = "build.gradle";        Type = "Java/Kotlin (Gradle)" },
        @{ File = "Cargo.toml";          Type = "Rust" },
        @{ File = "go.mod";              Type = "Go" },
        @{ File = "Gemfile";             Type = "Ruby" },
        @{ File = "composer.json";       Type = "PHP (Composer)" },
        @{ File = "CMakeLists.txt";      Type = "C/C++ (CMake)" },
        @{ File = "Makefile";            Marker = "Makefile" },
        @{ File = "Dockerfile";          Marker = "Dockerfile" },
        @{ File = "docker-compose.yml";  Marker = "docker-compose.yml" },
        @{ File = ".gitignore";          Marker = ".gitignore" },
        @{ File = "README.md";           Marker = "README.md" },
        @{ File = "LICENSE";             Marker = "LICENSE" }
    )

    foreach ($m in $markers) {
        if (Test-Path (Join-Path $TargetDir $m.File)) {
            if ($m.Type)   { $result.Type = $m.Type }
            if ($m.PM)     { $result.PackageManager = $m.PM }
            if ($m.Marker) { $result.Markers += $m.Marker }
            elseif ($m.File) { $result.Markers += $m.File }
        }
    }

    $pkgJson = Join-Path $TargetDir "package.json"
    if (Test-Path $pkgJson) {
        try {
            $c = Get-Content $pkgJson -Raw
            if ($c -match '"react"')    { $result.Type = "React (Node.js)" }
            if ($c -match '"next"')     { $result.Type = "Next.js" }
            if ($c -match '"vue"')      { $result.Type = "Vue.js" }
            if ($c -match '"@angular')  { $result.Type = "Angular" }
            if ($c -match '"svelte"')   { $result.Type = "Svelte" }
            if ($c -match '"electron"') { $result.Type = "Electron" }
        } catch { }
    }

    if (Test-Path (Join-Path $TargetDir "Dockerfile")) {
        $result.Type += " + Docker"
    }

    return $result
}

# ============================================================
#  3. ADD EXCLUSIONS
# ============================================================

function Invoke-AddExclusion {
    try { Clear-Host } catch { }
    Write-Title "DOBAVLENIE V ISKLYUCHENIYA"

    $items = [System.Collections.ArrayList]@()

    try { $dirs = @(Get-ChildItem -Path $TargetDir -Directory -ErrorAction SilentlyContinue) } catch { $dirs = @() }
    foreach ($d in $dirs) {
        [void]$items.Add([PSCustomObject]@{ Num = $items.Count + 1; Name = $d.Name; Type = "PAPKA"; IsExcluded = Test-IsExcluded $d.Name })
    }

    try { $files = @(Get-ChildItem -Path $TargetDir -File -ErrorAction SilentlyContinue) } catch { $files = @() }
    foreach ($f in $files) {
        [void]$items.Add([PSCustomObject]@{ Num = $items.Count + 1; Name = $f.Name; Type = "FAYL"; IsExcluded = Test-IsExcluded $f.Name })
    }

    Write-Host "  Soderzhimoe kornya:" -ForegroundColor $Colors.Info
    Write-Host ""

    foreach ($item in $items) {
        $mark  = if ($item.IsExcluded) { "[X]" } else { "[ ]" }
        $mc    = if ($item.IsExcluded) { $Colors.Warning } else { $Colors.Muted }
        $name  = if ($item.Type -eq "PAPKA") { "$($item.Name)/" } else { $item.Name }

        Write-Host "  $($item.Num.ToString().PadRight(4))" -NoNewline -ForegroundColor $Colors.Number
        Write-Host "$($mark.PadRight(5))" -NoNewline -ForegroundColor $mc
        Write-Host $name -ForegroundColor $Colors.Info
    }

    Write-Host ""
    Write-Host "  Vvedite: nomer(a) cherez probel, imya, ili 0=nazad" -ForegroundColor $Colors.Muted
    Write-Host ""

    while ($true) {
        $inp = Read-Host "  Isklyuchit"
        if ($inp -eq "0" -or $inp -eq "") { return }

        foreach ($part in ($inp -split '\s+')) {
            if ($part -match '^\d+$') {
                $num = [int]$part
                if ($num -ge 1 -and $num -le $items.Count) {
                    $n = $items[$num - 1].Name
                    if (Test-IsExcluded $n) {
                        Write-Host "  [!] '$n' uzhe v isklyucheniyakh" -ForegroundColor $Colors.Warning
                    } else {
                        [void]$script:UserExcludes.Add($n)
                        Save-UserExcludes
                        Write-Host "  [+] Dobavleno: $n" -ForegroundColor $Colors.Success
                    }
                } else {
                    Write-Host "  [!] Nomer $num vne diapazona 1-$($items.Count)" -ForegroundColor $Colors.Error
                }
            } else {
                if (Test-IsExcluded $part) {
                    Write-Host "  [!] '$part' uzhe v isklyucheniyakh" -ForegroundColor $Colors.Warning
                } else {
                    [void]$script:UserExcludes.Add($part)
                    Save-UserExcludes
                    Write-Host "  [+] Dobavleno: $part" -ForegroundColor $Colors.Success
                }
            }
        }
        Write-Host ""
        Write-Host "  Eshchyo? (nomer/imya ili 0=nazad)" -ForegroundColor $Colors.Muted
    }
}

# ============================================================
#  4. REMOVE EXCLUSIONS
# ============================================================

function Invoke-RemoveExclusion {
    try { Clear-Host } catch { }
    Write-Title "UDALENIE IZ ISKLYUCHENIY"

    Write-Host "  Standartnye (nelzya udalit):" -ForegroundColor $Colors.Muted
    foreach ($excl in $script:DefaultExcludes) {
        Write-Host "   [S] $excl" -ForegroundColor $Colors.Muted
    }

    Write-Host ""
    Write-Host "  Polzovatelskie:" -ForegroundColor $Colors.Info

    if ($script:UserExcludes.Count -eq 0) {
        Write-Host "   (pusto)" -ForegroundColor $Colors.Muted
        Write-Host ""
        Read-Host "  Nazhmite Enter dlya prodolzheniya"
        return
    }

    for ($i = 0; $i -lt $script:UserExcludes.Count; $i++) {
        Write-Host "   $($i + 1). $($script:UserExcludes[$i])" -ForegroundColor $Colors.Info
    }

    Write-Host ""
    Write-Host "  Nomer dlya udaleniya, 'all'=ochistit vsyo, 0=nazad" -ForegroundColor $Colors.Muted
    Write-Host ""

    while ($true) {
        $inp = Read-Host "  Udalit"
        if ($inp -eq "0" -or $inp -eq "") { return }

        if ($inp -eq "all") {
            $script:UserExcludes.Clear()
            Save-UserExcludes
            Write-Host "  [OK] Vse polzovatelskie isklyucheniya udaleny" -ForegroundColor $Colors.Success
            Write-Host ""
            Read-Host "  Nazhmite Enter dlya prodolzheniya"
            return
        }

        if ($inp -match '^\d+$') {
            $num = [int]$inp
            if ($num -ge 1 -and $num -le $script:UserExcludes.Count) {
                $removed = $script:UserExcludes[$num - 1]
                $script:UserExcludes.RemoveAt($num - 1)
                Save-UserExcludes
                Write-Host "  [-] Udaleno: $removed" -ForegroundColor $Colors.Success

                if ($script:UserExcludes.Count -eq 0) {
                    Write-Host "  Spisok pust." -ForegroundColor $Colors.Muted
                    Write-Host ""
                    Read-Host "  Nazhmite Enter dlya prodolzheniya"
                    return
                }

                Write-Host "  Tekushchiy spisok:" -ForegroundColor $Colors.Info
                for ($i = 0; $i -lt $script:UserExcludes.Count; $i++) {
                    Write-Host "   $($i + 1). $($script:UserExcludes[$i])" -ForegroundColor $Colors.Muted
                }
                Write-Host ""
                Write-Host "  Eshchyo? (nomer, 'all' ili 0=nazad)" -ForegroundColor $Colors.Muted
            } else {
                Write-Host "  [!] Nomer vne diapazona" -ForegroundColor $Colors.Error
            }
        } else {
            Write-Host "  [!] Vvedite nomer" -ForegroundColor $Colors.Error
        }
    }
}

# ============================================================
#  5. SHOW EXCLUSIONS
# ============================================================

function Show-Exclusions {
    try { Clear-Host } catch { }
    Write-Title "TEKUSHCHIE ISKLYUCHENIYA"

    Write-Section "STANDARTNYE"
    foreach ($excl in $script:DefaultExcludes) {
        Write-Host "  |   $excl" -ForegroundColor $Colors.Muted
    }

    Write-Section "POLZOVATELSKIE"
    if ($script:UserExcludes.Count -eq 0) {
        Write-Host "  |   (pusto)" -ForegroundColor $Colors.Muted
    } else {
        foreach ($excl in $script:UserExcludes) {
            Write-Host "  |   $excl" -ForegroundColor $Colors.Info
        }
    }

    Write-Host ""
    Read-Host "  Nazhmite Enter dlya prodolzheniya"
}

# ============================================================
#  6. PROJECT TREE
# ============================================================

function Show-ProjectTree {
    try { Clear-Host } catch { }
    Write-Title "DEREVO PROEKTA"

    $depth = Read-Host "  Glubina (1-5, Enter=2)"
    if (-not $depth) { $depth = 2 }
    try { $depth = [Math]::Max(1, [Math]::Min(5, [int]$depth)) } catch { $depth = 2 }

    Write-Host ""
    Write-Host "  Stroyu derevo..." -ForegroundColor $Colors.Info
    Write-Host ""
    Write-Host "  $TargetDir" -ForegroundColor $Colors.Path

    Show-TreeRecursive -Path $TargetDir -Prefix "  " -Level 0 -MaxLevel $depth

    Write-Host ""
    Write-Host "  Gotovo!" -ForegroundColor $Colors.Success
    Write-Host ""
    Read-Host "  Nazhmite Enter dlya prodolzheniya"
}

function Show-TreeRecursive {
    param([string]$Path, [string]$Prefix, [int]$Level, [int]$MaxLevel)

    if ($Level -ge $MaxLevel) { return }

    $items = @()
    try { $items += @(Get-ChildItem -Path $Path -Directory -ErrorAction SilentlyContinue) } catch { }
    try { $items += @(Get-ChildItem -Path $Path -File      -ErrorAction SilentlyContinue) } catch { }

    for ($i = 0; $i -lt $items.Count; $i++) {
        $item       = $items[$i]
        $isLast     = ($i -eq $items.Count - 1)
        $connector  = if ($isLast) { "+-- " } else { "|-- " }
        $nextPrefix = if ($isLast) { "$Prefix    " } else { "$Prefix|   " }

        $isExcluded = Test-IsExcluded $item.Name

        if ($item.PSIsContainer) {
            if ($isExcluded) {
                Write-Host "$Prefix$connector$($item.Name)/ [ISKLYUCHENO]" -ForegroundColor $Colors.Warning
            } else {
                Write-Host "$Prefix$connector$($item.Name)/" -ForegroundColor $Colors.Accent
                Show-TreeRecursive -Path $item.FullName -Prefix $nextPrefix -Level ($Level + 1) -MaxLevel $MaxLevel
            }
        } else {
            $sz = Format-FileSize $item.Length
            if ($isExcluded) {
                Write-Host "$Prefix$connector$($item.Name) ($sz) [ISKLYUCHENO]" -ForegroundColor $Colors.Warning
            } else {
                Write-Host "$Prefix$connector" -NoNewline -ForegroundColor $Colors.Muted
                Write-Host $item.Name -NoNewline -ForegroundColor $Colors.Info
                Write-Host " ($sz)" -ForegroundColor $Colors.Muted
            }
        }
    }
}

# ============================================================
#  7. EXPORT
# ============================================================

function Export-Report {
    try { Clear-Host } catch { }
    Write-Title "EKSPORT OTCHYOTA"

    $defName = "PROJECT_REPORT_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
    $fn = Read-Host "  Imya fayla (Enter = $defName)"
    if (-not $fn) { $fn = $defName }
    $rp = Join-Path $TargetDir $fn

    Write-Host ""
    Write-Host "  Generiruyu otchyot..." -ForegroundColor $Colors.Info

    $report = @"
============================================
 PROJECT STRUCTURE REPORT
 Path : $TargetDir
 Date : $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
============================================

ISKLYUCHENIYA (standartnye):
$($script:DefaultExcludes | ForEach-Object { "  - $_" } | Out-String)
ISKLYUCHENIYA (polzovatelskie):
$(if ($script:UserExcludes.Count -gt 0) { $script:UserExcludes | ForEach-Object { "  - $_" } | Out-String } else { "  (net)" })

DEREVO PROEKTA:
$TargetDir
"@

    $report += Get-TreeText -Path $TargetDir -Prefix "  " -Level 0 -MaxLevel 3

    try {
        $af = @(Get-ChildItem -Path $TargetDir -File -Recurse -ErrorAction SilentlyContinue)
        $ts = ($af | Measure-Object Length -Sum).Sum
        $report += @"

STATISTIKA:
  Vsego faylov: $($af.Count)
  Obshchiy razmer: $(Format-FileSize $ts)
"@
    } catch { }

    try { $report | Out-File -FilePath $rp -Encoding UTF8 } catch {
        Write-Host "  [!] Oshibka zapisi fayla: $_" -ForegroundColor $Colors.Error
        Read-Host "  Nazhmite Enter dlya prodolzheniya"
        return
    }

    Write-Host ""
    Write-Host "  Otchyot sokhranyon: $rp" -ForegroundColor $Colors.Success
    Write-Host ""
    Read-Host "  Nazhmite Enter dlya prodolzheniya"
}

function Get-TreeText {
    param([string]$Path, [string]$Prefix, [int]$Level, [int]$MaxLevel)

    $output = ""
    if ($Level -ge $MaxLevel) { return $output }

    $items = @()
    try { $items += @(Get-ChildItem -Path $Path -Directory -ErrorAction SilentlyContinue) } catch { }
    try { $items += @(Get-ChildItem -Path $Path -File      -ErrorAction SilentlyContinue) } catch { }

    for ($i = 0; $i -lt $items.Count; $i++) {
        $item       = $items[$i]
        $isLast     = ($i -eq $items.Count - 1)
        $connector  = if ($isLast) { "+-- " } else { "|-- " }
        $nextPrefix = if ($isLast) { "$Prefix    " } else { "$Prefix|   " }

        $isExcluded = Test-IsExcluded $item.Name

        if ($item.PSIsContainer) {
            if ($isExcluded) {
                $output += "`n$Prefix$connector$($item.Name)/ [ISKLYUCHENO]"
            } else {
                $output += "`n$Prefix$connector$($item.Name)/"
                $output += Get-TreeText -Path $item.FullName -Prefix $nextPrefix -Level ($Level + 1) -MaxLevel $MaxLevel
            }
        } else {
            if ($isExcluded) {
                $output += "`n$Prefix$connector$($item.Name) ($(Format-FileSize $item.Length)) [ISKLYUCHENO]"
            } else {
                $output += "`n$Prefix$connector$($item.Name) ($(Format-FileSize $item.Length))"
            }
        }
    }

    return $output
}

# ============================================================
#  STARTUP
# ============================================================

if (-not (Test-Path $TargetDir)) {
    Write-Host "  [ERROR] Directory '$TargetDir' not found!" -ForegroundColor Red
    Read-Host "  Press Enter to exit"
    exit 1
}

try { $TargetDir = (Resolve-Path $TargetDir).Path } catch { }

# Show splash
try { Clear-Host } catch { }
Write-Host ""
Write-Host "  ==========================================" -ForegroundColor $Colors.Title
Write-Host "    Project Analyzer v3.3" -ForegroundColor $Colors.Title
Write-Host "  ==========================================" -ForegroundColor $Colors.Title
Write-Host ""
Write-Host "  Target: $TargetDir" -ForegroundColor $Colors.Path
Write-Host "  Script: tools/analyze.ps1" -ForegroundColor $Colors.Muted
Write-Host ""

Show-MainMenu

# ============================================================
#  GLOBAL ERROR CATCH — window never closes silently
# ============================================================

} catch {
    Write-Host ""
    Write-Host "  =========================================" -ForegroundColor Red
    Write-Host "   FATAL ERROR" -ForegroundColor Red
    Write-Host "  =========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  $($_.ScriptStackTrace)"   -ForegroundColor DarkGray
    Write-Host ""
    Read-Host "  Press Enter to exit"
    exit 1
}
