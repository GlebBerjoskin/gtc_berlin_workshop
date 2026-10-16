# GTC Berlin workshop: LLM inference for agentic workflow

Files for the workshop Devlab (JupyterLab with Docker and NVIDIA OpenShell).
They go on top of the course agent in `/workspace/research`.

## What's here

`research/` holds files that replace the ones in `/workspace/research`:

- `prompts.py`, `agents.py`: the pre-call brief agent. A lead agent, a scout,
  a prospect researcher, competitor researchers (at most 3) and a fact checker.
  The output is a one-page brief for an account executive, every fact sourced.
- `tools.py`: the course search tool, plus one fix: a failed search is retried
  once, then returned to the model as an error instead of ending the run.
- `00_demo.ipynb`: the opening demo. A clean input and a real CRM record, run
  in the background, with the plan, the searches and the brief.
- `01_token_factory.ipynb`: direct calls to Token Factory and a micro-benchmark
  for the fact-checker role, to pick a model per role in seconds.
- `02_full_agent.ipynb`: your own run, followed role by role, then your numbers
  for the cost estimate and where to change the agent.
- `workshop.py`: helpers for the notebooks: `prepare()`, `start()`, `status()`,
  `show()`, `log()`, and after a run `files()`, `trace()`, `changes()`,
  `check()`. Runs through `openshell/run.py` like the course notebook.

The OpenShell policy, the tools and the run wrapper stay the same.

## Get the files

Run this in a notebook cell. It keeps a `.orig` copy of each file it replaces.

```python
import io, shutil, tarfile, urllib.request
from pathlib import Path

url = 'https://github.com/GlebBerjoskin/gtc_berlin_workshop/archive/refs/heads/main.tar.gz'
project = Path('/workspace/research')
with tarfile.open(fileobj=io.BytesIO(urllib.request.urlopen(url).read())) as tar:
    for member in tar.getmembers():
        parts = Path(member.name).parts
        if member.isfile() and len(parts) > 2 and parts[1] == 'research':
            target = project.joinpath(*parts[2:])
            backup = target.with_name(target.name + '.orig')
            if target.exists() and not backup.exists():
                shutil.copyfile(target, backup)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(tar.extractfile(member).read())
            print('updated', target)
```

To go back to the course agent:

```python
for backup in Path('/workspace/research').rglob('*.orig'):
    shutil.copyfile(backup, backup.with_name(backup.name.removesuffix('.orig')))
    print('restored', backup.with_name(backup.name.removesuffix('.orig')))
```

## Run a brief

Open `02_full_agent.ipynb` and run the cells in order. Or, from any notebook in
`/workspace/research`:

```python
from workshop import prepare, start, status, show
prepare()
start('clean', 'We sell HR and payroll software to small and mid-size companies in Europe, '
               'like Personio. Brief me for a call with <prospect> in 1 hour. Source every claim.')
status()
show('clean')
```

Files of every run are in `runs/<run-id>/`, logs in `runs/_logs/`.

Based on the Nebius Academy deep research course agent.
