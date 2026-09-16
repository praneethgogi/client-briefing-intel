# Runs the evaluation gate. Add -Offline to skip the LLM.
param([switch]$Offline)
if ($Offline) { .\.venv\Scripts\python.exe -m evals.run_evals --offline } else { .\.venv\Scripts\python.exe -m evals.run_evals }
