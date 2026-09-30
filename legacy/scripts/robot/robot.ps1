# Varlamov Shorts robot: executes jobs from .\queue (download / thumb / info / ytlist / transcribe / prep)
$ErrorActionPreference = 'Continue'
$Root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$Shorts = Split-Path -Parent $Root
$Bin    = Join-Path $Root 'bin'
$Q = Join-Path $Root 'queue'; $Done = Join-Path $Root 'done'; $Fail = Join-Path $Root 'failed'; $Logs = Join-Path $Root 'logs'
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$env:PYTHONIOENCODING = 'utf-8'

# single instance: Windows scheduler may start us every 5 min; extra copies exit at once
$Mutex = New-Object System.Threading.Mutex($false, 'Local\VarlamovShortsRobot')
if(-not $Mutex.WaitOne(0)){ exit }
function Log($m){ $l = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m; Write-Host $l; [IO.File]::AppendAllText((Join-Path $Logs 'robot.log'), $l + "`r`n", $utf8) }

function Find-Tool($name, $cands){
  foreach($c in $cands){ if($c -and (Test-Path $c)){ return (Resolve-Path $c).Path } }
  $cmd = Get-Command $name -ErrorAction SilentlyContinue; if($cmd){ return $cmd.Source }
  return $null
}
function Get-YtDlp {
  $p = Find-Tool 'yt-dlp.exe' @("$Bin\yt-dlp.exe")
  if(-not (Test-Path "$Bin\yt-dlp.exe")){
    Log 'yt-dlp not found, downloading official build from github.com/yt-dlp'
    Invoke-WebRequest 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe' -OutFile "$Bin\yt-dlp.exe" -UseBasicParsing
    $p = "$Bin\yt-dlp.exe"
  }
  return $p
}
function Get-FfmpegDir {
  $f = Get-ChildItem "$env:USERPROFILE\.stacher" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
  if($f){ return $f.DirectoryName }
  $c = Get-Command ffmpeg -ErrorAction SilentlyContinue; if($c){ return (Split-Path $c.Source) }
  return $null
}
function Ensure-Deno {
  # modern YouTube needs a JS runtime for yt-dlp to see all formats
  if(Get-Command deno -ErrorAction SilentlyContinue){ return }
  if(Test-Path "$Bin\deno.exe"){ $env:PATH = "$Bin;$env:PATH"; return }
  try {
    Log 'deno not found, downloading from github.com/denoland'
    $z = "$Bin\deno.zip"
    Invoke-WebRequest 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' -OutFile $z -UseBasicParsing
    Expand-Archive $z -DestinationPath $Bin -Force; Remove-Item $z
    $env:PATH = "$Bin;$env:PATH"
  } catch { Log "deno download failed: $_" }
}

function Save-Thumb($j, $dest){
  try {
    $yt = Get-YtDlp; $ff = Get-FfmpegDir
    $ta = @('--skip-download','--no-playlist','--write-thumbnail','--convert-thumbnails','jpg','-o', (Join-Path $dest 'maxresdefault.%(ext)s'))
    if($ff){ $ta += @('--ffmpeg-location', $ff) }
    $o = & $yt @ta $j.url 2>&1
    $o | ForEach-Object { [IO.File]::AppendAllText((Join-Path $Logs ($j._id + '.log')), "$_`r`n", $utf8) }
    $t = Join-Path $dest 'maxresdefault.jpg'
    if(Test-Path -LiteralPath $t){ return 'maxresdefault.jpg' } else { return 'thumb FAILED' }
  } catch { return "thumb FAILED: $_" }
}

function Job-Thumb($j){
  $dest = Join-Path $Shorts $j.folder
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  $r = Save-Thumb $j $dest
  if($r -like '*FAILED*'){ throw $r }
  return @{ thumb = $r }
}

function Job-Download($j){
  $dest = Join-Path $Shorts $j.folder
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  $jobStart = (Get-Date).AddSeconds(-5)
  $yt = Get-YtDlp; $ff = Get-FfmpegDir; Ensure-Deno
  & $yt -U 2>&1 | Out-Null
  $h = if($j.height){ $j.height } else { 1080 }
  $ya = @('-f', "bv*[height=$h][vcodec^=avc1]+ba[ext=m4a]/bv*[height=$h]+ba/bv*[height<=$h]+ba/b[height<=$h]",
            '--merge-output-format','mp4','--no-playlist','--no-part','--windows-filenames',
            '-o', (Join-Path $dest '%(uploader)s - %(title)s.%(ext)s'), '--print', 'after_move:filepath')
  if($ff){ $ya += @('--ffmpeg-location', $ff) }
  & $yt -F $j.url 2>&1 | Select-Object -Last 40 | ForEach-Object { [IO.File]::AppendAllText((Join-Path $Logs ($j._id + '.log')), "$_`r`n", $utf8) }
  $out = & $yt @ya $j.url 2>&1
  $out | ForEach-Object { [IO.File]::AppendAllText((Join-Path $Logs ($j._id + '.log')), "$_`r`n", $utf8) }
  # don't trust console text (Cyrillic gets mangled) - take the newest mp4 in the folder
  $file = (Get-ChildItem -LiteralPath $dest -Filter *.mp4 | Where-Object { $_.LastWriteTime -gt $jobStart } | Sort-Object LastWriteTime | Select-Object -Last 1).FullName
  if(-not $file){ throw "download failed, see logs\$($j._id).log" }
  # file names like the existing ones: ? : | " -> _
  $name = [IO.Path]::GetFileName($file)
  $clean = $name -replace '[\uFF1F\uFF1A\uFF5C\uFF02\u29F8\uFF0A\uFF1C\uFF1E]', '_'
  if($clean -ne $name){ $new = Join-Path $dest $clean; Move-Item -LiteralPath $file -Destination $new -Force; $file = $new }
  $ffprobe = if($ff){ Join-Path $ff 'ffprobe.exe' } else { 'ffprobe' }
  $res = & $ffprobe -v error -select_streams v:0 -show_entries stream=height -of csv=p=0 "$file" 2>$null
  $hgt = [int](("$res" -split ',') | Where-Object { $_ -match '^\d+$' } | Select-Object -First 1)
  if($hgt -ne $h){ throw "got ${hgt}p instead of ${h}p: $file (kept for inspection)" }
  $thumb = Save-Thumb $j $dest
  return @{ file = $file.Substring($Shorts.Length + 1); probe = "$res"; thumb = $thumb }
}

function Job-Info($j){
  # description + chapters (timecodes) + metadata (+ top comments if "comments":true), no video
  $dest = Join-Path $Shorts $j.folder
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  $yt = Get-YtDlp; Ensure-Deno
  $name = if($j.name){ $j.name } else { 'info' }
  $ia = @('--skip-download','--no-playlist','--write-info-json','--write-description','-o', (Join-Path $dest ($name + '.%(ext)s')))
  if($j.comments){ $ia += @('--write-comments','--extractor-args','youtube:max_comments=400,all,0;comment_sort=top') }
  $o = & $yt @ia $j.url 2>&1
  $o | ForEach-Object { [IO.File]::AppendAllText((Join-Path $Logs ($j._id + '.log')), "$_`r`n", $utf8) }
  $f = Join-Path $dest ($name + '.info.json')
  if(-not (Test-Path -LiteralPath $f)){ throw "info failed, see logs\$($j._id).log" }
  return @{ file = $f.Substring($Shorts.Length + 1) }
}

function Job-YtList($j){
  # list a channel tab / playlist / search page without downloading: one JSON per line
  $yt = Get-YtDlp; Ensure-Deno
  $out = Join-Path $Shorts $j.output
  if(Test-Path -LiteralPath $out){ Remove-Item -LiteralPath $out }
  $lim = if($j.limit){ $j.limit } else { 30 }
  $ya = @('--flat-playlist','--playlist-end',"$lim",'--print-to-file','%()j',$out)
  $o = & $yt @ya $j.url 2>&1
  $o | ForEach-Object { [IO.File]::AppendAllText((Join-Path $Logs ($j._id + '.log')), "$_`r`n", $utf8) }
  if(-not (Test-Path -LiteralPath $out)){ throw "ytlist failed, see logs\$($j._id).log" }
  return @{ file = $j.output }
}

function Get-Python {
  $venvPy = Join-Path $Root 'venv\Scripts\python.exe'
  if(Test-Path $venvPy){ return $venvPy }
  $base = $null
  foreach($c in @('py','python')){ $g = Get-Command $c -ErrorAction SilentlyContinue; if($g -and $g.Source -notlike '*WindowsApps*'){ $base = $g.Source; break } }
  if(-not $base){ throw 'Python not found on this PC' }
  Log "creating venv with $base (one time, several minutes)"
  if($base -like '*py.exe'){ & $base -3 -m venv (Join-Path $Root 'venv') } else { & $base -m venv (Join-Path $Root 'venv') }
  & $venvPy -m pip install --upgrade pip 2>&1 | Out-Null
  & $venvPy -m pip install faster-whisper nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" 2>&1 | ForEach-Object { [IO.File]::AppendAllText((Join-Path $Logs 'pip.log'), "$_`r`n", $utf8) }
  return $venvPy
}
function Job-Transcribe($j){
  $py = Get-Python
  $in  = Join-Path $Shorts $j.input
  $out = Join-Path $Shorts $j.output
  $model = if($j.model){ $j.model } else { 'large-v3' }
  $nv = if($j.novad){ 'novad' } else { 'vad' }
  $o = & $py (Join-Path $Root 'transcribe.py') $in $out $model $nv 2>&1
  $o | ForEach-Object { [IO.File]::AppendAllText((Join-Path $Logs ($j._id + '.log')), "$_`r`n", $utf8) }
  if(-not (Test-Path $out)){ throw "transcribe failed, see logs\$($j._id).log" }
  return @{ file = $j.output; info = ($o | Select-Object -Last 1) }
}

function Job-Prep($j, $jobPath){
  # prep: one job -> exact piece boundaries, shots, framing, subtitles, check (logic in prep.py)
  $py = Get-Python
  $ff = Get-FfmpegDir
  if($ff -and ($env:PATH -notlike "*$ff*")){ $env:PATH = "$ff;$env:PATH" }
  $res = Join-Path $Root "work\prep_$($j._id).result.json"
  $lg  = Join-Path $Logs ($j._id + '.log')
  if(Test-Path -LiteralPath $res){ Remove-Item -LiteralPath $res }
  $o = & $py (Join-Path $Root 'prep.py') $jobPath $res $lg 2>&1
  if(-not (Test-Path -LiteralPath $res)){ throw "prep.py не отработал, см. logs\$($j._id).log" }
  $r = [IO.File]::ReadAllText($res, $utf8) | ConvertFrom-Json
  if(-not $r.ok){ throw "$($r.error)" }
  return @{ plan = $r.plan; plan_json = $r.plan_json; srt = $r.srt; total = $r.total; seconds = $r.seconds; warnings = @($r.warnings) }
}

Log "robot started. Shorts = $Shorts"
$Self = $MyInvocation.MyCommand.Path; $SelfTime = (Get-Item $Self).LastWriteTime
while($true){
  [IO.File]::WriteAllText((Join-Path $Root 'alive.txt'), (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $utf8)
  Get-ChildItem $Q -Filter *.json -ErrorAction SilentlyContinue | Sort-Object Name | ForEach-Object {
    $jf = $_; $id = $jf.BaseName
    try {
      $j = [IO.File]::ReadAllText($jf.FullName, $utf8) | ConvertFrom-Json
      $j | Add-Member -NotePropertyName _id -NotePropertyValue $id -Force
      Log "job $id : $($j.type)"
      [IO.File]::WriteAllText((Join-Path $Root 'working.txt'), "$id $($j.type) since $(Get-Date -Format 'HH:mm:ss')", $utf8)
      $r = switch($j.type){ 'download' { Job-Download $j } 'thumb' { Job-Thumb $j } 'info' { Job-Info $j } 'ytlist' { Job-YtList $j } 'transcribe' { Job-Transcribe $j } 'prep' { Job-Prep $j $jf.FullName } default { throw "unknown job type $($j.type)" } }
      $r.ok = $true; $r.finished = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
      [IO.File]::WriteAllText((Join-Path $Done "$id.result.json"), ($r | ConvertTo-Json), $utf8)
      Move-Item $jf.FullName (Join-Path $Done $jf.Name) -Force
      Log "job $id OK"
    } catch {
      Log "job $id FAILED: $_"
      [IO.File]::WriteAllText((Join-Path $Fail "$id.error.txt"), "$_", $utf8)
      Move-Item $jf.FullName (Join-Path $Fail $jf.Name) -Force
    }
    Remove-Item (Join-Path $Root 'working.txt') -ErrorAction SilentlyContinue
  }
  # self-update: if Claude changed this script, restart with the new version
  if((Get-Item $Self).LastWriteTime -ne $SelfTime){ Log 'script updated, restarting'; $Mutex.ReleaseMutex(); $Mutex.Dispose(); Start-Process powershell -WindowStyle Hidden -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File',"`"$Self`"") ; exit }
  Start-Sleep -Seconds 15
}
