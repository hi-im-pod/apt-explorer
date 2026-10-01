"""data/guesses.json: what the unresolved names probably are, with the evidence and a measured confidence.

The resolver leaves a name unresolved when no source lists it. This module
scores each such name with the signals in resolve/similarity.py, turns the
scores into a label and a confidence through an evaluation on names whose
answer is known, and writes both the guesses and the evaluation.

A guess never changes anything else. Actors, aliases, report links and the
resolution counts come from the resolver alone. A proposed alias is only shown
as "possibly the same as X", next to the evidence for it.

What the evaluation may use is strict.
- Ground truth is the labelled set's `derived` and `confirmed` rows. Derived
  labels come from evidence in the sources. Confirmed labels are set by a
  person. The `pending` rows are an earlier agent's guesses made without a
  scoring system, so they are never used to train, choose signals or calibrate.
- Each ground-truth name is scored as if it were unresolved: its own key is
  left out of the reference (see similarity.analyse), and the model that
  scores it is fitted without it. The numbers therefore measure names no
  source knows.
"""
import csv
import logging
import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from aptx.core.models import ReportRecord, SoftwareRecord
from aptx.resolve import similarity as sim
from aptx.resolve.names import norm
from aptx.resolve.registry import Registry
from aptx.resolve.similarity import LABELS, Analysis, Reference

log = logging.getLogger(__name__)

# The labelled set lives with the tests, next to the resolver checks that share it.
DEFAULT_LABELS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "paper_unresolved_labels.csv"
GROUND_TRUTH = frozenset({"derived", "confirmed"})
PENDING_STATUS = "pending confirmation"
CONFIRMED_STATUS = "confirmed"

# Fewer labelled names than this cannot support a fit, so nothing is published.
MIN_GROUND_TRUTH = 20
# A signal that fires on fewer ground-truth names than this cannot be measured.
MIN_FIRES = 3
# A label with fewer ground-truth names than this cannot be called validated.
MIN_LABEL_SUPPORT = 10
# The strength of the pull toward zero on the model's weights. It is fixed, not
# tuned, because there are too few labelled names to tune anything else on.
L2 = 1.0
# Confidence needed for a band, on the calibrated scale.
BAND_MEDIUM = 0.70
BAND_HIGH = 0.85
# A band is only used when at least this many ground-truth names reached it
# with the precision it claims, measured with each name left out of its own
# calibration. Fewer than that cannot tell a 0.94 from a 0.75.
MIN_BAND_SUPPORT = 20
# A guess refused a band is held this far below the band's threshold, so its
# confidence and its band agree.
CAP_MARGIN = 0.01
BAND_ORDER = ("high", "medium", "low")
# Raw-score bins for calibration. With this few labelled names, three bins is
# as fine as the counts allow.
BIN_EDGES = (0.5, 0.7, 0.85, 1.0001)
# Pseudo-observations pulling a sparse bin's precision toward its raw score.
SMOOTHING = 4
# A kind of match is published as "possibly the same as" when at least this
# share of its proposals on the ground truth were right.
MIN_MATCH_PRECISION = 0.5
NAME_ONLY_SIGNALS = ("cluster_id", "vendor_suffix", "malware_word", "non_latin")
# Signals that only add context to a guess, and are shown even when the model
# gives them no weight.
CONTEXT_SIGNALS = ("actor_resemblance", "software_resemblance", "cooc_actor", "cve_actor", "title_malware_ctx", "title_actor_ctx")


@dataclass(frozen=True)
class Label:
    name: str
    label: str
    status: str
    basis: str


def read_labels(path: Path = DEFAULT_LABELS) -> list[Label]:
    """The labelled set. Raises FileNotFoundError when there is none."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        return [Label(r["name"], r["label"], r["status"], r["prefill_basis"]) for r in csv.DictReader(f)]


# The model: a small logistic regression, written out so the pipeline needs no extra library

def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Solve a x = b by Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            factor = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= factor * m[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-max(min(z, 35.0), -35.0)))


def fit_logistic(rows: Sequence[Sequence[float]], y: Sequence[int], l2: float = L2) -> list[float]:
    """Weights, the intercept first, of an L2-penalised logistic regression fitted by Newton's method.

    The intercept is not penalised, so a signal-free name gets the ground
    truth's own base rate. The penalty also keeps the weights finite for a
    signal that has only ever fired on one label.
    """
    n, k = len(rows), (len(rows[0]) if rows else 0) + 1
    x = [[1.0, *r] for r in rows]
    w = [0.0] * k
    for _ in range(50):
        p = [_sigmoid(sum(wi * xi for wi, xi in zip(w, row))) for row in x]
        grad = [sum((p[i] - y[i]) * x[i][j] for i in range(n)) + (l2 * w[j] if j else 0.0) for j in range(k)]
        hess = [[sum(p[i] * (1 - p[i]) * x[i][j] * x[i][c] for i in range(n)) + (l2 if j == c and j else 0.0)
                 for c in range(k)] for j in range(k)]
        step = _solve(hess, grad)
        w = [wi - si for wi, si in zip(w, step)]
        if max(abs(s) for s in step) < 1e-9:
            break
    return w


def predict_logistic(w: Sequence[float], features: Sequence[float]) -> float:
    return _sigmoid(w[0] + sum(wi * xi for wi, xi in zip(w[1:], features)))


def _vector(features: Mapping[str, float], signals: Sequence[str]) -> list[float]:
    return [features[s] for s in signals]


def cross_validated(samples: Sequence["Sample"], signals: Sequence[str]) -> list[float]:
    """Each actor or malware sample's probability of being malware, from a model fitted without it."""
    idx = [i for i, s in enumerate(samples) if s.label in ("actor", "malware")]
    out: dict[int, float] = {}
    for held in idx:
        rest = [i for i in idx if i != held]
        w = fit_logistic([_vector(samples[i].analysis.features, signals) for i in rest],
                         [1 if samples[i].label == "malware" else 0 for i in rest])
        out[held] = predict_logistic(w, _vector(samples[held].analysis.features, signals))
    return [out.get(i, 0.0) for i in range(len(samples))]


def _log_loss(samples: Sequence["Sample"], probs: Sequence[float]) -> float:
    total, n = 0.0, 0
    for s, p in zip(samples, probs):
        if s.label not in ("actor", "malware"):
            continue
        p = min(max(p, 1e-6), 1 - 1e-6)
        total -= math.log(p if s.label == "malware" else 1 - p)
        n += 1
    return total / n if n else 0.0


@dataclass
class Sample:
    """A ground-truth name scored as if unresolved."""
    name: str
    label: str
    status: str
    analysis: Analysis
    truth_actor: str | None
    matchable: bool


def _derivable(row: Label, key: str, truth_actor: str | None, ref: Reference) -> bool:
    if row.label == "actor":
        return truth_actor is not None
    if row.label in ("malware", "tool"):
        return any(e.kind == row.label for e in ref.software_with_key(key))
    return False


def _samples(labels: Iterable[Label], ref: Reference, truth: Callable[[str], str | None]) -> list[Sample]:
    out: list[Sample] = []
    for row in labels:
        if row.status not in GROUND_TRUTH or row.label not in LABELS or not norm(row.name):
            continue
        key = norm(row.name)
        truth_actor = truth(row.name) if row.label == "actor" else None
        if row.status == "derived" and not _derivable(row, key, truth_actor, ref):
            # A derived label was read from the sources. When these sources do not
            # say it, as in a build from a small sample, the row is not ground truth here.
            continue
        analysis = sim.analyse(row.name, ref, exclude_key=key)
        out.append(Sample(row.name, row.label, row.status, analysis, truth_actor,
                          bool(truth_actor) and truth_actor in ref.known_actor_ids(exclude_key=key)))
    return out


# Deciding a label

def decide(analysis: Analysis, p_malware: float) -> tuple[str, float | None, str | None]:
    """The label, its raw score, and the rule that forced it when one did.

    A rule label has no raw score, because no measurement stands behind it.
    """
    if sim.is_placeholder(analysis.name):
        return "not-an-entity", None, "placeholder_word"
    if sim.is_campaign_name(analysis.name):
        return "not-an-entity", None, "campaign_word"
    if analysis.exact_actor and not analysis.exact_software:
        # A source lists the name as an actor alias, and the resolver left it unresolved only because
        # the alias is shared by two actors. The evaluation cannot measure this signal, because every
        # ground-truth name is known to a source, so the label is a rule and is never validated.
        return "actor", None, "exact_actor_name"
    label = "malware" if p_malware >= 0.5 else "actor"
    raw = max(p_malware, 1 - p_malware)
    hit = analysis.software_hit
    if label == "malware" and hit is not None and hit.target == "tool":
        # The software the name resembles is a tool, not malware. The ground
        # truth has no tool, so this label is never validated.
        label = "tool"
    return label, raw, None


@dataclass
class Model:
    signals: tuple[str, ...]
    weights: list[float]
    # (upper edge of the raw-score bin, calibrated confidence), plus the
    # confidence of a name on which no kept signal fired.
    bins: list[tuple[float, float]]
    no_signal_confidence: float
    validated_labels: frozenset[str]
    # The bands the held-out evaluation supports. A guess whose calibrated
    # confidence falls in a band outside this set drops to the next one down.
    granted: frozenset[str] = frozenset(BAND_ORDER)

    def p_malware(self, features: Mapping[str, float]) -> float:
        return predict_logistic(self.weights, _vector(features, self.signals))

    def fired(self, features: Mapping[str, float]) -> list[str]:
        return [s for s in self.signals if features.get(s)]

    def calibrated(self, raw: float, fired: bool) -> float:
        return _lookup(self.bins, self.no_signal_confidence, raw, fired)

    def cap(self, value: float, fired: bool) -> float:
        """The confidence, held below the threshold of the band the evaluation refused it."""
        band = self.settled_band(value, fired)
        return min(value, CAPS[band])

    def settled_band(self, value: float, fired: bool) -> str:
        band = band_for(value, fired)
        while band not in self.granted:
            band = BAND_ORDER[BAND_ORDER.index(band) + 1]
        return band

    def confidence(self, raw: float, fired: bool) -> float:
        return self.cap(self.calibrated(raw, fired), fired)


CAPS = {"high": 1.0, "medium": BAND_HIGH - CAP_MARGIN, "low": BAND_MEDIUM - CAP_MARGIN}


def _lookup(bins: Sequence[tuple[float, float]], no_signal: float, raw: float, fired: bool) -> float:
    if not fired:
        return no_signal
    for upper, value in bins:
        if raw < upper:
            return value
    return bins[-1][1]


def band_for(confidence: float, fired: bool) -> str:
    """"high", "medium" or "low". A name on which no signal fired is low whatever its confidence."""
    if not fired:
        return "low"
    return "high" if confidence >= BAND_HIGH else "medium" if confidence >= BAND_MEDIUM else "low"


def _smoothed(correct: int, n: int, prior: float) -> float:
    return (correct + SMOOTHING * prior) / (n + SMOOTHING)


def _calibrate(rows: list[tuple[float, bool, bool]]) -> tuple[list[tuple[float, float]], float]:
    """Calibration from cross-validated predictions.

    `rows` is (raw score, whether the prediction was right, whether a kept
    signal fired) for each ground-truth name. Names with no kept signal are
    calibrated on their own, because their raw score is only the base rate.
    The bins are then made non-decreasing, since a higher raw score must never
    earn a lower confidence.
    """
    silent = [ok for _, ok, fired in rows if not fired]
    no_signal = _smoothed(sum(silent), len(silent), 0.5) if silent else 0.5
    values: list[float] = []
    lower = BIN_EDGES[0]
    for upper in BIN_EDGES[1:]:
        in_bin = [ok for raw, ok, fired in rows if fired and lower <= raw < upper]
        mid = (lower + min(upper, 1.0)) / 2
        values.append(_smoothed(sum(in_bin), len(in_bin), mid))
        lower = upper
    for i in range(1, len(values)):
        values[i] = max(values[i], values[i - 1])
    return list(zip(BIN_EDGES[1:], (round(v, 3) for v in values))), round(no_signal, 3)


def held_out_confidences(rows: list[tuple[float, bool, bool]]) -> list[float]:
    """Each row's calibrated confidence, from bins that were made without that row.

    Calibrating on a name and then scoring the calibration on the same name
    flatters it, most of all in a sparse bin, where one name is a large share.
    """
    out = []
    for i, (raw, _, fired) in enumerate(rows):
        bins, no_signal = _calibrate(rows[:i] + rows[i + 1:])
        out.append(_lookup(bins, no_signal, raw, fired))
    return out


def band_pools(rows: list[tuple[float, bool, bool]]) -> list[tuple[str, int, int, bool]]:
    """For the high and medium bands: (band, names, right, granted).

    `rows` is (held-out confidence, whether the guess was right, whether a kept
    signal fired). Names refused the high band are counted in the medium band's
    pool, because that is where they would be shown. A band is granted when its
    pool is large enough and at least as precise as the band claims.
    """
    carried: list[bool] = []
    out = []
    for band, floor in (("high", BAND_HIGH), ("medium", BAND_MEDIUM)):
        pool = [ok for conf, ok, fired in rows if band_for(conf, fired) == band] + carried
        granted = len(pool) >= MIN_BAND_SUPPORT and sum(pool) / len(pool) >= floor
        out.append((band, len(pool), sum(pool), granted))
        carried = [] if granted else pool
    return out


def granted_bands(rows: list[tuple[float, bool, bool]]) -> frozenset[str]:
    return frozenset({"low"} | {band for band, _, _, ok in band_pools(rows) if ok})


# The evaluation

def _rate(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def fit(labels: Sequence[Label], ref: Reference, truth: Callable[[str], str | None]) -> tuple[Model, dict] | None:
    """Choose signals, fit and calibrate the model, and measure it. None when the ground truth is too small."""
    samples = _samples(labels, ref, truth)
    binary = [s for s in samples if s.label in ("actor", "malware")]
    if len(samples) < MIN_GROUND_TRUTH or len({s.label for s in binary}) < 2:
        return None

    fires = {sig: [s for s in binary if s.analysis.features[sig]] for sig in sim.SIGNALS}
    candidates = tuple(sig for sig in sim.SIGNALS if len(fires[sig]) >= MIN_FIRES)

    # Every candidate is removed in turn. A signal stays only if the model does
    # worse without it, judged by cross-validated log loss.
    with_all = _log_loss(binary, [p for p, s in zip(cross_validated(samples, candidates), samples) if s in binary])
    change: dict[str, float] = {}
    for sig in candidates:
        rest = tuple(c for c in candidates if c != sig)
        probs = cross_validated(samples, rest)
        change[sig] = _log_loss(binary, [p for p, s in zip(probs, samples) if s in binary]) - with_all
    kept = tuple(sig for sig in candidates if change[sig] > 0)

    probs = cross_validated(samples, kept)
    weights = fit_logistic([_vector(s.analysis.features, kept) for s in binary],
                           [1 if s.label == "malware" else 0 for s in binary])

    support = Counter(s.label for s in samples)
    validated = frozenset(label for label in LABELS if support[label] >= MIN_LABEL_SUPPORT)

    def cv_decision(s: Sample, p: float) -> tuple[str, float | None, bool]:
        label, raw, _ = decide(s.analysis, p)
        return label, raw, any(s.analysis.features[k] for k in kept)

    calib_rows = []
    calib_index = []
    for i, (s, p) in enumerate(zip(samples, probs)):
        if s.label in ("actor", "malware"):
            label, raw, fired = cv_decision(s, p)
            if raw is not None:
                calib_rows.append((raw, label == s.label, fired))
                calib_index.append(i)
    bins, no_signal = _calibrate(calib_rows)
    # The bands are judged on names that were calibrated without themselves, so
    # a band the data cannot support is refused before any guess is shown in it.
    held = held_out_confidences(calib_rows)
    held_rows = [(conf, ok, fired) for conf, (_, ok, fired) in zip(held, calib_rows)]
    pools = band_pools(held_rows)
    model = Model(kept, weights, bins, no_signal, validated, granted=granted_bands(held_rows))
    held_conf = dict(zip(calib_index, held))

    predictions = []
    for i, (s, p) in enumerate(zip(samples, probs)):
        label, raw, fired = cv_decision(s, p)
        if raw is None:
            conf = None
        elif i in held_conf:
            conf = model.cap(held_conf[i], fired)
        else:
            conf = model.confidence(raw, fired)
        band = band_for(conf, fired) if label in validated and conf is not None else "unvalidated"
        predictions.append((s, label, conf, band))

    evaluation = _report(samples, predictions, candidates, kept, fires, change, model, validated, pools)
    return model, evaluation


def _report(samples, predictions, candidates, kept, fires, change, model, validated, pools) -> dict:
    n = len(samples)
    correct = sum(1 for s, label, _, _ in predictions if label == s.label)
    truth_counts = Counter(s.label for s in samples)
    majority = max(LABELS, key=lambda label: (truth_counts[label], -LABELS.index(label)))

    name_only = tuple(sig for sig in NAME_ONLY_SIGNALS if sig in kept or len(fires[sig]) >= MIN_FIRES)
    name_only_probs = cross_validated(samples, name_only)
    name_only_correct = sum(1 for s, p in zip(samples, name_only_probs) if decide(s.analysis, p)[0] == s.label)

    confusion = [[0] * len(LABELS) for _ in LABELS]
    for s, label, _, _ in predictions:
        confusion[LABELS.index(s.label)][LABELS.index(label)] += 1
    per_label = []
    for i, label in enumerate(LABELS):
        predicted = sum(row[i] for row in confusion)
        per_label.append({"label": label, "support": truth_counts[label], "predicted": predicted,
                          "precision": _rate(confusion[i][i], predicted), "recall": _rate(confusion[i][i], truth_counts[label]),
                          "validated": label in validated})

    bands = []
    for band, low_edge in (("high", BAND_HIGH), ("medium", BAND_MEDIUM), ("low", 0.0)):
        rows = [(s, label) for s, label, _, b in predictions if b == band]
        ok = sum(1 for s, label in rows if label == s.label)
        bands.append({"band": band, "min_confidence": low_edge, "n": len(rows), "correct": ok,
                      "precision": _rate(ok, len(rows)), "coverage": _rate(len(rows), n)})

    signals = []
    for sig, text in sim.SIGNALS.items():
        rows = fires[sig]
        counts = Counter(s.label for s in rows)
        top = max(counts, key=lambda k: (counts[k], k)) if counts else None
        if sig in kept:
            note = "Kept: the model does worse without it."
        elif sig in candidates:
            note = "Dropped: removing it did not make the model worse."
        else:
            note = f"Dropped: it fires on fewer than {MIN_FIRES} ground-truth names, too few to measure."
        signals.append({
            "signal": sig, "description": text, "fires": len(rows), "implied_label": top,
            "precision_when_fires": _rate(counts[top], len(rows)) if top else None,
            "weight": round(model.weights[1 + kept.index(sig)], 3) if sig in kept else None,
            "loss_change_without": round(change[sig], 4) if sig in change else None,
            "kept": sig in kept, "note": note})

    by_kind = []
    actors = [(s, l) for s, l, _, _ in predictions if s.label == "actor"]
    for kind in ("variant", "contains", "fuzzy"):
        proposed = [(s, l) for s, l in actors if l == "actor" and s.analysis.actor_hit and s.analysis.actor_hit.kind == kind]
        right = [s for s, _ in proposed if s.matchable and s.analysis.actor_hit.target == s.truth_actor]
        by_kind.append({"kind": kind, "proposed": len(proposed), "correct": len(right),
                        "precision": _rate(len(right), len(proposed)),
                        "published": bool(proposed) and len(right) / len(proposed) >= MIN_MATCH_PRECISION})

    limits = []
    if not validated >= set(LABELS):
        missing = [label for label in LABELS if label not in validated]
        limits.append("The ground truth has fewer than %d names labelled %s, so guesses with those labels are shown as unvalidated."
                      % (MIN_LABEL_SUPPORT, " or ".join(missing)))
    limits.append("The ground-truth names are ones that a source lists, so they are better known than a typical unresolved name.")
    limits.append("Signals were chosen on the same %d names that score them, so the figures are likely a little optimistic. "
                  "Confidence is calibrated without each name in turn, which removes a second source of the same bias." % n)
    for band, pooled, right, granted in pools:
        if not granted:
            limits.append("No guess is shown as %s confidence. The band needs at least %d held-out names with %d%% or more right, "
                          "and %d qualified, of which %d were right."
                          % (band, MIN_BAND_SUPPORT, round((BAND_HIGH if band == "high" else BAND_MEDIUM) * 100), pooled, right))

    return {
        "ground_truth": {"n": n, "derived": sum(1 for s in samples if s.status == "derived"),
                         "confirmed": sum(1 for s in samples if s.status == "confirmed"),
                         "by_label": [{"label": label, "count": truth_counts[label]} for label in LABELS]},
        "accuracy": _rate(correct, n), "correct": correct,
        "baselines": {"majority_label": majority, "majority_accuracy": _rate(truth_counts[majority], n),
                      "name_only_accuracy": _rate(name_only_correct, n)},
        "per_label": per_label,
        "confusion": {"labels": list(LABELS), "rows": confusion},
        "bands": bands,
        "signals": signals,
        "unmeasured_signals": [{
            "signal": "exact_name_listed",
            "reason": "Every ground-truth name is labelled because a source lists it, so leaving that source out removes the signal, "
                      "and keeping it would make the test circular. A guess that rests on it is shown as unvalidated."}],
        "matching": {"actor_names": len(actors), "matchable": sum(1 for s, _ in actors if s.matchable), "by_kind": by_kind},
        "limitations": limits,
    }


# The guesses

def _weighted(model: Model, analysis: Analysis, label: str, p_malware: float) -> list[dict]:
    """Evidence for a guess: each kept signal that fired, then context.

    The weight is how far the signal pushes toward the guessed label, so a positive weight supports the
    guess and a negative weight argues against it. The model's own weights point toward malware, so
    for an actor guess the sign is flipped. The model only weighs actor against malware, so a guess with
    any other label carries no weight: a number that means "toward malware" would mislead there.
    """
    sign = 1 if label == "malware" else -1
    out: list[dict] = []
    for sig in model.fired(analysis.features):
        weight = model.weights[1 + model.signals.index(sig)] * analysis.features[sig]
        shown = round(sign * weight, 3) if label in ("actor", "malware") else None
        out.append({"signal": sig, "detail": analysis.evidence[sig].detail, "weight": shown})
    for sig in CONTEXT_SIGNALS:
        if sig in analysis.evidence and sig not in model.signals:
            out.append({"signal": sig, "detail": analysis.evidence[sig].detail, "weight": None})
    return out


def _guess(name: str, count: int, analysis: Analysis, model: Model, ref: Reference, published: set[str],
           by_kind: Mapping[str, bool], truth_counts: Mapping[str, int], total: int) -> dict:
    p = model.p_malware(analysis.features)
    label, raw, rule = decide(analysis, p)
    fired = bool(model.fired(analysis.features))
    evidence = _weighted(model, analysis, label, p)
    exact = sim.exact_presence(name, ref)
    if rule:
        detail = next((e.detail for e in exact if e.signal == rule), sim.RULES[rule])
        evidence.insert(0, {"signal": rule, "detail": detail, "weight": None})
    if not rule and not fired:
        base = max(("actor", "malware"), key=lambda k: truth_counts.get(k, 0))
        evidence.insert(0, {"signal": "base_rate", "weight": None, "detail": (
            f"No measured signal fired, so this is only the most common label in the ground truth "
            f"({base}, {truth_counts.get(base, 0)} of {total} names).")})
    for item in exact:
        if item.signal == rule:
            continue
        evidence.append({"signal": item.signal, "detail": item.detail, "weight": None})

    validated = label in model.validated_labels and raw is not None
    confidence = model.confidence(raw, fired) if validated else None
    band = band_for(confidence, fired) if validated else "unvalidated"

    hit = analysis.actor_hit
    matched = None
    if label == "actor" and hit is not None and by_kind.get(hit.kind) and hit.target in published:
        matched = hit.target
    return {"name": name, "count": count, "label": label,
            "confidence": None if confidence is None else round(confidence, 2), "band": band,
            "matched_actor_id": matched, "matched_actor_name": ref.actor_display.get(matched) if matched else None,
            "evidence": evidence, "status": PENDING_STATUS}


def _merge_unresolved(rows: Iterable[Mapping]) -> list[tuple[str, int]]:
    """One row per name key, with the counts added and the most used spelling kept.

    Sources spell one name "Iron Group" and "iron group", and the resolver
    lists both. A reader should see one guess for it.
    """
    merged: dict[str, list] = {}
    for row in rows:
        key = norm(row["name"])
        if not key:
            continue
        entry = merged.setdefault(key, [0, []])
        entry[0] += row["count"]
        entry[1].append((row["count"], row["name"]))
    return sorted(((max(e[1], key=lambda t: (t[0], t[1]))[1], e[0]) for e in merged.values()),
                  key=lambda t: (-t[1], t[0].casefold()))


@dataclass
class Prepared:
    """The reference, the fitted model and its evaluation: everything a guess needs."""
    ref: Reference
    model: Model
    evaluation: dict
    published: set[str]
    by_kind: dict[str, bool]
    truth_counts: dict[str, int]
    total: int


def make_reference(registry: Registry, software: Iterable[SoftwareRecord], paper_reports: Iterable[ReportRecord],
                   published_actors: Mapping[str, str], shown_sources: Iterable[str] | None = None) -> Reference:
    """The reference scored against: published actors only, from the sources a page may show."""
    return sim.only_actors(sim.build_reference(registry, list(software), list(paper_reports), shown_sources),
                           published_actors)


def prepare(ref: Reference, labels: Sequence[Label] | None, truth: Callable[[str], str | None],
            published_actors: Mapping[str, str]) -> Prepared | None:
    """Fit and evaluate on `ref`. None without enough ground truth, because a guess with no measurement behind it has nothing to say."""
    fitted = fit(labels or [], ref, truth) if labels else None
    if fitted is None:
        return None
    model, evaluation = fitted
    return Prepared(ref, model, evaluation, set(published_actors),
                    {row["kind"]: row["published"] for row in evaluation["matching"]["by_kind"]},
                    {row["label"]: row["count"] for row in evaluation["ground_truth"]["by_label"]},
                    evaluation["ground_truth"]["n"])


def guess_name(name: str, count: int, prepared: Prepared) -> dict:
    """The guess for one name, scored against the prepared reference."""
    return _guess(name, count, sim.analyse(name, prepared.ref), prepared.model, prepared.ref, prepared.published,
                  prepared.by_kind, prepared.truth_counts, prepared.total)


def build_guesses(registry: Registry, software: Iterable[SoftwareRecord], paper_reports: Iterable[ReportRecord],
                  unresolved: Iterable[Mapping], labels: Sequence[Label] | None, published_actors: Mapping[str, str],
                  shown_sources: Iterable[str] | None = None, prepared: Prepared | None = None) -> dict:
    """The contents of guesses.json.

    `unresolved` is resolution.json's unresolved_names. `labels` is the labelled
    set, or None when there is none. Without enough ground truth the file
    carries no evaluation and no guesses, because a guess with no measurement
    behind it would have nothing to say for itself. `prepared` is a fit made
    earlier on a reference that carries title statistics; without it one is made here.
    """
    if prepared is None:
        ref = make_reference(registry, software, paper_reports, published_actors, shown_sources)
        prepared = prepare(ref, labels, registry.lookup, published_actors)
    if prepared is None:
        return {"evaluation": None, "guesses": []}

    status = {norm(label.name): label for label in labels or []}
    typed = {norm(r["name"]) for r in unresolved if r.get("typed_as")}
    guesses = []
    for name, count in _merge_unresolved(r for r in unresolved if not r.get("typed_as")):
        key = norm(name)
        row = status.get(key)
        if key in typed or (row and row.status == "derived"):
            continue
        if row and row.status == "confirmed":
            guesses.append({"name": name, "count": count, "label": row.label, "confidence": None, "band": "confirmed",
                            "matched_actor_id": None, "matched_actor_name": None, "evidence": [], "status": CONFIRMED_STATUS})
            continue
        guesses.append(guess_name(name, count, prepared))
    return {"evaluation": prepared.evaluation, "guesses": guesses}


# The evaluation entry point

def compare_pending(payload: Mapping, labels: Iterable[Label]) -> dict:
    """How the guesses compare with the earlier hand-made guesses, which are not ground truth.

    The pending rows were written before any scoring system existed. They are
    compared here, and never scored against, so that a person confirming them
    can see where the two disagree.
    """
    ours = {norm(g["name"]): g for g in payload["guesses"]}
    rows = [r for r in labels if r.status == "pending" and norm(r.name) in ours]
    agree = [r for r in rows if ours[norm(r.name)]["label"] == r.label]
    return {"compared": len(rows), "agree": len(agree),
            "rate": _rate(len(agree), len(rows)),
            "disagreements": [{"name": r.name, "pending": r.label, "guess": ours[norm(r.name)]["label"],
                               "confidence": ours[norm(r.name)]["confidence"], "band": ours[norm(r.name)]["band"]}
                              for r in rows if r not in agree]}


def main(argv: Sequence[str] | None = None) -> int:
    """`python -m aptx.build.guesses --evaluate` builds from the stored snapshots and prints the evaluation."""
    import argparse
    import json
    import sys
    import tempfile

    from aptx import cli
    from aptx.core.snapshot import SnapshotStore

    parser = argparse.ArgumentParser(prog="aptx.build.guesses", description="Evaluate the name guesses.")
    parser.add_argument("--evaluate", action="store_true", required=True, help="print the evaluation and the comparison")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--json", type=Path, help="also write the whole guesses.json here")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        cli.run(Path(tmp), SnapshotStore(), fetch=False, labels=args.labels)
        payload = json.loads((Path(tmp) / "guesses.json").read_text(encoding="utf-8"))
    if args.json:
        args.json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    ev = payload["evaluation"]
    if ev is None:
        print("no evaluation: too few labelled names", file=sys.stderr)
        return 1
    print(f"scored {ev['ground_truth']['n']} names: accuracy {ev['accuracy']}, "
          f"majority baseline {ev['baselines']['majority_accuracy']}, name-only {ev['baselines']['name_only_accuracy']}")
    for row in ev["per_label"]:
        print(f"  {row['label']:<14} support {row['support']:>3} precision {row['precision']} recall {row['recall']}")
    for row in ev["bands"]:
        print(f"  band {row['band']:<7} n {row['n']:>3} precision {row['precision']}")
    for row in ev["signals"]:
        print(f"  signal {row['signal']:<21} fires {row['fires']:>3} weight {row['weight']} {row['note']}")
    pending = compare_pending(payload, read_labels(args.labels))
    print(f"vs the {pending['compared']} pending hand guesses: {pending['agree']} agree ({pending['rate']})")
    for row in pending["disagreements"]:
        print(f"  {row['name']}: pending {row['pending']}, now {row['guess']} ({row['band']}, {row['confidence']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
