# d4t 取得程式碼（PowerShell 版）— authored 2026-07-30.
#
# 為什麼有兩個版本
# ---------------
# `get_code.py` 用 Python 的 urllib。在鎖很緊的公司機上 urllib 有三個做不到的事：
#   1. 讀不到 PAC（自動設定指令碼）—— py 版靠借 .NET 算，但只拿得到「第一個」proxy
#   2. 不會對 proxy 做 Windows 整合驗證（NTLM / Kerberos）
#   3. PAC 給了多個 PROXY 候選時不會依序 fallback
# 這三件事 .NET **全部原生支援**，而 PowerShell 就是 .NET —— **瀏覽器連得到的
# 東西，PowerShell 通常就連得到**。所以在「py 版被 proxy 拒絕」的機器上先試這個。
#
# 契約跟 py 版完全一樣：讀 tools/FILELIST.txt、逐檔抓、驗 git blob SHA、atomic 寫入。
#
# 怎麼拿到這支
# ------------
# 在 GitHub 上打開 tools/get_code.ps1 → 按右上角的複製鈕 → 貼進記事本存成
# get_code.ps1。然後（PowerShell 預設不准跑腳本，所以用 -ExecutionPolicy Bypass）：
#
#   powershell -ExecutionPolicy Bypass -File .\get_code.ps1
#   powershell -ExecutionPolicy Bypass -File .\get_code.ps1 -Dest D:\tools
#   powershell -ExecutionPolicy Bypass -File .\get_code.ps1 -Ref 5fdbb2a…
#   powershell -ExecutionPolicy Bypass -File .\get_code.ps1 -Proxy http://主機:8080

[CmdletBinding()]
param(
    [string]$Dest  = "d4t",
    [string]$Ref   = "main",
    [string]$Proxy = ""
)

$ErrorActionPreference = "Stop"
$Repo     = "hxlub0905-cmyk/d4t"
$Manifest = "tools/FILELIST.txt"

# Windows 8.1 / Server 2012 之後仍有機器的 .NET 預設 TLS 1.0，而 GitHub 只收
# TLS 1.2 以上 —— 不設這行會拿到一個看起來像「被擋」的連線失敗。
try {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls11
} catch { }

function Get-ProxyArgs {
    <# proxy 相關的參數。明講的優先；否則用系統設定（PAC 會被解開），
       並且帶上 Windows 整合驗證 —— 公司 proxy 常常要求它，而那正是
       Python 版做不到的一件事。#>
    if ($Proxy) {
        return @{ Proxy = $Proxy; ProxyUseDefaultCredentials = $true }
    }
    $sys = [System.Net.WebRequest]::GetSystemWebProxy()
    $for = $sys.GetProxy("https://raw.githubusercontent.com/x")
    if ($for -and $for.AbsoluteUri -ne "https://raw.githubusercontent.com/x") {
        return @{ Proxy = $for.AbsoluteUri; ProxyUseDefaultCredentials = $true }
    }
    return @{}          # 不需要 proxy
}

function Get-Text {
    param([string]$Path, [hashtable]$ProxyArgs)
    $url = "https://raw.githubusercontent.com/$Repo/$Ref/$Path"
    # -UseBasicParsing：PS 5.1 沒有它會去叫 IE 引擎（在 Server Core 上會炸）
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 30 @ProxyArgs
    return $r
}

function Get-BlobSha {
    <# git 算 blob SHA 的方式："blob <長度>\0" + 內容。#>
    param([byte[]]$Bytes)
    $head = [Text.Encoding]::ASCII.GetBytes("blob " + $Bytes.Length + "`0")
    $all  = New-Object byte[] ($head.Length + $Bytes.Length)
    [Array]::Copy($head, 0, $all, 0, $head.Length)
    [Array]::Copy($Bytes, 0, $all, $head.Length, $Bytes.Length)
    $sha  = [Security.Cryptography.SHA1]::Create()
    try {
        return (($sha.ComputeHash($all) | ForEach-Object { $_.ToString("x2") }) -join "")
    } finally { $sha.Dispose() }
}

function Write-Atomic {
    param([string]$Root, [string]$Rel, [byte[]]$Bytes)
    $full = Join-Path $Root ($Rel -replace "/", "\")
    $dir  = Split-Path -Parent $full
    if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $tmp = "$full.tmp"
    [IO.File]::WriteAllBytes($tmp, $Bytes)
    Move-Item -LiteralPath $tmp -Destination $full -Force
}

# ---------------------------------------------------------------------------
$proxyArgs = Get-ProxyArgs
# 絕對路徑不可以再跟目前目錄接起來 —— `Join-Path` 會做出 `C:\cur\D:\tools`
# 這種東西，而它**建得起來**，於是檔案安靜地跑到錯的地方去（實測就發生了：
# `-Dest /tmp/x` 寫到了 `<repo>/tmp/x`）。而且 PowerShell 的目前目錄跟 .NET
# 行程的目前目錄是兩件事，所以相對路徑要自己接 `.ProviderPath`。
$destFull = if ([IO.Path]::IsPathRooted($Dest)) {
    [IO.Path]::GetFullPath($Dest)
} else {
    [IO.Path]::GetFullPath((Join-Path (Get-Location).ProviderPath $Dest))
}
Write-Host "來源  : https://raw.githubusercontent.com/$Repo ($Ref)"
Write-Host "目的地: $destFull"
if ($proxyArgs.ContainsKey("Proxy")) {
    Write-Host ("Proxy : " + $proxyArgs.Proxy + "（含 Windows 整合驗證）")
} else {
    Write-Host "Proxy : （不用 proxy，直接連）"
}

try {
    $raw = (Get-Text -Path $Manifest -ProxyArgs $proxyArgs).Content
} catch {
    Write-Host ""
    Write-Host "✗ 抓 $Manifest 失敗：$($_.Exception.Message)"
    $resp = $_.Exception.Response
    if ($resp -and $resp.StatusCode -eq 404) {
        Write-Host "  連得上，但這個分支上沒有這個檔案 —— 檢查 -Ref（現在是 '$Ref'）。"
    } elseif ($resp -and ($resp.StatusCode -eq 407)) {
        Write-Host "  proxy 要求驗證而整合驗證沒過。用 -Proxy 明講位址，"
        Write-Host "  或請 IT 確認你的帳號可以透過 proxy 連 raw.githubusercontent.com。"
    } else {
        Write-Host "  連 PowerShell 也連不到 —— 那就不是 Python 的問題了。剩下的路："
        Write-Host "  1. 請 IT 放行 codeload.github.com（zip 就會回來，這是根治）"
        Write-Host "  2. 在有網路的機器上取得，用你搬 wheels\ 的同一條路搬過來"
    }
    exit 2
}

$want = @()
foreach ($line in ($raw -split "`r?`n")) {
    $line = $line.Trim()
    if ($line -and -not $line.StartsWith("#")) {
        $i = $line.IndexOf(" ")
        if ($i -gt 0) {
            $want += ,@($line.Substring(0, $i), $line.Substring($i + 1))
        }
    }
}
if ($want.Count -eq 0) {
    Write-Host ""
    Write-Host "✗ $Manifest 是空的 —— proxy 可能回了一頁別的東西。"
    exit 2
}
Write-Host "清單  : $($want.Count) 個檔案"
Write-Host ""

# 清單自己不在自己的清單裡（SHA 沒辦法自我包含），但抓下來那份還是要有它。
Write-Atomic -Root $destFull -Rel $Manifest -Bytes ([Text.Encoding]::UTF8.GetBytes($raw))

$bad = @()
$done = 0
foreach ($item in $want) {
    $sha, $path = $item[0], $item[1]
    try {
        $r = Get-Text -Path $path -ProxyArgs $proxyArgs
    } catch {
        $bad += ,@($path, "抓不到：$($_.Exception.Message)")
        continue
    }
    $bytes = $r.RawContentStream.ToArray()
    if ((Get-BlobSha -Bytes $bytes) -ne $sha) {
        # 最常見的原因不是「檔案壞了」，是 proxy 回了一頁 HTML（而且 HTTP 200）
        $why = "內容不是預期的（可能是 proxy 的攔截頁）"
        if ($bytes.Length -gt 0 -and $bytes[0] -eq 0x3C) { $why += "；開頭是 '<'，看起來真的是 HTML" }
        $bad += ,@($path, $why)
        continue
    }
    Write-Atomic -Root $destFull -Rel $path -Bytes $bytes
    $done++
    if (($done % 25) -eq 0 -or $done -eq $want.Count) { Write-Host "  $done / $($want.Count)" }
}

if ($bad.Count -gt 0) {
    Write-Host ""
    Write-Host "✗ $($bad.Count) 個檔案沒抓成功："
    foreach ($b in ($bad | Select-Object -First 12)) { Write-Host ("    " + $b[0] + "  " + $b[1]) }
    Write-Host ""
    Write-Host "  這份程式碼不完整，不要用。先解決上面的原因再重跑。"
    exit 1
}

Write-Host ""
Write-Host "✓ $done 個檔案都抓下來了，SHA 全部對得上。"
Write-Host ""
Write-Host "下一步："
Write-Host "  cd $destFull"
Write-Host "  python tools\doctor.py        # 環境自檢（會告訴你還缺什麼）"
Write-Host "  相依套件裝不了的話走離線 wheels：docs\OFFLINE-INSTALL.md"
exit 0
