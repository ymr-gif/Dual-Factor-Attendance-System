"""Tap ↔ face correlation (Step 31, Flow track).

A tap identifies a student (NFC) and carries their enrolled reference embedding.
The perception service (Step 30) publishes recognized-face embeddings. This matcher
correlates the two within `ASSOC_WINDOW_SEC`, under strict card-required rules, and
emits one outcome (an attendance status) per resolved tap or unclaimed face:

  tap + matching face ≥ threshold        -> accepted (present, verified)
  tap + face below threshold             -> mismatch  (review)
  tap + no face in window                -> no_face   (review)
  matched face, liveness not-live        -> spoof     (review)
  recognized face, no tap claims it      -> tailgating (cardless 1:N name lookup)

Design (design-notes §2/§3): single backend worker, in-process buffers, one shared
host clock for tap + face timestamps. Assignment is optimal (Hungarian) so a burst
of taps and faces is matched globally, not greedily. Buffers are bounded (drop
oldest faces) so backpressure never grows memory unbounded.

Decoupled from I/O for testing: `outcome_sink` (writes the log / notify / broadcast),
`face_search` (cardless 1:N), and `clock` are all injected. `resolve(now)` is pure
w.r.t. the clock so tests drive time explicitly.
"""

import os
from collections import OrderedDict

import numpy as np
from scipy.optimize import linear_sum_assignment

from . import decision, face, liveness


def _env_f(name: str, default: float) -> float:
    return float(os.environ.get(name, str(default)))


ASSOC_WINDOW_SEC = _env_f("ASSOC_WINDOW_SEC", 4.0)
TAP_COOLDOWN_SEC = _env_f("TAP_COOLDOWN_SEC", 2.0)
# Reuse the same cosine cutoff the 1:1 flow uses; overridable for the matcher.
MATCH_THRESHOLD = _env_f("MATCH_THRESHOLD", face.FACE_THRESHOLD)
# Similarity a cardless tailgater lookup must clear to be *named* (else "unknown").
TAILGATE_NAME_THRESHOLD = _env_f("TAILGATE_NAME_THRESHOLD", face.FACE_THRESHOLD)
RESOLVE_INTERVAL_SEC = _env_f("RESOLVE_INTERVAL_SEC", 0.5)
MAX_FACE_BUFFER = int(os.environ.get("MAX_FACE_BUFFER", "256"))
MAX_TAILGATED_TRACKS = int(os.environ.get("MAX_TAILGATED_TRACKS", "512"))

_BIG = 10.0  # cost sentinel for time-invalid tap/face pairs


class PendingTap:
    __slots__ = ("id", "uid", "student_id", "student", "embedding", "ts")

    def __init__(self, tid, uid, student_id, student, embedding, ts):
        self.id = tid
        self.uid = uid
        self.student_id = student_id
        self.student = student
        self.embedding = np.asarray(embedding, dtype=np.float32)
        self.ts = ts


class PendingFace:
    __slots__ = ("track_id", "embedding", "live_score", "is_live", "bbox", "ts", "consumed", "emitted")

    def __init__(self, track_id, embedding, live_score, is_live, bbox, ts):
        self.track_id = track_id
        self.embedding = np.asarray(embedding, dtype=np.float32)
        self.live_score = live_score
        self.is_live = is_live
        self.bbox = bbox
        self.ts = ts
        self.consumed = False
        self.emitted = False


class Matcher:
    def __init__(
        self,
        window=ASSOC_WINDOW_SEC,
        cooldown=TAP_COOLDOWN_SEC,
        threshold=MATCH_THRESHOLD,
        tailgate_threshold=TAILGATE_NAME_THRESHOLD,
        outcome_sink=None,
        face_search=None,
        clock=None,
        max_face_buffer=MAX_FACE_BUFFER,
        max_tailgated_tracks=MAX_TAILGATED_TRACKS,
    ):
        import time as _time

        self.window = window
        self.cooldown = cooldown
        self.threshold = threshold
        self.tailgate_threshold = tailgate_threshold
        self.resolve_interval = RESOLVE_INTERVAL_SEC
        self.outcome_sink = outcome_sink
        self.face_search = face_search
        self.clock = clock or _time.time
        self.max_face_buffer = max_face_buffer
        self.max_tailgated_tracks = max_tailgated_tracks
        # One tailgating verdict per physical presence episode (track_id): a
        # refreshed PendingFace for a track already flagged is the same
        # continuous dwell (perception.py's FACE_REFRESH_SEC re-emits it every
        # few seconds), not a new episode — suppress the duplicate outcome.
        # Bounded/drop-oldest so a long-running kiosk process never grows this
        # unbounded.
        self._tailgated_tracks: OrderedDict = OrderedDict()
        self._taps: list[PendingTap] = []
        self._faces: list[PendingFace] = []
        self._last_tap: dict[str, float] = {}
        self._next_id = 1

    # --- ingest ---

    def add_tap(self, uid, student_id, embedding, student=None, ts=None):
        """Buffer a tap. Returns its id, or None if debounced (held/duplicate card
        within TAP_COOLDOWN_SEC)."""
        now = self.clock() if ts is None else ts
        last = self._last_tap.get(uid)
        if last is not None and now - last < self.cooldown:
            return None
        # Construct before recording the debounce timestamp: if this raises, the
        # tap never entered the buffer, and the caller (the /tap 500) should see
        # the same failure on retry rather than a misleading 'debounced' success.
        t = PendingTap(self._next_id, uid, student_id, student, embedding, now)
        self._next_id += 1
        self._last_tap[uid] = now
        self._taps.append(t)
        return t.id

    def on_face(self, ev):
        """Sink for perception face events (register via perception.on_face)."""
        f = PendingFace(
            track_id=ev.get("track_id"),
            embedding=ev["embedding"],
            live_score=ev.get("live_score"),
            is_live=ev.get("is_live"),
            bbox=ev.get("bbox"),
            ts=ev.get("ts") if ev.get("ts") is not None else self.clock(),
        )
        self._faces.append(f)
        if len(self._faces) > self.max_face_buffer:
            # Bounded buffer: drop oldest un-emitted faces (design-notes backpressure).
            self._faces = self._faces[-self.max_face_buffer :]

    # --- resolve ---

    def resolve(self, now=None):
        """Resolve every tap whose window has closed and every unclaimed ripe face.
        Emits each outcome through outcome_sink and returns the list of outcomes."""
        if now is None:
            now = self.clock()
        outcomes = []

        ripe_taps = [t for t in self._taps if now - t.ts >= self.window]
        if ripe_taps:
            faces = [f for f in self._faces if not f.consumed]
            assignment = self._assign(ripe_taps, faces)
            for i, t in enumerate(ripe_taps):
                j = assignment.get(i)
                if j is None:
                    # No time-valid face left for this tap (none, or all taken).
                    outcomes.append(self._no_face(t))
                    continue
                # An assigned face is time-valid; it is accounted for by this tap's
                # verdict (accepted / spoof / mismatch), so consume it either way —
                # only genuinely unassigned faces go on to be tailgating.
                f = faces[j]
                f.consumed = True
                sim = face.cosine(t.embedding, f.embedding)
                if sim < self.threshold:
                    outcomes.append(self._mismatch(t))
                elif f.is_live is False and liveness.calibrated():
                    # Only a *calibrated* liveness verdict may reject a genuine card+face
                    # match as spoof. Uncalibrated (LIVENESS_THRESHOLD unset) -> advisory:
                    # accept the match, still log the score for later calibration.
                    outcomes.append(self._spoof(t, f, sim))
                else:
                    outcomes.append(self._present(t, f, sim))
            self._taps = [t for t in self._taps if now - t.ts < self.window]

        # Tailgating: a ripe face with no consumed match and no pending tap that could
        # still claim it (a pending tap within the window defers the verdict).
        for f in self._faces:
            if f.consumed or f.emitted:
                continue
            if now - f.ts >= self.window and not any(
                abs(t.ts - f.ts) <= self.window for t in self._taps
            ):
                f.emitted = True
                if f.track_id in self._tailgated_tracks:
                    # Already flagged this track's presence episode once; this
                    # is a later refresh of the same continuous dwell, not a
                    # new tailgater. Still evicted normally (f.emitted above),
                    # just no repeat outcome.
                    continue
                self._tailgated_tracks[f.track_id] = None
                if len(self._tailgated_tracks) > self.max_tailgated_tracks:
                    self._tailgated_tracks.popitem(last=False)
                outcomes.append(self._tailgating(f))

        # Evict resolved / stale faces; keep live (within-window, unclaimed) ones.
        self._faces = [
            f
            for f in self._faces
            if not f.consumed and not f.emitted and now - f.ts < self.window + 1.0
        ]

        for o in outcomes:
            self._emit(o)
        return outcomes

    def _assign(self, taps, faces):
        """Optimal (Hungarian) tap->face assignment. Only time-valid pairs (within
        the window) are eligible; returns {tap_idx: face_idx}."""
        if not faces:
            return {}
        cost = np.full((len(taps), len(faces)), _BIG, dtype=np.float64)
        for i, t in enumerate(taps):
            for j, f in enumerate(faces):
                if abs(f.ts - t.ts) <= self.window:
                    cost[i, j] = 1.0 - face.cosine(t.embedding, f.embedding)
        rows, cols = linear_sum_assignment(cost)
        return {int(i): int(j) for i, j in zip(rows, cols) if cost[i, j] < _BIG}

    # --- outcome builders ---

    def _base(self, uid, student_id, student, status, method="nfc"):
        return {
            "status": status,
            "uid": uid,
            "student_id": student_id,
            "student": student,
            "method": method,
            "face_score": None,
            "face_match": None,
            "liveness_score": None,
            "liveness_pass": None,
            "track_id": None,
            "reason": None,
        }

    def _present(self, t, f, sim):
        o = self._base(t.uid, t.student_id, t.student, decision.ACCEPTED, method="nfc+face")
        o.update(
            face_score=sim, face_match=True, liveness_score=f.live_score,
            liveness_pass=f.is_live, track_id=f.track_id, reason="verified",
        )
        return o

    def _spoof(self, t, f, sim):
        o = self._base(t.uid, t.student_id, t.student, decision.SPOOF, method="nfc+face")
        o.update(
            face_score=sim, face_match=True, liveness_score=f.live_score,
            liveness_pass=f.is_live, track_id=f.track_id, reason="liveness fail on matched face",
        )
        return o

    def _mismatch(self, t):
        o = self._base(t.uid, t.student_id, t.student, decision.MISMATCH, method="nfc+face")
        o.update(face_match=False, reason="face in window below match threshold")
        return o

    def _no_face(self, t):
        o = self._base(t.uid, t.student_id, t.student, decision.NO_FACE)
        o.update(reason="no face in association window")
        return o

    def _tailgating(self, f):
        ident, sim = None, None
        if self.face_search is not None:
            try:
                res = self.face_search(f.embedding, 1)
                if res:
                    r = res[0]
                    sim = r.get("similarity")
                    if sim is not None and sim >= self.tailgate_threshold:
                        ident = r
            except Exception as e:
                print(f"[matcher] tailgater lookup failed: {e}")
        o = self._base(
            "", (ident or {}).get("student_id"), ident, decision.TAILGATING, method="face"
        )
        o.update(
            face_score=sim, liveness_score=f.live_score, liveness_pass=f.is_live,
            track_id=f.track_id,
            reason=f"tailgating; nearest={ident['student_id'] if ident else 'unknown'}",
        )
        return o

    def _emit(self, outcome):
        if self.outcome_sink is None:
            return
        try:
            self.outcome_sink(outcome)
        except Exception as e:  # an outcome-writer error must not stall the matcher
            print(f"[matcher] outcome sink error: {e}")
