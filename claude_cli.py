"""Shared, resilient wrapper around the `claude` CLI.

Both the daily crawler (`daily_crawler.py`) and the interactive Slack bot
(`slack_bot.py`) shell out to `claude -p --model sonnet` for AI narrative.
Historically each had its own bare `subprocess.run` that, on failure, logged
only `result.stderr` — which `claude` leaves empty when it fails on a
usage/rate limit or auth error (it reports those on *stdout* or via the exit
code). That made failures invisible AND non-retried, so a single transient
blip (e.g. the 08:00 cron hitting a usage window) silently dropped the whole
day's analysis.

`run_claude()` centralizes the invocation with:
  - retry + exponential backoff over transient failures, and
  - rich diagnostics (exit code + stderr + stdout snippet) on every failed
    attempt, surfaced through a caller-supplied `log` callable.

It is Slack/env-independent (only `subprocess`/`time`), mirroring the other
shared helpers (`compare_utils`, `history_engine`). Callers keep their own
graceful-degradation behaviour for the `None` (persistent-failure) return.
"""

import subprocess
import time

# Defaults chosen so a transient failure is retried quickly while a *sustained*
# limit still gives up fast enough not to stall the pipeline. backoff[i] is the
# sleep (seconds) BEFORE attempt i+2; the last value repeats if attempts grow.
DEFAULT_MODEL = "sonnet"
DEFAULT_TIMEOUT = 120
DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF = (5, 15)


def run_claude(
    prompt,
    *,
    model=DEFAULT_MODEL,
    timeout=DEFAULT_TIMEOUT,
    attempts=DEFAULT_ATTEMPTS,
    backoff=DEFAULT_BACKOFF,
    label="",
    log=None,
):
    """Invoke `claude -p --model <model>` feeding `prompt` on stdin, with retries.

    Args:
        prompt:   text piped to claude's stdin.
        model:    model name passed to `--model`.
        timeout:  per-attempt timeout in seconds.
        attempts: total tries (>=1). Retries cover rc!=0, empty stdout,
                  timeouts, and unexpected exceptions alike — all are treated
                  as transient.
        backoff:  sequence of sleep-seconds inserted BETWEEN attempts. Indexed
                  by retry number; the final value repeats if there are more
                  retries than entries. Empty/zero => no delay.
        label:    short context tag (e.g. company name) included in log lines.
        log:      optional callable(str) for diagnostics. `None` silences them.
                  (daily_crawler passes `print`; slack_bot passes
                  `logger.warning`.)

    Returns:
        The trimmed stdout string on success, or `None` if every attempt failed.
        Callers decide how to degrade on `None`.
    """
    attempts = max(1, int(attempts))

    def _log(msg):
        if log:
            try:
                log(msg)
            except Exception:
                # Logging must never break the analysis path.
                pass

    tag = f" [{label}]" if label else ""
    last_reason = "no attempt ran"

    for attempt in range(1, attempts + 1):
        try:
            result = subprocess.run(
                ["claude", "-p", "--model", model],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0 and result.stdout.strip():
                if attempt > 1:
                    _log(f"[claude]{tag} succeeded on attempt {attempt}/{attempts}")
                return result.stdout.strip()
            # claude commonly emits usage/rate-limit or auth errors on stdout
            # (not stderr), so capture both streams plus the exit code.
            last_reason = (
                f"rc={result.returncode} "
                f"stderr={result.stderr.strip()[:300]!r} "
                f"stdout={result.stdout.strip()[:300]!r}"
            )
        except subprocess.TimeoutExpired:
            last_reason = f"timeout after {timeout}s"
        except FileNotFoundError:
            # `claude` not on PATH — retrying cannot help; fail fast.
            _log(f"[claude]{tag} executable not found on PATH; aborting")
            return None
        except Exception as e:  # pragma: no cover - defensive
            last_reason = f"exception: {e!r}"

        _log(f"[claude]{tag} attempt {attempt}/{attempts} failed: {last_reason}")

        if attempt < attempts:
            delay = backoff[min(attempt - 1, len(backoff) - 1)] if backoff else 0
            if delay > 0:
                time.sleep(delay)

    _log(f"[claude]{tag} giving up after {attempts} attempt(s): {last_reason}")
    return None
