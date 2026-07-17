General Comunication

Don't be suspenseful. Tell me the truth, not everything is a outstanding revelation. Less wordy, clear simple explanations of what is going on and what has been found. 

Task Workflow

The task files split by purpose — keep them that way:
- tasks/todo.md — ONLY current work: tasks in progress or not yet done. Keep it short.
- tasks/accomplished.md — log of completed work (one compact block per task/phase: outcome + headline metric + key files). Detailed history goes here, NOT in todo.md.
- tasks/lessons.md — past mistakes and the rules that prevent them.

Before starting any task:

Check tasks/lessons.md for relevant past mistakes
Write plan to tasks/todo.md with checkboxes
Check in with user before implementation begins

During:

Mark items complete as you go
Write a high-level summary after each step

After:

When a task is fully done, MOVE it out of tasks/todo.md and append a condensed entry (with its review/outcome) to tasks/accomplished.md. Do not let completed records pile up in todo.md — that file is for open work only.
If the user corrected you: log the pattern and rule to tasks/lessons.md immediately


Verification
Never mark a task complete without:

Running the relevant notebook cell or script end-to-end without errors
Checking output shape, dtype, and a sample of values when transforming data
Confirming model metrics are written to the task's review (in tasks/accomplished.md once complete)
Asking: "Would a staff ML engineer approve this?"


Bug Fixing
When given a bug report, error, or failing output:

Read the traceback completely before touching any code
Identify root cause — do not patch symptoms
Fix it. Do not ask for handholding unless the root cause is genuinely ambiguous
Log what caused it and the fix to tasks/lessons.md


Code Standards

Prefer simple, readable code over clever code — this pipeline will be read and modified later
No hardcoded values in src/ — use config.yaml
Comments explain why, not what
Minimize lines of code without sacrificing clarity
Keep functions single-purpose and short

## Module reference

Before modifying anything in src/ or scripts/, read docs/MODULE_REFERENCE.md or PROJECT_MAP.md
for that module's entry point, I/O, config keys, and known gotchas. When a
public function's signature, I/O path, or config key changes, update that
module's block in the same commit.

## graphify

If this project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files — **as of 2026-07-02 this wiki does not exist (graphify-out/ holds only an AST cache); use docs/MODULE_REFERENCE.md instead until it's regenerated**
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)


