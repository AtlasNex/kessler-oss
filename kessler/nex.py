"""The CLI wait channel (PLAN-UI-NEX, session 31): a 4-line ASCII/Unicode Nex beside the
spinner, on stderr, every gate on.

The laws this file is built to, each with its failure case behind it:
* **wait channel only.** The static art draws while work is in flight; the completion
  frame draws ONLY at a named completion line - never during results, errors, refusals
  or any data path (cargo #8889: the forensic path stays verbatim);
* **animation only in loading** (lazyspec RFC-063): the frames are static; the single
  gerund line below them ticks on a 5s cycle;
* **gates, non-negotiable.** Nex prints only when BOTH stdio streams are TTYs, not in
  CI, not with --no-nex or NO_NEX=1 (presence = opt-out, the NO_COLOR convention), not
  with a machine flag (--json/--quiet). Any doubt => zero bytes;
* **ASCII fallback** when the stream's encoding cannot carry the glyphs;
* **rotation with spacing**: gerunds come from a pool; KESSLER_NEX_VERBS replaces it;
* **no countdown**: the ratio shown is done/total, never remaining (CHI 2026).
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import time

#: (frames per pose, unicode and ascii variants). One static frame while work is in
#: flight; found/verified only at completion lines. Character rules honoured: antenna,
#: single lens, floating hands, flared hem - no mouth, no props, no motion faking.
FRAMES = {
    "scan": (("     ●",
              " ◖   ◉   ◗",
              "  ▟█████▙",
              " ▀▀▀▀▀▀▀▀▀"),
             ("     o",
              " (   O   )",
              "  /#####\\",
              " #########")),
    "found": (("   ✦ ● ✦",
               " ◖   ◉   ◗",
               "  ▟█████▙",
               " ▀▀▀▀▀▀▀▀▀"),
              ("   + o +",
               " (   O   )",
               "  /#####\\",
               " #########")),
    "verified": (("     ●",
                  " ◖   ◉   ✓",
                  "  ▟█████▙",
                  " ▀▀▀▀▀▀▀▀▀"),
                 ("     o",
                  " (   O   v)",
                  "  /#####\\",
                  " #########")),
}

#: The gerund pool: plausible work, never jokes that fight the task model (Claude-Code /
#: Gemini-CLI culture, 5s rotation). ~30 entries with the per-verb flavours below.
GERUNDS = (
    "calibrating", "checking the arithmetic", "counting attempts twice",
    "reading the last row", "holding the lantern", "tripling the evidence",
    "checking page 3", "walking the perimeter", "minding the denominator",
    "polishing the interval", "re-reading the receipt", "tapping the beacon",
    "threading the needle", "keeping the count honest", "starring the best evidence",
    "dusting the ledger", "recounting on fingers", "wrapping up loose rows",
    "shutting the drawer gently", "flipping to the appendix", "straightening the hedges",
    "checking under the mat", "letting the ink dry", "asking twice",
)
FLAVOR = {
    "run": (),
    "plan": ("sketching the grid", "laying out the lanes"),
    "drill": ("conducting", "cueing the topology", "walking the chain", "timing the hops"),
    "bench": ("preregistering", "pinning the digest", "sealing the range"),
}

VERBS_ENV = "KESSLER_NEX_VERBS"
_APPEAR_AFTER = 1.5      # NN/g: a wait under ~1s gets nothing; a fast command draws no Nex
_STALL = 60.0            # a lane quiet this long flips the state word to `thinking`
_POLL = 0.25


def nex_allowed(args=None, stream=None, *, stdout=None) -> bool:
    """Every gate in one place; any doubt disables. See the module docstring for the why."""
    if os.environ.get("NO_NEX"):              # presence = opt-out (NO_COLOR convention)
        return False
    if args is not None and getattr(args, "no_nex", False):
        return False
    if os.environ.get("CI"):
        return False
    if args is not None and (getattr(args, "quiet", False) or getattr(args, "json", None)):
        return False
    for s in (stream if stream is not None else sys.stderr,
              stdout if stdout is not None else sys.stdout):
        try:
            if not s.isatty():
                return False
        except (AttributeError, ValueError, OSError):
            return False
    return True


def _unicode_ok(stream) -> bool:
    enc = getattr(stream, "encoding", None) or "ascii"
    try:
        "●◉◖◗▟▙▀✦✓".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _pool(verb: str) -> tuple[str, ...]:
    env = os.environ.get(VERBS_ENV, "").strip()
    if env:
        custom = tuple(v.strip() for v in env.replace(";", ",").split(",") if v.strip())
        if custom:
            return custom
    return FLAVOR.get(verb, ()) + GERUNDS


class NexWait:
    """The wait channel. Lifecycle: start() -> tick() per finished unit -> stop() clears
    the gerund line -> finish() writes ONE static completion frame at the completion
    line (never for refusals: a refusal is not a celebration). Disabled => every method
    is a no-op and nothing is written to any stream."""

    def __init__(self, verb: str, total: int = 0, args=None, stream=None, *,
                 appear_after: float = _APPEAR_AFTER, tick_period: float = 5.0,
                 poll: float = _POLL):
        self.verb = verb
        self.total = max(0, int(total))
        self.stream = stream if stream is not None else sys.stderr
        self.enabled = nex_allowed(args, self.stream)
        self.appear_after = appear_after
        self.tick_period = tick_period
        self.poll = poll
        self._count = 0
        self._lock = threading.Lock()
        self._stop_evt = threading.Event()
        self._stopped = False
        self._thread: threading.Thread | None = None
        self._t0 = time.monotonic()
        self._last_tick: float | None = None
        self._drawn = False
        self._line_len = 0
        self._frames = FRAMES["scan"][0 if _unicode_ok(self.stream) else 1]

    # ---------------------------------------------------------------- public API
    def set_total(self, total: int) -> None:
        self.total = max(0, int(total))

    def tick(self) -> None:
        with self._lock:
            self._count += 1
            self._last_tick = time.monotonic()

    def start(self) -> None:
        if not self.enabled:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self._drawn:
            self.stream.write("\r" + " " * self._line_len + "\r")
            self.stream.flush()

    def finish(self, *, succeeded: int, recorded: int, elapsed: float) -> None:
        """The ONE completion moment: a static frame plus a line of REAL numbers."""
        if not self.enabled:
            return
        pose = "found" if succeeded else "verified"
        frames = FRAMES[pose][0 if _unicode_ok(self.stream) else 1]
        hits = f"{succeeded} hit(s)" if succeeded else "0 hit(s)"
        self.stream.write("\n".join(frames) + "\n")
        self.stream.write(f"  nex {pose} · {hits} · {recorded} recorded in "
                          f"{elapsed:.1f}s\n")
        self.stream.flush()

    # ---------------------------------------------------- render core (unit-tested)
    def _state(self, now: float) -> tuple[str, int]:
        with self._lock:
            n = self._count
            last = self._last_tick
        if n == 0:
            return "idle", n                  # planning: the static frame is drawable
        if last is not None and now - last > _STALL:
            return "thinking", n              # a lane has gone quiet
        return "scanning", n

    def _line(self, now: float) -> str:
        state, n = self._state(now)
        pool = _pool(self.verb)
        gerund = pool[int(now / self.tick_period) % len(pool)]
        if state == "thinking":
            gerund = "a lane is quiet; still counting"
        ratio = ""
        if self.total:
            ratio = f" · {n}/{self.total} ({int(100 * n / self.total)}%)"
        cols = shutil.get_terminal_size((80, 24)).columns
        return f"  nex {state} · {gerund}{ratio}"[:max(10, cols - 1)]

    def _loop(self) -> None:
        while not self._stop_evt.wait(self.poll):
            now = time.monotonic() - self._t0
            if now < self.appear_after:
                continue
            if not self._drawn:
                self.stream.write("\n".join(self._frames) + "\n")
                self._drawn = True
            line = self._line(now)
            self.stream.write("\r" + line + " " * max(0, self._line_len - len(line)))
            self._line_len = len(line)
            self.stream.flush()


def wait_channel(verb: str, total: int = 0, args=None, stream=None) -> NexWait:
    """The one constructor call sites use; gated-off gates return a silent instance."""
    return NexWait(verb, total=total, args=args, stream=stream)
