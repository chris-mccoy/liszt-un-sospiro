#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
perform.py -- render the braille-decoded Un sospiro (brf.py) as an expressive piano MIDI file.

The notes come from the score; everything else here -- tempo, rubato, dynamics, voicing,
articulation, pedalling -- is an interpretation layered over them.
"""
import argparse, bisect, math, random, struct, sys
from fractions import Fraction as F

sys.path.insert(0, __import__('os').path.dirname(__file__))
import brf
from brf import build

PPQ = 480
TPU = PPQ // 4                    # ticks per unit: the tempo grid is the 16th note
UNIT = F(1, 16)

DYN = {'ppp': 28, 'pp': 37, 'p': 47, 'mp': 57, 'mf': 67, 'f': 78, 'ff': 90, 'fff': 102}

# ---------------------------------------------------------------- flattening

def flatten(measures, order):
    """Notes and markers on one score time line, in 16ths from the start."""
    notes, marks, bars, held = [], [], [], []
    base = F(0)
    for k, mi in enumerate(order):
        m = measures[mi]
        length = m.get('len', brf.MEASURE) / UNIT
        bars.append({'k': k, 'num': m['num'], 'start': base, 'len': length, 'key': m['key'],
                     'text': m['text']})
        for h, evs in m['lines'].items():
            byvoice = {}
            for e in evs:
                byvoice.setdefault(e['voice'], []).append(e)
            for e in evs:
                t = base + e['t'] / UNIT
                for mk in e.get('markers', []):
                    marks.append((t, h, mk))
                if e['kind'] == 'rest' and e.get('fermata'):
                    held.append((t, e['dur'] / UNIT))          # a fermata over a rest
                if e['kind'] != 'chord' or e.get('alt_pair'):
                    continue
                dur = e.get('dur', F(0)) / UNIT
                if e.get('stem'):
                    dur = max(dur, e['stem'] / UNIT)
                chord = list(zip(e['pitches'], [n['small'] for n in e['notes']]))
                info = {'t': t, 'dur': dur, 'hand': e['hand'], 'line': h, 'k': k, 'pos': e['t'] / UNIT,
                        'artic': set(e.get('artic', [])), 'slur': e.get('slur'), 'tie': e.get('tie'),
                        'grace': e['grace'], 'fermata': e.get('fermata', False),
                        'arp': ('arpeggio',) in e.get('markers', []), 'stemmed': bool(e.get('stem')),
                        'value': e.get('dur', F(0)), 'cadenza': length != brf.MEASURE / UNIT}
                if e.get('alternate'):
                    # a fingered tremolo: alternate this chord with its partner
                    vs = byvoice[e['voice']]
                    partner = vs[vs.index(e) + 1]
                    step = e['alternate'] / UNIT
                    a = chord
                    b = list(zip(partner['pitches'], [n['small'] for n in partner['notes']]))
                    n = int(e['dur'] / UNIT / step)
                    for j in range(n):
                        add_chord(notes, b if j % 2 else a, dict(info, t=t + j * step, dur=step, slur='note'))
                    continue
                add_chord(notes, chord, info)
        base += length
    merge_ties(notes)
    return notes, sorted(marks, key=lambda x: x[0]), bars, held

def add_chord(notes, chord, info):
    ps = sorted(p for p, _ in chord)
    cid = len(notes)
    for p, small in chord:
        role = 'single'
        if len(ps) > 1:
            if info['line'] == 'R':
                role = 'top' if p == ps[-1] else 'inner'
            else:
                role = 'bass' if p == ps[0] else 'inner'
        notes.append(dict(info, pitch=p, small=small, role=role, chord=cid, size=len(ps)))

def merge_ties(notes):
    notes.sort(key=lambda n: (n['t'], n['pitch']))
    starts = {}
    for i, n in enumerate(notes):
        starts.setdefault((n['t'], n['pitch']), []).append(i)
    dead = set()
    for i, n in enumerate(notes):
        if i in dead or not n['tie'] or n['grace']:
            continue
        cur = n
        while cur['tie']:
            nxt = [j for j in starts.get((cur['t'] + cur['dur'], cur['pitch']), []) if j not in dead and j != i]
            if not nxt:
                break
            j = nxt[0]
            dead.add(j)
            n['dur'] += notes[j]['dur']
            n['fermata'] = n['fermata'] or notes[j]['fermata']
            cur = notes[j]
            n['tie'] = cur['tie'] if cur is not n else None
            if not cur['tie']:
                n['tie'] = None
    notes[:] = [n for i, n in enumerate(notes) if i not in dead]

# ---------------------------------------------------------------- the interpretation

# words that change the tempo: a new section factor, or a ramp ('rit', 'accel') to one
TEMPO_WORDS = [
    ('poco a poco rallentando', 'ramp', 1.75, 32), ('un poco piu mosso', 'set', 0.86, 0),
    ('dimin. e rallent', 'ramp', 1.4, 0), ('piu lento', 'set', 1.6, 0), ('in tempo', 'set', 1.0, 0),
    ('affrettando', 'ramp', 0.82, 32), ('acceler', 'ramp', 0.72, 0), ('velocissimo', 'set', 0.32, 0),
    ('presto', 'set', 0.42, 0), ('smorz', 'ramp', 1.3, 4), ('rit', 'ramp', 1.5, 0),
    ('leggierissimo', 'set', 0.9, 0), ('agitato con passionato', 'set', 0.88, 0),
    ('impetuoso', 'set', 0.95, 0), ('languendo', 'dip', 1.25, 4), ('sotto voce', 'set', 1.03, 0),
    ('armonioso', 'set', 1.0, 0), ('appassionato', 'set', 0.97, 0),
]
# the phrases, by bar: the rubato breathes with them, pressing on through the middle of each and
# giving at its close
PHRASES = [(1, 2), (3, 5), (6, 8), (9, 12), (13, 15), (16, 18), (19, 21), (22, 24), (25, 26), (27, 29),
           (30, 31), (32, 33), (34, 35), (36, 37), (38, 39), (40, 41), (42, 43), (44, 45), (46, 49),
           (50, 51), (52, 52), (53, 55), (56, 58), (59, 61), (62, 63), (64, 65), (66, 67), (68, 69),
           (70, 70), (71, 73), (74, 76)]
TEXTURES = ['legatiss', 'dolce', 'cantando', 'grazioso', 'leggierissimo', 'velocissimo', 'impetuoso',
            'agitato', 'con forza', 'marcato', 'sotto voce', 'languendo', 'armonioso', 'non legato',
            'quasi arpa', 'appassionato']

class Plan:
    """Tempo and dynamics as functions of score time (16ths)."""
    def __init__(self, notes, marks, bars, held, args):
        self.notes, self.marks, self.bars, self.held, self.args = notes, marks, bars, held, args
        self.total = int(sum(b['len'] for b in bars))
        self.words = [(t, mk[1]) for t, h, mk in marks if mk[0] == 'word']
        self.bar_starts = [b['start'] for b in bars]
        self.build_dynamics()
        self.build_tempo()

    def bar_at(self, t):
        return self.bars[bisect.bisect_right(self.bar_starts, t) - 1]

    # --- dynamics: a level (velocity) curve from the printed marks
    def build_dynamics(self):
        pts = [(F(0), DYN['p'], 'set')]
        self.texture = []
        for t, w in self.words:
            for tex in TEXTURES:
                if tex in w:
                    self.texture.append((t, tex))
            for part in w.replace('.', ' ').split():
                if part in DYN:
                    pts.append((t, DYN[part], 'set'))
                elif part in ('cresc', 'cr'):
                    pts.append((t, None, 'cresc'))
                elif part in ('dimin', 'dim', 'smorz'):
                    pts.append((t, None, 'dim'))
            if 'con forza' in w:
                pts.append((t, None, 'cresc'))
            if 'sotto voce' in w:
                pts.append((t, DYN['p'] - 4, 'set'))
            if 'armonioso' in w and t > 0:
                pts.append((t, DYN['p'], 'set'))
        # where the print leaves the level open: the coda sings out at mp after the cadenza
        coda = next(b['start'] for b in self.bars if b['num'] == 62)
        pts.append((coda, DYN['mp'], 'set'))
        lento = next(b['start'] for b in self.bars if b['num'] == 70)
        pts.append((lento, DYN['p'], 'set'))
        pts.sort(key=lambda x: x[0])
        # resolve: a cresc/dim ramps to the next printed level when that lies its way within four
        # bars, else by about two steps over at most three bars; a printed level always wins
        sets = [(t, lv) for t, lv, k in pts if k == 'set']
        curve = []                       # (t, level, ramps to the next point)
        cur = DYN['p']
        for t, lv, kind in pts:
            if kind == 'set':
                curve.append((t, lv, False)); cur = lv
                continue
            sign = 1 if kind == 'cresc' else -1
            nxt = next(((t2, l2) for t2, l2 in sets if t2 > t), None)
            end, tgt = t + 48, cur + sign * 18
            if nxt is not None:
                if nxt[0] - t <= 64 and (nxt[1] - cur) * sign > 0:
                    end, tgt = nxt[0] - F(1, 2), nxt[1]
                elif nxt[0] < end:
                    end = nxt[0] - F(1, 2)
                    tgt = cur + sign * 18 * float((end - t) / 48)
            tgt = max(DYN['ppp'], min(DYN['fff'], tgt))
            curve.append((t, cur, True))
            curve.append((end, tgt, False))
            cur = tgt
        curve.sort(key=lambda x: (x[0], not x[2]))
        self.dyn_t = [c[0] for c in curve]
        self.dyn_v = [c[1] for c in curve]
        self.dyn_r = [c[2] for c in curve]
        # hairpins: swells added on top, relaxing afterwards
        self.pins = []
        open_pin = {}
        for t, h, mk in self.marks:
            if mk[0] != 'hairpin':
                continue
            if mk[1] in ('cresc', 'dim'):
                open_pin[h] = (t, mk[1])
            elif h in open_pin:
                t0, kind = open_pin.pop(h)
                if t > t0:
                    self.pins.append((t0, t, 9 if kind == 'cresc' else -9))
        tx = sorted(self.texture)
        self.tex_t = [t for t, _ in tx]
        self.tex_v = [v for _, v in tx]

    def level(self, t):
        i = bisect.bisect_right(self.dyn_t, t) - 1
        if i < 0:
            return DYN['p']
        if self.dyn_r[i] and i + 1 < len(self.dyn_t) and self.dyn_t[i + 1] > self.dyn_t[i]:
            t0, t1 = self.dyn_t[i], self.dyn_t[i + 1]
            return self.dyn_v[i] + (self.dyn_v[i + 1] - self.dyn_v[i]) * float((t - t0) / (t1 - t0))
        return self.dyn_v[i]

    def pin(self, t):
        off = 0.0
        for t0, t1, amt in self.pins:
            if t0 <= t <= t1:
                off += amt * math.sin(math.pi / 2 * float((t - t0) / (t1 - t0)))
            elif t1 < t <= t1 + 8:
                off += amt * (1 - float((t - t1) / 8))
        return off

    def texture_at(self, t):
        i = bisect.bisect_right(self.tex_t, t) - 1
        return self.tex_v[i] if i >= 0 else 'legatiss'

    # --- tempo: seconds for each 16th of the performance
    def build_tempo(self):
        a = self.args
        base = 60.0 / a.tempo / 4            # seconds per 16th at the quarter-note tempo
        n = self.total
        sect = [1.0] * n                     # the section factor (>1 slower), with its ramps
        events = []
        for t, w in sorted(self.words):
            for word, kind, val, span in TEMPO_WORDS:
                if word in w:
                    events.append((int(t), kind, val, span))
                    break
        events.sort()
        # two slowing words on one note (rit. and smorz.) are one slowing, the stronger of them
        merged = []
        for ev in events:
            if merged and ev[0] == merged[-1][0] and ev[1] == merged[-1][1] == 'ramp' and ev[2] > 1:
                merged[-1] = max(merged[-1], ev, key=lambda e: e[2])
            else:
                merged.append(ev)
        events = merged
        cur = 1.0
        for idx, (u, kind, val, span) in enumerate(events):
            nxt = events[idx + 1][0] if idx + 1 < len(events) else n
            prev_u = events[idx - 1][0] if idx else 0
            if kind == 'set':
                for i in range(u, nxt):
                    sect[i] = val
                cur = val
            elif kind == 'dip':
                # a moment's give: ease over `span` 16ths, then back in time at the next bar
                back = int(next((b['start'] for b in self.bars if b['start'] > u), n))
                for i in range(u, min(nxt, back)):
                    sect[i] = cur * (1 + (val - 1) * min(1.0, (i - u + 1) / span))
            else:
                # a ramp from the current factor toward val, over `span` 16ths (or up to the next word).
                # A slowing is prepared: it begins half a bar before the word and eases in
                target = cur * val if val > 1 else val
                end = min(nxt, u + span) if span else nxt
                end = max(end, u + 1)
                start = max(prev_u + 1, u - 8) if val > 1 else u
                for i in range(start, nxt):
                    x = min(1.0, (i - start + 1) / (end - start))
                    sect[i] = cur + (target - cur) * (x ** 1.4 if val > 1 else x)
                cur = target
        # a cadenza the print gives no tempo word for runs on once past its measured beats
        for b in self.bars:
            s, ln = int(b['start']), int(b['len'])
            if ln != 16 and not any(s <= u < s + ln for u, *_ in events):
                for i in range(s + 16, s + ln):
                    sect[i] *= 0.72
        mult = list(sect)
        for b in self.bars:
            s, ln = int(b['start']), int(b['len'])
            if ln != 16:
                continue
            # the pulse of 4/4: a hair of weight on beat one, and on the half bar
            for j in range(16):
                mult[s + j] *= 1.03 if j < 2 else (1.012 if 8 <= j < 10 else 0.995)
        r = a.rubato
        sighs = [int(g['t']) for g in melodic_graces(self.notes)]
        sigh_len = {int(g['t']): max(nn['dur'] for nn in self.notes
                                     if nn['t'] == g['t'] and nn['line'] == 'R' and not nn['grace'])
                    for g in melodic_graces(self.notes)}
        # phrase rubato: settle in, press on through the middle, give at the close.  After a grace
        # note in the melody the phrase no longer presses: it breathes out to its close
        num_k = {b['num']: b['k'] for b in self.bars}
        for first, last in PHRASES:
            units = [u for b in self.bars[num_k[first]:num_k[last] + 1] if b['len'] == 16
                     for u in range(int(b['start']), int(b['start']) + 16)]
            for i, u in enumerate(units):
                x = (i + 0.5) / len(units)
                f = 1 + 0.05 * max(0.0, 1 - x / 0.12)
                if 0.08 < x < 0.85 and not any(units[0] <= s - 4 <= u for s in sighs):
                    f -= 0.09 * math.sin(math.pi * (x - 0.08) / 0.77)
                if x > 0.8:
                    f += 0.30 * ((x - 0.8) / 0.2) ** 2
                mult[u] *= 1 + (f - 1) * r
        # hairpins move the tempo too: on into a crescendo, relaxing through a diminuendo
        for t0, t1, amt in self.pins:
            u0, u1 = int(t0), int(t1)
            for u in range(u0, min(n, u1 + 4)):
                x = min(1.0, (u - u0 + 0.5) / max(1, u1 - u0))
                if u >= u1:
                    x = 1 - (u - u1) / 4         # and back over a beat
                mult[u] *= 1 + ((-0.05 if amt > 0 else 0.07) * x) * r
        # look ahead: into what changes.  A louder or faster arrival is pressed toward, with a
        # breath just before it; a softer or slower one, a key change or a section end is broadened
        # into, the more the bigger the change
        arrivals = {}
        for k in range(1, len(self.bars)):
            b, p = self.bars[k], self.bars[k - 1]
            s = int(b['start'])
            if p['len'] != 16:
                continue                         # after a cadenza: its own words have done it
            before, after = sect[s - 1], sect[min(n - 1, s + 1)]
            lv0, lv1 = self.level(b['start'] - F(1, 2)), self.level(b['start'] + F(1, 2))
            if after > before * 1.04 or lv1 < lv0 - 6 or b['key'] != p['key']:
                arrivals[s] = ('broaden', max(0.12, min(0.35, (after / before - 1) + (lv0 - lv1) / 60)))
            elif after < before * 0.96 or lv1 > lv0 + 8:
                arrivals[s] = ('press', min(0.10, (1 - after / before) + (lv1 - lv0) / 150))
        for s, (kind, amt) in arrivals.items():
            if kind == 'broaden':
                for j in range(8):               # over the last half bar
                    if s - 1 - j >= 0:
                        mult[s - 1 - j] *= 1 + amt * r * ((8 - j) / 8) ** 2
            else:
                for j in range(32):              # on through the last two bars, then a breath
                    if s - 1 - j >= 0:
                        mult[s - 1 - j] *= 1 - amt * r * (1 - j / 32)
                for j in range(2):
                    if s - 1 - j >= 0:
                        mult[s - 1 - j] *= 1 + 0.18 * r
        # and into a fermata over the beat before it
        ferm_starts = sorted({int(nn['t']) for nn in self.notes if nn['fermata']} |
                             {int(t) for t, d in self.held})
        for s in ferm_starts:
            for j in range(4):
                if s - 1 - j >= 0:
                    mult[s - 1 - j] *= 1 + 0.25 * r * ((4 - j) / 4) ** 2
        # a grace note in the melody is a moment to linger: the tempo gives over the beat before it,
        # stays held back through the rest of the bar (or, on a downbeat, through its long note), and
        # only then relaxes, over half a bar (less where the music is pressing on, as in the
        # affrettando)
        for s in sighs:
            give = (0.4 if sect[s] >= 0.98 else 0.12) * r
            bar_end = int(next((b['start'] for b in self.bars if b['start'] > s), n))
            if s == int(self.bar_at(s)['start']):
                bar_end = min(bar_end, s + int(sigh_len[s]))
            for j in range(4):
                if s - 1 - j >= 0:
                    mult[s - 1 - j] *= 1 + give * ((4 - j) / 4) ** 1.2
            for u in range(s, min(n, bar_end)):
                mult[u] *= 1 + give
            for j in range(8):
                if bar_end + j < n:
                    mult[bar_end + j] *= 1 + give * (1 - (j + 1) / 9)
        # fermatas: over notes, and over rests
        heldu = set()
        for nn in self.notes:
            if nn['fermata']:
                i = int(nn['t'])
                heldu.update(range(i, min(n, i + max(1, int(nn['dur'])))))
        sounding = {int(nn['t']) for nn in self.notes if not nn['grace']}
        for t, d in self.held:                 # a rest's fermata holds only where both hands rest
            heldu.update(u for u in range(int(t), min(n, int(t + d) + 1)) if u not in sounding)
        long_held = set()
        for nn in self.notes:
            if nn['fermata'] and nn['dur'] >= 8:            # a long note under a fermata
                long_held.update(range(int(nn['t']), min(n, int(nn['t'] + nn['dur']))))
        # however the effects compound, the music does not stall: a cap on the slowing, a little
        # higher under a fermata
        for j in range(n):
            if j not in heldu:
                mult[j] = min(mult[j], max(2.2, sect[j] * 1.35))
        for j in heldu:
            mult[j] *= 1.5 if j in long_held else 2.3
            mult[j] = min(mult[j], 2.8 if j in long_held else 4.2)
        # the close: a broad last line
        for j in range(32):
            i = n - 1 - j
            mult[i] *= 1 + 0.25 * ((32 - j) / 32) ** 2
        self.unit = [base * m for m in mult]
        self.start = [0.0]
        for d in self.unit:
            self.start.append(self.start[-1] + d)

    def sec(self, t):
        """Score time (16ths, may be fractional) -> seconds."""
        t = float(t)
        i = min(int(t), len(self.unit) - 1)
        return self.start[i] + (t - i) * self.unit[i]

    def tick(self, s):
        """Seconds -> MIDI ticks on the tempo map that follows self.unit."""
        i = bisect.bisect_right(self.start, s) - 1
        i = max(0, min(i, len(self.unit) - 1))
        return int(round(TPU * (i + (s - self.start[i]) / self.unit[i])))

# ---------------------------------------------------------------- rendering

def chord_offsets(pitches, hand, room, rnd):
    """When each key of a chord goes down, in seconds after the first (pitches ascending).
    A pianist's chord fans out over a few tens of milliseconds, mostly from the bottom up and
    wider the more notes and the wider the stretch, while the melody note (top of the right
    hand) or the bass (bottom of the left) comes first.  It never spreads over more than a
    third of the time to the hand's next chord."""
    n = len(pitches)
    if n == 1:
        return [0.0]
    span = pitches[-1] - pitches[0]
    width = (0.004 + 0.0045 * (n - 1) + 0.0004 * span) * rnd.uniform(0.6, 1.4)
    width = min(width, 0.045, room / 3)
    upward = rnd.uniform(0.45, 0.85)              # how much of the fan runs bottom to top
    offs = [width * (upward * i / (n - 1) + (1 - upward) * rnd.random()) for i in range(n)]
    lead = 0.006 + rnd.uniform(0, 0.006)
    if hand == 'R':
        offs[-1] = min(offs) - lead
    else:
        offs[0] = min(offs) - lead / 2
    first = min(offs)
    return [o - first for o in offs]

def melodic_graces(notes):
    """Single grace notes leading into a melody note of a quarter or more (bars 11, 24, 26):
    graces that ask for time, not the quick ones of a run."""
    out = []
    by_place = {}
    for n in notes:
        by_place.setdefault((n['line'], n['t']), []).append(n)
    for (line, t), ns in by_place.items():
        gr = [n for n in ns if n['grace']]
        main = [n for n in ns if not n['grace'] and n['dur'] >= 4]
        if line == 'R' and len({n['chord'] for n in gr}) == 1 and main:
            out.append(gr[0])
    return out

def figuration(n):
    """A note that is part of the accompanying figuration: a quick note in a run or arpeggio,
    not a stemmed or accented melody note."""
    return (n['value'] < F(1, 8) and not n['stemmed'] and 'accent' not in n['artic']
            and not n['grace'] and n['size'] == 1)

def render(notes, marks, bars, held, args):
    rnd = random.Random(args.seed)
    plan = Plan(notes, marks, bars, held, args)
    out = []                              # (sec_on, sec_off, pitch, vel)
    by_chord = {}
    for n in notes:
        by_chord.setdefault(n['chord'], []).append(n)
    # next onset per line, for legato
    onsets = {}
    for n in notes:
        if not n['grace']:
            onsets.setdefault(n['line'], set()).add(n['t'])
    onset_list = {h: sorted(v) for h, v in onsets.items()}

    def next_onset(h, t):
        lst = onset_list.get(h, [])
        i = bisect.bisect_right(lst, t)
        return lst[i] if i < len(lst) else None

    # the shape of a figure: in a run or arpeggio the notes swell toward its peak
    fig = sorted((n['t'], n['pitch']) for n in notes if figuration(n))
    fig_t = [f[0] for f in fig]
    def swell(n):
        lo, hi = bisect.bisect_left(fig_t, n['t'] - 8), bisect.bisect_right(fig_t, n['t'] + 8)
        if hi - lo < 4:
            return 0.0
        ps = [f[1] for f in fig[lo:hi]]
        mid = (max(ps) + min(ps)) / 2
        return max(-5.0, min(5.0, 0.22 * (n['pitch'] - mid)))

    graces = {}
    for n in notes:
        if n['grace']:
            graces.setdefault((n['line'], n['t']), []).append(n['chord'])
    sighs = {g['chord'] for g in melodic_graces(notes)}

    # a slow wander in the timing, shared by both hands (a hand's own placement comes on top)
    drift, x = [], 0.0
    for _ in range(plan.total + 1):
        x = 0.9 * x + rnd.gauss(0, 0.0022)
        drift.append(x)

    for cid, chord in sorted(by_chord.items(), key=lambda x: x[1][0]['t']):
        n0 = chord[0]
        t, h = n0['t'], n0['hand']
        line = n0['line']
        tex = plan.texture_at(t)
        lv = plan.level(t) + plan.pin(t)
        bar = plan.bar_at(t)
        pos = float(t - bar['start'])
        # 4/4: beat one strongest, beat three next
        metric = 0.0
        if bar['len'] == 16 and not figuration(n0):
            metric = 3 if pos == 0 else 1.5 if pos == 8 else (0.5 if pos % 4 == 0 else 0)
        place = drift[int(t)] + (rnd.gauss(0, 0.004) if line == 'R' else rnd.gauss(-0.004, 0.004))
        x = (float(t) % 64) / 64          # a four-bar arc
        arc = 3.5 * math.sin(math.pi * x) - 1.5
        if tex in ('leggierissimo', 'velocissimo', 'sotto voce', 'languendo'):
            lv -= 5
        if tex in ('impetuoso', 'con forza', 'marcato'):
            lv += 4
        on_base = plan.sec(t) + place
        unit = plan.unit[min(int(t), len(plan.unit) - 1)]
        if n0['grace']:
            # graces come just before the beat; a run of them (the harp of the più lento) rolls in
            seq = graces[(line, t)]
            rank = len(seq) - seq.index(cid)
            gap = min(0.055, 0.42 * unit * 2) if len(seq) < 4 else min(0.06, 0.5 * unit)
            if cid in sighs:
                gap = min(0.2, 0.45 * plan.unit[max(0, int(t) - 1)])   # unhurried, into the note
            on_base = plan.sec(t) + drift[int(t)] - rank * gap
        dur_s = plan.sec(t + n0['dur']) - plan.sec(t) if n0['dur'] else 0.06
        ar = n0['artic']
        # how long the key is held (the pedal carries most of the sound in this piece)
        if n0['grace']:
            hold = 0.12 if len(graces[(line, t)]) >= 4 else 0.06
            if cid in sighs:
                hold = plan.sec(t) - on_base + 0.03
        elif 'staccatissimo' in ar:
            hold = min(dur_s * 0.35, 0.09)
        elif 'staccato' in ar:
            hold = min(dur_s * 0.55, 0.16)
        elif tex == 'non legato' and figuration(n0):
            hold = dur_s * 0.8
        else:
            nx = next_onset(line, t)
            end = plan.sec(nx) + 0.018 if nx is not None and nx <= t + n0['dur'] + F(1, 1000) else plan.sec(t) + dur_s
            hold = max(end - on_base, dur_s * 0.98)
        if n0['fermata']:
            hold = max(hold, dur_s * 1.05)
        hold = max(hold, 0.035)
        ps = sorted(chord, key=lambda n: n['pitch'])
        nx = next_onset(line, t)
        room = plan.sec(nx) - plan.sec(t) if nx is not None else 1.0
        if n0['arp']:
            step = rnd.uniform(0.026, 0.036)       # a printed arpeggio rolls from the bottom
            offsets = [i * step for i in range(len(ps))]
        else:
            offsets = chord_offsets([n['pitch'] for n in ps], h, room, rnd)
        for idx, n in enumerate(ps):
            v = lv + metric + arc
            role = n['role']
            if figuration(n):
                # the accompanying figuration recedes, the more so in the left hand's arpeggios
                v -= 9 if line == 'L' else 5
                v += swell(n)
            else:
                if line == 'R':
                    v += 4                          # the melody sings over the figuration
                if role == 'top':
                    v += 5
                elif role == 'inner':
                    v -= 7
                elif role == 'bass':
                    v += 2
                elif line == 'L' and n['value'] >= F(1, 4):
                    v -= 5                          # a held bass note under the arpeggio
            if n['stemmed']:
                v += 7                              # a melody note that carries its own stem
            if 'accent' in ar:
                v += 8
            if 'marcato' in ar:
                v += 12
            if 'staccato' in ar and 'accent' not in ar:
                v -= 3
            if n['small']:
                v -= 7
            if n['grace']:
                v -= 8
            v += rnd.gauss(0, 2.0)
            if v < 30:
                v = 30 - (30 - v) * 0.5             # and the softest from vanishing
            if v > 98:
                v = 98 + (v - 98) * 0.45            # soft knee: keep the loudest chords from clipping
            v = int(max(10, min(118, round(v))))
            on = on_base + offsets[idx]
            off = on_base + hold + rnd.gauss(0, 0.006)     # releases are a little uneven too
            out.append((on, max(off, on + 0.03), n['pitch'], v))
    out.sort()
    return plan, out, pedal_plan(plan, notes)

def pedal_plan(plan, notes):
    """Sempre pedale: the pedal goes down at the start and changes, just after the beat, wherever
    the harmony moves: at a beat whose notes have little in common with the beat before.  An
    arpeggio climbing through one chord keeps its bass; a chromatic run is cleared beat by beat."""
    beats = {}
    for n in notes:
        beats.setdefault(int(n['t'] // 4), []).append(n)
    pedal = [(plan.sec(0) + 0.004, 127)]
    prev = None
    for b in sorted(beats):
        pcs = {n['pitch'] % 12 for n in beats[b]}
        if prev is not None and len(pcs & prev) / len(pcs | prev) < 0.5:
            t = min(n['t'] for n in beats[b])
            gr = any(n['grace'] for n in beats[b])
            lift = plan.sec(t) - (0.30 if gr else 0.0) - 0.002   # before a roll of graces, ahead of it
            pedal.append((lift, 0))
            pedal.append((lift + 0.075, 127))
        prev = pcs
    pedal.sort()
    return pedal

# ---------------------------------------------------------------- MIDI

def vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F)); n >>= 7
    return bytes(reversed(out))

def chunk(events):
    events.sort(key=lambda e: (e[0], e[1]))
    data, last = bytearray(), 0
    for t, _, b in events:
        data += vlq(t - last) + b; last = t
    data += b'\x00\xff\x2f\x00'
    return b'MTrk' + struct.pack('>I', len(data)) + bytes(data)

def meta(kind, payload):
    return bytes([0xFF, kind]) + vlq(len(payload)) + payload

KEY_NAMES = {-5: (-5, 0), 3: (3, 0), 4: (4, 1)}   # sharps/flats -> (sf, minor?)

def write(path, plan, out, pedal, bars, title):
    cond = [(0, 0, meta(0x03, title.encode('latin-1'))),
            (0, 1, meta(0x58, bytes([4, 2, 24, 8])))]
    last_key, last_len = None, 16
    for b in bars:
        tick = int(b['start']) * TPU
        if b['key'] != last_key:
            sf, mi = KEY_NAMES.get(b['key'], (b['key'], 0))
            cond.append((tick, 2, meta(0x59, struct.pack('>bB', sf, mi))))
            last_key = b['key']
        if b['len'] != last_len:            # a cadenza bar: its own length, in 16ths
            ln = int(b['len'])
            sig = (ln // 4, 2) if ln % 4 == 0 else ((ln // 2, 3) if ln % 2 == 0 else (ln, 4))
            cond.append((tick, 1, meta(0x58, bytes([sig[0], sig[1], 24, 8]))))
            last_len = b['len']
        cond.append((tick, 3, meta(0x06, f"m.{b['num']}".encode())))
    last_us = None
    for i, d in enumerate(plan.unit):
        us = int(round(d * 4 * 1e6))
        if us != last_us:
            cond.append((i * TPU, 4, meta(0x51, us.to_bytes(3, 'big'))))
            last_us = us
    for t, h, mk in plan.marks:
        if mk[0] == 'word' and mk[1]:
            cond.append((int(t * TPU), 5, meta(0x01, mk[1].encode('latin-1'))))
    piano = [(0, 0, meta(0x03, b'Piano')), (0, 1, bytes([0xB0, 0x00, 0x00])), (0, 2, bytes([0xC0, 0x00])),
             (0, 3, bytes([0xB0, 0x07, 110]))]
    # one key, one sounding note: a re-strike ends the previous one, and two strikes of the same key
    # at once (a note that is the arpeggio's first and the held bass too) are one
    evs = []
    by_p = {}
    for e in sorted([on, off, p, v] for on, off, p, v in out):
        prev = by_p.get(e[2])
        if prev and e[0] - prev[-1][0] < 0.03:
            prev[-1][1] = max(prev[-1][1], e[1])
            prev[-1][3] = max(prev[-1][3], e[3])
            continue
        by_p.setdefault(e[2], []).append(e)
        evs.append(e)
    for p, lst in by_p.items():
        for a, b in zip(lst, lst[1:]):
            if a[1] > b[0] - 0.012:
                a[1] = max(a[0] + 0.02, b[0] - 0.012)
    for on, off, p, v in evs:
        t0, t1 = plan.tick(max(0.0, on)), plan.tick(max(0.0, off))
        if t1 <= t0:
            t1 = t0 + 1
        piano.append((t0, 6, bytes([0x90, p, v])))
        piano.append((t1, 5, bytes([0x80, p, 64])))
    for s, val in pedal:
        piano.append((plan.tick(max(0.0, s)), 4 if val == 0 else 7, bytes([0xB0, 64, val])))
    end = plan.tick(plan.start[-1]) + PPQ * 2
    piano.append((end, 9, bytes([0xB0, 64, 0])))
    data = b'MThd' + struct.pack('>IHHH', 6, 1, 2, PPQ) + chunk(cond) + chunk(piano)
    with open(path, 'wb') as f:
        f.write(data)

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('brf')
    ap.add_argument('-o', '--out', default='sospiro.mid')
    ap.add_argument('--tempo', type=float, default=72, help='quarter notes per minute')
    ap.add_argument('--rubato', type=float, default=1.0, help='how much the tempo gives and takes (1 = as built)')
    ap.add_argument('--seed', type=int, default=144)
    ap.add_argument('--report', action='store_true', help='print tempo, loudness and markings bar by bar')
    args = ap.parse_args()
    measures, order = build(open(args.brf, encoding='ascii').read())
    notes, marks, bars, held = flatten(measures, order)
    plan, out, pedal = render(notes, marks, bars, held, args)
    write(args.out, plan, out, pedal, bars, 'Liszt: Un sospiro (Trois etudes de concert, S.144 No. 3)')
    if args.report:
        report(plan, out, marks, bars)
    print(f'{args.out}: {len(bars)} bars, {len(out)} notes, {plan.start[-1]:.1f} s')

def report(plan, out, marks, bars):
    starts = [plan.sec(b['start']) for b in bars] + [plan.start[-1]]
    ons = sorted((on, v) for on, off, p, v in out)
    times = [o[0] for o in ons]
    words = {}
    for t, h, mk in marks:
        k = plan.bars.index(plan.bar_at(t))
        if mk[0] == 'word':
            words.setdefault(k, []).append(mk[1])
        elif mk[0] == 'hairpin':
            words.setdefault(k, []).append({'cresc': '<', 'dim': '>'}.get(mk[1], '|'))
    for k, b in enumerate(bars):
        s0, s1 = starts[k], starts[k + 1]
        vs = [v for _, v in ons[bisect.bisect_left(times, s0):bisect.bisect_left(times, s1)]]
        mean = sum(vs) / len(vs) if vs else 0
        q = 60 * b['len'] / 4 / (s1 - s0)
        print(f"m.{b['num']:<4d}{s0:7.1f}s  q={q:5.1f}  vel {mean:5.1f} (max {max(vs, default=0):3d})"
              f"  level {plan.level(b['start']):5.1f}  {plan.texture_at(b['start']):12s} {' '.join(words.get(k, []))}")

if __name__ == '__main__':
    main()
