# INSTALL / ENVIRONMENT

This file contains platform-specific instructions for installing `ffmpeg`/`ffprobe` if you need them. The main `README.md` points here for details.

## Windows

- Install with Chocolatey (run PowerShell as Administrator):

```powershell
choco install ffmpeg
```

- Install with winget:

```powershell
winget install --id Gyan.FFmpeg
```

- Manual download:
  1. Download a static build (e.g. from https://www.gyan.dev/ffmpeg/builds/).
  2. Unzip and add the `bin` folder to your PATH.

Safe PowerShell method to add the bin folder to User PATH (avoids `setx` truncation):

```powershell
$bin = 'C:\path\to\ffmpeg\bin'
$user = [Environment]::GetEnvironmentVariable('PATH','User')
if (-not $user) { $user = '' }
if (-not ($user.Split(';') -contains $bin)) {
  $new = ($user.TrimEnd(';') + ';' + $bin).TrimStart(';')
  [Environment]::SetEnvironmentVariable('PATH',$new,'User')
  Write-Host 'User PATH updated'
} else { Write-Host 'Bin already in User PATH' }
```

Verify:

```powershell
where.exe ffprobe
ffprobe -version
```

## macOS

```bash
brew install ffmpeg
which ffprobe
ffprobe -version
```

## Linux

- Debian/Ubuntu:

```bash
sudo apt update
sudo apt install ffmpeg
which ffprobe
ffprobe -version
```

- Fedora:

```bash
sudo dnf install ffmpeg
```

## Troubleshooting

- If `ffprobe` is not found after install, restart your terminal or IDE.
- If PATH got truncated by `setx`, edit PATH manually via **System Properties → Environment Variables** or restore missing entries from Machine PATH.
- As an alternative, run the script with the ffprobe folder added to the session PATH:

```powershell
$env:PATH = "$env:PATH;C:\path\to\ffmpeg\bin"
python vedio.py C:\path\to\video.mp4 --out-dir C:\path\to\jsons
```
