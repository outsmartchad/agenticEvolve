---
name: cron-manager
description: ALWAYS read this skill for cron, schedule, recurring job, reminder, periodic task, "run every", "set up automated", or "show my scheduled/active jobs". Manages all timed/repeating agent tasks.
argument-hint: /cron add "every 2h" "Scan GitHub trending for useful dev tools"
disable-model-invocation: true
allowed-tools: Bash(python3 *), Read, Write
---

# Cron Manager

Manage agent-scheduled recurring tasks. Jobs are stored in `~/.agenticEvolve/cron/jobs.json`.

## Commands

### Add a job
```
/cron add "<schedule>" "<prompt>" [--deliver <platform>]
```

Schedule formats:
- Cron expression: `"0 9 * * *"` (9am daily)
- Interval: `"every 2h"`, `"every 30m"`, `"every 1d"`
- Relative: `"in 30m"`, `"in 2h"` (one-shot)

### List jobs
```
/cron list
```

### Remove a job
```
/cron remove <job_id>
```

### Pause/resume
```
/cron pause <job_id>
/cron resume <job_id>
```

## Procedure

### Adding a job

1. Read the current jobs file:
```bash
cat ~/.agenticEvolve/cron/jobs.json 2>/dev/null || echo '[]'
```

2. Parse the schedule. Convert human-readable schedules to cron expressions:
   - `"every 2h"` → `interval_seconds: 7200`
   - `"every 30m"` → `interval_seconds: 1800`
   - `"0 9 * * *"` → `cron: "0 9 * * *"`
   - `"in 30m"` → `run_at: <ISO timestamp 30m from now>`, `once: true`

3. Create the job object:
```json
{
  "id": "<8-char hex>",
  "prompt": "the task prompt",
  "schedule_type": "interval|cron|once",
  "schedule_value": "...",
  "deliver_to": "telegram|discord|whatsapp|local",
  "deliver_chat_id": "...",
  "created_at": "ISO timestamp",
  "next_run_at": "ISO timestamp",
  "run_count": 0,
  "paused": false
}
```

4. Append to the jobs array and write back:
```bash
python3 -c "
import json, os
from datetime import datetime, timezone
path = os.path.expanduser('~/.agenticEvolve/cron/jobs.json')
os.makedirs(os.path.dirname(path), exist_ok=True)
jobs = json.loads(open(path).read()) if os.path.exists(path) else []
new_job = {  # fill in details
}
jobs.append(new_job)
with open(path, 'w') as f:
    json.dump(jobs, f, indent=2)
"
```

5. Report: "Scheduled: <summary>. Next run at <time>."

### Self-contained prompts

Cron prompts run in fresh sessions with no conversation history. They must be fully self-contained:

Bad: "Check on that deployment"
Good: "Check the status of the API deployment at ~/projects/myapi. Run the health check endpoint and report any errors."

## Important Notes

- The cron scheduler runs inside the gateway process (not OS cron)
- Jobs only execute while `ae gateway` is running
- Each job invokes `claude -p` with the job's prompt
- Output is delivered to the specified platform
- Job output is saved to `~/.agenticEvolve/cron/output/<job_id>/`
