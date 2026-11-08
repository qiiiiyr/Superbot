# Setting up superbot (Windows)

This guide assumes you have never done this before. Each step is one thing to type in **PowerShell** (Start menu → type "PowerShell" → open it).

## 1. Install uv (one time)

uv installs Python and everything the bot needs.

```powershell
winget install --id=astral-sh.uv -e
```

Close PowerShell and open it again so it can find `uv`.

## 2. Go to the bot's folder

```powershell
cd path\to\dropship-superbot
```

## 3. Tell uv where to keep its files (every new PowerShell window)

The bot's folder path is very long, and that breaks one of the database libraries on Windows. So the bot's Python environment lives in a short folder instead:

```powershell
$env:UV_PROJECT_ENVIRONMENT = 'C:\Users\riqi2\sb-venv'
```

To make this permanent so you never type it again:

```powershell
[Environment]::SetEnvironmentVariable('UV_PROJECT_ENVIRONMENT', 'C:\Users\riqi2\sb-venv', 'User')
```

## 4. Install the bot

```powershell
uv sync
```

## 5. Add your settings

1. Copy the example file: `copy .env.example .env`
2. Open `.env` in Notepad: `notepad .env`
3. After `ANTHROPIC_API_KEY=`, paste your key from https://console.anthropic.com → **API Keys**. You need to add a small amount of credit there first.
4. `MONTHLY_LLM_CAP_CENTS=500` means the bot stops using AI after it has spent **$5 this month**. Change it if you want.

`.env` holds your secrets. Never send it to anyone or upload it anywhere.

## 6. Start the bot

```powershell
uv run superbot
```

When you see `ready — open http://127.0.0.1:8000`, it is running. Leave the window open. Press **Ctrl+C** to stop it.

## 7. Open the dashboard

Open **http://127.0.0.1:8000** in your browser. It has four pages:

- **Approvals:** everything the bot wants to do, waiting for you. Click **Approve** or **Reject**. Approved actions run within 30 seconds.
- **History:** what ran, what failed, and why. A yellow row marked **Interrupted, check manually** means the bot was cut off mid-action: check it yourself before doing anything else.
- **Status:** running or paused, a **Pause everything** button, this month's AI spending, and when the background jobs last ran.
- **Logs:** the last 200 lines of the log.

The dashboard only works on this PC. Other computers can't reach it, and other websites can't press its buttons. If port 8000 is already taken, put `DASHBOARD_PORT=8001` in `.env`.

The bot never spends money or publishes anything by itself. Everything risky waits for your approval, and anything you don't approve within 48 hours expires.

## 8. Pause from PowerShell

Use the **Pause everything** button on the Status page, or type this in a second PowerShell window (in the same folder):

```powershell
uv run superbot pause
uv run superbot resume
```

While paused you can still approve or reject things, but nothing runs until you resume. You can also put `PAUSED=true` in `.env` to keep the bot paused every time it starts.

## Where things are

| What | Where |
|---|---|
| Log of what the bot did | `data\logs\superbot.log` |
| The bot's database (approvals, AI spending) | `data\superbot.db` |
| Your settings and keys | `.env` |

If something failed mid-run (for example, the PC lost power), the bot marks it **failed — check manually** on the next start instead of trying again. Check it yourself (for example, whether the order was really placed) before doing anything else with it.
