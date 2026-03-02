@echo off
rem OpenClaw Gateway (v2026.2.1)
set PATH=C:\Users\superma\.bun\bin;D:\Programs\anaconda3;D:\Programs\anaconda3\Library\mingw-w64\bin;D:\Programs\anaconda3\Library\usr\bin;D:\Programs\anaconda3\Library\bin;D:\Programs\anaconda3\Scripts;D:\Programs\anaconda3\bin;C:\Python313\Scripts;C:\Python313;D:\Program Files\MySQL\MySQL Server 8.0\bin;C:\Windows\system32;C:\Windows;C:\Windows\System32\Wbem;C:\Windows\System32\WindowsPowerShell\v1.0;C:\Windows\System32\OpenSSH;C:\Program Files\Git\cmd;C:\Program Files (x86)\NVIDIA Corporation\PhysX\Common;D:\Program Files (x86)\NetSarang\Xshell 7;D:\Program Files (x86)\NetSarang\Xftp 7;D:\Programs\mingw64\bin;D:\Programs\mingw64;D:\Programs\upx-4.2.4-win64;D:\Program Files\rust\.rustup;D:\Program Files\rust\.cargo;C:\Program Files\dotnet;D:\Programs\ffmpeg-7.1.1-full_build\bin;C:\Program Files\nodejs;C:\ProgramData\chocolatey\bin;D:\ProgramData\Microsoft VS Code\bin;C:\Program Files\GitHub CLI;C:\Program Files\Redis;C:\Program Files\Docker\Docker\resources\bin;D:\Programs\anaconda3\condabin;.;C:\Users\superma\AppData\Roaming\npm;D:\Programs\Antigravity\bin
set OPENCLAW_GATEWAY_PORT=18789
set OPENCLAW_GATEWAY_TOKEN=305de1d4781421b48d2cdc457d1f9bdb207c32102d558cfb
set OPENCLAW_SYSTEMD_UNIT=openclaw-gateway.service
set OPENCLAW_SERVICE_MARKER=openclaw
set OPENCLAW_SERVICE_KIND=gateway
set OPENCLAW_SERVICE_VERSION=2026.2.1
"C:\Program Files\nodejs\node.exe" D:\Temp\Roaming_Data\npm\node_modules\openclaw\dist\index.js gateway --port 18789
