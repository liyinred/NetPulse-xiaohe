# NetPulse

## FastAPI 中央服务

在项目根目录激活 `pcdn-tx` Conda 环境并启动服务：

```powershell
conda activate pcdn-tx
uvicorn app.main:app --reload --app-dir central_service_FastAPI --host 0.0.0.0 --port 8086
```

## Vue3 前端部署

在 `NetPulse` 文件夹根目录执行以下 shell 命令，删除旧的 `dist` 文件夹并解压新的构建产物：

```bash
sudo rm -rf frontend_Vue3/dist && sudo unzip -o frontend_Vue3/dist.zip -d frontend_Vue3/dist
```

## Go Agent

Go Agent 位于 `terminal_agent_Golang`，要求 Go 1.22 或更高版本。以下命令均在 `terminal_agent_Golang` 目录执行。

### 直接运行

```powershell
go run .
```

`go run .` 适合开发调试。程序会根据 Go 临时可执行文件的位置创建 `config.yaml`；需要持久保存配置时，请构建并运行下方的可执行文件。

### Windows EXE

```powershell
go build -trimpath -ldflags="-s -w" -o netpulse-agent.exe
```

构建产物：

```text
netpulse-agent.exe
```

运行：

```powershell
.\netpulse-agent.exe
```

### Windows 交叉编译 Linux amd64

在 PowerShell 中执行：

```powershell
$env:GOOS = "linux"; $env:GOARCH = "amd64"; $env:CGO_ENABLED = "0"; go build -trimpath -ldflags="-s -w" -o netpulse-agent-linux-amd64; Remove-Item Env:GOOS, Env:GOARCH, Env:CGO_ENABLED
```

构建产物：

```text
netpulse-agent-linux-amd64
```

### Linux 本机编译 amd64

```bash
GOOS=linux GOARCH=amd64 CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o netpulse-agent-linux-amd64
chmod +x netpulse-agent-linux-amd64
./netpulse-agent-linux-amd64
```

生成的 Agent 是单个可执行文件，不需要额外复制 Go 依赖。程序首次运行时会在可执行文件所在目录创建外部配置文件 `config.yaml`，因此该目录需要具备写权限。

## Git 提交推送

将本地 `main` 分支的提交以 `--amend` 方式补充到当前提交，并强制推送到远端 `origin` 和 `github` 的 `wenhao666` 分支：

```bash
git add . && git commit --amend --no-edit && git push --force-with-lease origin main:wenhao666 && git push --force-with-lease github main:wenhao666
```
