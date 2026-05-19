# automation/

macOS launchd automation + Cowork monitoring dashboard for the paper
recommendation pipeline in [`../skills/`](../skills/).

The `skills/` directory above defines _what_ the pipeline does (fetch, score,
review, take notes). This `automation/` directory defines _when_ and _how_ it
runs on this Mac, and gives you a glanceable status page.

## What's in here

```
automation/
├── install.sh                                  one-shot installer / uninstaller
├── launchd/
│   ├── runner.sh                               daily-papers pipeline runner
│   ├── com.sitongliu.daily-papers.plist        fires runner.sh 9am daily
│   ├── backfill-runner.sh                      weekly wiki backfill runner
│   └── com.sitongliu.backfill-stubs.plist      fires backfill-runner.sh Sun 9am
└── monitor/
    └── paper-pipeline-monitor.html             Cowork artifact source
```

## The two jobs

| Job | Fires | Real cadence | What it does |
|---|---|---|---|
| `com.sitongliu.daily-papers` | every day 9am | every ~3 days (66h throttle) | runs `claude -p "paper recommendations from the last 3 days"` against the Obsidian vault |
| `com.sitongliu.backfill-stubs` | every Sunday 9am | every ~6 calendar days (date diff throttle) | runs `skills/_shared/backfill_empty_stubs.py` + always refreshes the wiki index |

Each job's runner uses a different throttle strategy on purpose:

- **daily-papers** uses an hour-based check (`MIN_INTERVAL_SEC - SLACK_SEC = 66h`). Because launchd only fires at 9am, the effective cadence settles into clean 3-day intervals once `last-run` aligns with that hour.
- **backfill** uses a calendar-day check (`(today - last_d).days >= 6`). This is robust against Mac sleep/wake drift that would otherwise skew an hour-based check over a week.

## How it works

```
launchd ──9am──▶ runner ──throttle ok?──▶ claude -p / python -m skill
                   │                              │
                   ├── on skip ──┐                ├── writes log
                   ├── on fatal ─┼─▶ trap EXIT ──▶│
                   └── on done ──┘                ├── on success: updates last-run
                                                  └── mirrors {last-run,log}
                                                     → Paper_Recommendation/.status/
                                                         (Cowork artifact reads this)
```

**Why launchd fires often but each job is "every N days":** launchd doesn't
have a clean "every N days" primitive — `StartCalendarInterval` is calendrical
(specific hours/minutes/weekdays), and `StartInterval` measures from last
launch, which drifts when the Mac sleeps. Each runner instead fires on a
calendar trigger (daily for daily-papers, weekly for backfill) and
self-throttles using a `*-last-run` timestamp file.

**Why the status mirror:** Cowork explicitly blocks mounting
`~/Library/Application Support/`, but the artifact still needs to read
`last-run` and `runner.log` to render status. The runner copies both files
into `Paper_Recommendation/.status/` on every exit (skip / fatal / success)
via a `trap mirror_status EXIT` hook.

## Install

From the repo root:

```bash
cd automation
./install.sh
```

This will:

1. Create `~/Library/Application Support/daily-papers/` and `Paper_Recommendation/.status/`
2. Copy `runner.sh` (and any other `*.sh` under `launchd/`) into the state dir
3. Substitute `__HOME__` → `$HOME` in each `*.plist` and drop them into `~/Library/LaunchAgents/`
4. `launchctl bootout` + `launchctl bootstrap` to load them
5. Seed `last-run` to now if it doesn't already exist (so the first 9am fire
   after install is a benign skip — no surprise Claude API spend)
6. Run the runner once so the `.status/` mirror has initial content
7. Write a deployed monitor HTML to `~/Library/Application Support/daily-papers/paper-pipeline-monitor.html`

The installer is idempotent — safe to re-run after edits.

### Override paths

The runner respects these env vars; set them before `install.sh` (and put
them into the plist's `EnvironmentVariables` block if you want them persisted
across reboots):

| Variable          | Default                                  |
|-------------------|------------------------------------------|
| `PAPER_REC_PATH`  | `$HOME/Documents/Paper_Recommendation`   |
| `OBSIDIAN_VAULT`  | `$HOME/Documents/Obsidian/Research`      |
| `CLAUDE_BIN`      | `/opt/homebrew/bin/claude`               |

## Uninstall

```bash
./install.sh --uninstall          # remove launchd jobs, keep state files
./install.sh --uninstall --purge  # also wipe ~/Library/Application Support/daily-papers/ and .status/
```

## Cowork monitor

`install.sh` writes a substituted copy of the monitor HTML to:

```
~/Library/Application Support/daily-papers/paper-pipeline-monitor.html
```

To register it as a Cowork artifact, open Cowork and ask:

> Create a Cowork artifact from
> `~/Library/Application Support/daily-papers/paper-pipeline-monitor.html`,
> id `paper-pipeline-monitor`.

The artifact reads `Paper_Recommendation/.status/{last-run,runner.log}` via
the vault MCP, so it stays live without any extra plumbing.

### What the panel shows

**Schedule card** — top-right badge reflects today:

- `等待 fire` (muted) — no log entry for today yet (before 9am, or launchd hasn't fired)
- `今天已 skip` (amber) — runner fired but the throttle blocked the real run
- `今天已运行` (green) — `start:` / `end: rc=0` appeared in today's log

Below the badge: last real run (epoch → local date), next real run (computed
as `last + 66h` rounded up to the next 9am), and the most recent 8 log lines
color-coded by event type.

**Quick run** — four buttons:

| Button                    | What it copies to clipboard                              |
|---------------------------|----------------------------------------------------------|
| 近 3 天论文推荐            | `paper recommendations from the last 3 days`             |
| 编辑 user-config.json      | absolute path to `skills/_shared/user-config.json`        |
| 查看 runner.log            | absolute path to `~/Library/.../daily-papers/runner.log` |
| 打开 Obsidian Vault        | absolute path to `~/Documents/Obsidian/Research`         |

**Conference paper search** — Venue dropdown (split into ML / Healthcare),
Year, optional Topic query, and a healthcare-filter toggle for ML venues
(auto-hidden for healthcare venues). The composed prompt is shown live
beneath the form; clicking the button copies it to clipboard.

### Why the buttons copy to clipboard instead of running directly

Cowork artifacts execute in a sandboxed iframe with three injected APIs:
`callMcpTool`, `askClaude`, `runScheduledTask`. There is no API to inject
text into the chat input, and `<a href="computer://…">` navigation is
blocked by the iframe's URL-scheme policy. So a button literally cannot
"click and run" in the way the chat itself can.

The clipboard model side-steps this: click → text in clipboard → paste
where you actually want it (chat for prompts, Finder `⌘⇧G` for paths).
The toast at the bottom of the artifact confirms each copy.

Two alternatives exist if you ever decide the extra paste is worth more
machinery:

- **Cowork scheduled task + `runScheduledTask`** — works only for fixed
  prompts (i.e., the 3-day recommendation, not conference search where
  venue/year/topic are dynamic). Adds a "permanently disabled" entry to
  your scheduled tasks list.
- **A local shell MCP** that exposes a `run` tool over your real Mac shell.
  True one-click for everything, but you'd install + connect the MCP on
  every machine, and any button click would run arbitrary commands locally —
  worth thinking carefully about before adding that surface.

## Verifying after install

```bash
# 1. launchd loaded both jobs
launchctl list | grep sitongliu
#   →  -   0   com.sitongliu.daily-papers
#      -   0   com.sitongliu.backfill-stubs

# 2. runners are in place and executable
ls -la "$HOME/Library/Application Support/daily-papers/"*.sh

# 3. state mirror exists
ls -la "$HOME/Documents/Paper_Recommendation/.status/"

# 4. force-fire each runner (will skip if seed was just placed,
#    but the trap still mirrors state)
"$HOME/Library/Application Support/daily-papers/runner.sh"
"$HOME/Library/Application Support/daily-papers/backfill-runner.sh"
tail "$HOME/Library/Application Support/daily-papers/runner.log"
tail "$HOME/Library/Application Support/daily-papers/backfill.log"
```

## Force a run before the throttle is up

**daily-papers** (hour-based throttle):

```bash
# Pretend last run was 72h ago
echo $(($(date +%s) - 72*3600)) \
  > "$HOME/Library/Application Support/daily-papers/last-run"
"$HOME/Library/Application Support/daily-papers/runner.sh"
```

**backfill-stubs** (calendar-day-based throttle):

```bash
# Pretend last run was 7 days ago
python3 -c "
from datetime import datetime, timedelta
print(int((datetime.now() - timedelta(days=7)).timestamp()))
" > "$HOME/Library/Application Support/daily-papers/backfill-last-run"
"$HOME/Library/Application Support/daily-papers/backfill-runner.sh"
```

Either is also what to do if a fresh install seeded `*-last-run` to "now" and
you want to skip the first cadence wait.

## Troubleshooting

**`launchctl list | grep sitongliu` shows nothing.**
The plist didn't load. Run `plutil -lint ~/Library/LaunchAgents/com.sitongliu.daily-papers.plist`
to validate syntax, then `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sitongliu.daily-papers.plist`
to load manually. Check the `__HOME__` placeholder was substituted (it should
be your real `/Users/...` path, not the literal string `__HOME__`).

**`last-run` never updates even though 9am has come and gone.**
Either (a) the runner is skipping every fire because the throttle isn't yet
satisfied — check `runner.log` for `skip:` lines and compare hours to the
`>=66h` threshold; or (b) the Claude CLI returned a non-zero exit (look for
`end: rc=<nonzero>` and `not updating last-run because rc=...`).

**The monitor artifact shows "未同步".**
The `trap mirror_status EXIT` only fires after at least one runner invocation.
Either wait for the next 9am, or run the runner manually once:
`"$HOME/Library/Application Support/daily-papers/runner.sh"`.

**The plist refers to a `__HOME__` path literally.**
You copied the source plist instead of letting `install.sh` substitute it.
Re-run `./install.sh`.

## Re-installing on a new Mac

```bash
git clone <this repo> ~/Documents/Paper_Recommendation
cd ~/Documents/Paper_Recommendation/automation
./install.sh
```

That's it — `__HOME__` is resolved at install time, so the plists are
portable. Assuming the new Mac uses the same Obsidian vault layout
(`~/Documents/Obsidian/Research`) and has `claude` at `/opt/homebrew/bin/claude`,
nothing else needs to change. Otherwise set the env-var overrides above.

## File layout after install

```
~/Library/LaunchAgents/
  com.sitongliu.daily-papers.plist           ← launchd reads these
  com.sitongliu.backfill-stubs.plist

~/Library/Application Support/daily-papers/
  runner.sh                                  ← daily-papers runner
  backfill-runner.sh                         ← weekly backfill runner
  paper-pipeline-monitor.html                ← deployed monitor source
  last-run                                   ← daily-papers last success (epoch)
  backfill-last-run                          ← backfill last success (epoch)
  runner.log                                 ← daily-papers fires (skip + run)
  backfill.log                               ← backfill fires (skip + run)
  launchd.{out,err}.log                      ← daily-papers launchd stdio
  backfill.launchd.{out,err}.log             ← backfill launchd stdio

~/Documents/Paper_Recommendation/.status/    ← mirrors, read by Cowork artifact
  last-run
  runner.log
  backfill-last-run
  backfill.log
```
