#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
brf.py -- read a bar-over-bar keyboard score in North American ASCII music braille (BANA
Music Braille Code) into timed note events.

Only the part of the code that the transcription of Liszt's Un sospiro uses is handled;
anything else raises.  The key and time signatures come from the end of the title page.
"""
import copy, itertools, math, re, sys
from fractions import Fraction as F

# ---------------------------------------------------------------- tables

NOTE_CELLS = {}
for form, row in enumerate(('defghij', '?:$]\\[w', 'nopqrst', 'yz&=(!)')):   # 8th, 4th, half, whole
    for step, ch in enumerate(row):                                            # C D E F G A B
        NOTE_CELLS[ch] = (step, form)
REST_CELLS = {'x': 0, 'v': 1, 'u': 2, 'm': 3}
INTERVALS = {'/': 1, '+': 2, '#': 3, '9': 4, '0': 5, '3': 6, '-': 7}
OCTAVES = [(',,', 8), ('@@', 0), (',', 7), (';', 6), ('.', 5), ('"', 4), ('_', 3), ('^', 2), ('@', 1)]
ACCS = [('%%', 2), ('<<', -2), ('%', 1), ('<', -1), ('*', 0)]
STEMS = {'a': F(1, 4), 'b': F(1, 8), 'k': F(1, 2), 'l': F(1, 16)}
DIATONIC = [0, 2, 4, 5, 7, 9, 11]
SHARP_ORDER = [3, 0, 4, 1, 5, 2, 6]       # F C G D A E B
FLAT_ORDER = [6, 2, 5, 1, 4, 0, 3]        # B E A D G C F
MEASURE = F(1)                            # set from the time signature by build()
BEAT = F(1, 4)

def key_alters(n):
    """Key signature with n sharps (n>0) or flats (n<0) -> {step: alteration}."""
    return {s: 1 for s in SHARP_ORDER[:n]} if n >= 0 else {s: -1 for s in FLAT_ORDER[:-n]}

def braille_number(s):
    return int(''.join('1234567890'['abcdefghij'.index(ch)] for ch in s))

# ---------------------------------------------------------------- tokenizer

WORD_RUN = re.compile(r"(?: [a-z')]+)*>")

def tokenize(s):
    """Tokenize one line of music (hand sign included) into a flat list of tuples."""
    toks, i, n = [], 0, len(s)
    def at(p):
        return s.startswith(p, i)
    while i < n:
        c = s[i]
        if c == ' ':
            toks.append(('sep',)); i += 1; continue
        if at('.>>') or at('_>>'):
            toks.append(('hand', 'R' if c == '.' else 'L')); i += 3; continue
        if at('.>') or at('_>'):
            toks.append(('hand', 'R' if c == '.' else 'L')); i += 2; continue
        if at('<>'):
            toks.append(('inacc',)); i += 2; continue
        if at('"1'):
            toks.append(('pinacc',)); i += 2; continue
        if at('.k'):
            toks.append(('mdiv',)); i += 2; continue
        if at("<k'"):
            toks.append(('bar', 'double')); i += 3; continue
        if at('<k'):
            toks.append(('bar', 'final')); i += 2; continue
        if at('<7'):
            toks.append(('repeat_start',)); i += 2; continue
        if at('<2'):
            toks.append(('repeat_end',)); i += 2; continue
        if (at('#1') or at('#2')) and not any(t[0] in ('note', 'rest') for t in toks):
            toks.append(('ending', int(s[i + 1]))); i += 2; continue
        m = re.match(r",'(%%|<<|%|<|\*),'", s[i:])
        if m:                                       # a cautionary accidental, in parentheses in print
            toks.append(('acc', dict(ACCS)[m.group(1)])); i += m.end(); continue
        if at(",'"):
            toks.append(('comma',)); i += 2; continue
        if at('<l'):
            toks.append(('fermata',)); i += 2; continue
        if at('<c'):
            toks.append(('ped', 'down')); i += 2; continue
        if at('*c'):
            toks.append(('ped', 'up')); i += 2; continue
        if at('@c'):
            toks.append(('tie', 'note')); i += 2; continue
        if at('.c'):
            toks.append(('tie', 'chord')); i += 2; continue
        if at('"c'):
            toks.append(('slur', 'cross')); i += 2; continue
        if at(';b'):
            toks.append(('slur', 'open')); i += 2; continue
        if at('^2'):
            toks.append(('slur', 'close')); i += 2; continue
        if at('.l'):
            toks.append(('alternate', F(1, 16))); i += 2; continue
        m = re.match(r"_([1-90]+)'", s[i:])
        if m:
            toks.append(('tuplet', int(m.group(1)), False)); i += m.end(); continue
        if c == '2':
            j = i
            while j < n and s[j] == '2':
                j += 1
            toks.append(('tuplet', 3, j - i > 1)); i = j; continue
        if c == '_' and i + 1 < n and s[i + 1] in STEMS:
            val = STEMS[s[i + 1]]; i += 2
            if i < n and s[i] == "'":
                val = val * 3 / 2; i += 1
            toks.append(('stem', val)); continue
        if c == '>':
            if i + 1 < n and s[i + 1] in '34':
                toks.append(('hairpin', 'end')); i += 2; continue
            if at('>59'):
                toks.append(('word', 'SIGN')); i += 3; continue
            m = re.match(r"[a-z]+", s[i + 1:])
            word = m.group(0) if m else ''
            j = i + 1 + len(word)
            if word in ('c', 'd'):
                toks.append(('hairpin', 'cresc' if word == 'c' else 'dim')); i = j
                if i < n and s[i] == "'":
                    i += 1
                continue
            if word == 'k':
                toks.append(('arpeggio',)); i = j; continue
            if j < n and s[j] == "'":
                word += '.'; j += 1
            if j < n and s[j] == ' ':           # a multi-word expression runs to a closing '>'
                m2 = WORD_RUN.match(s[j:])
                if m2:
                    word += s[j:j + m2.end() - 1].replace("'", '.')
                    j += m2.end()
                    if j < n and s[j] == ' ':
                        j += 1
            toks.append(('word', word)); i = j; continue
        if at('.8'):
            toks.append(('artic', 'accent')); i += 2; continue
        if at(';8'):
            toks.append(('artic', 'marcato')); i += 2; continue
        if at('_8'):
            toks.append(('artic', 'tenuto')); i += 2; continue
        if at(',8'):
            toks.append(('artic', 'staccatissimo')); i += 2; continue
        if c == '8':
            toks.append(('artic', 'staccato')); i += 1; continue
        if at(',55'):
            toks.append(('small', True)); i += 3; continue
        if at(',5'):
            toks.append(('small', False)); i += 2; continue
        if at('55'):
            toks.append(('grace', True)); i += 2; continue
        if c == '5':
            toks.append(('grace', False)); i += 1; continue
        if c == '7':
            toks.append(('repeat',)); i += 1; continue
        hit = False
        for p, o in OCTAVES:
            if at(p):
                toks.append(('oct', o)); i += len(p); hit = True; break
        if hit:
            continue
        for p, a in ACCS:
            if at(p):
                toks.append(('acc', a)); i += len(p); hit = True; break
        if hit:
            continue
        if c in NOTE_CELLS or c in REST_CELLS:
            i += 1; dots = 0
            while i < n and s[i] == "'":
                dots += 1; i += 1
            if c in NOTE_CELLS:
                toks.append(('note', NOTE_CELLS[c][0], NOTE_CELLS[c][1], dots))
            else:
                toks.append(('rest', REST_CELLS[c], dots))
            continue
        if c in INTERVALS:
            dbl = i + 1 < n and s[i + 1] == c
            toks.append(('interval', INTERVALS[c], dbl)); i += 2 if dbl else 1; continue
        if c == 'c':
            if at('cc'):
                toks.append(('slur', 'double')); i += 2
            else:
                toks.append(('slur', 'note')); i += 1
            continue
        if c == "'":
            i += 1; continue          # guide dot, or separator after a hand sign or word
        raise ValueError(f'unknown sign {c!r} at {i} in {s!r}')
    return toks

# ---------------------------------------------------------------- reading the file

KEYLINE = re.compile(r'^(?:%+|<+|#[a-j]+[%<])$')

def keysig_value(s):
    if not s:
        return 0
    if set(s) == {'%'}:
        return len(s)
    if set(s) == {'<'}:
        return -len(s)
    m = re.match(r'#([a-j]+)([%<])$', s)
    v = braille_number(m.group(1))
    return v if m.group(2) == '%' else -v

SIGNATURE = re.compile(r"(#[a-j]+[%<]|[%<]*)(\.c|_c|#[a-j]+[1-90]+)\s*$")

def meter(s):
    """A braille time signature -> (measure length, beat), in whole notes."""
    if s in ('.c', '_c'):                       # common time, alla breve
        return (F(1), F(1, 4)) if s == '.c' else (F(1), F(1, 2))
    m = re.match(r'#([a-j]+)([1-90]+)$', s)
    up, low = braille_number(m.group(1)), int(m.group(2))
    beat = F(3, low) if low == 8 and up % 3 == 0 and up > 3 else F(1, low)
    return F(up, low), beat

# Slips in a transcription, checked against the print: (measure line as it is, as it should be).
CORRECTIONS = []

def read_parallels(text):
    """The parallels in order: {'num', 'lines': [line, ...], 'key': sharps/flats or None, 'text': [...]},
    with the opening key signature and the meter."""
    text = text.replace('\r', '')
    for bad, good in CORRECTIONS:
        if bad not in text:
            raise ValueError(f'correction does not apply: {bad!r}')
        text = text.replace(bad, good)
    lines = text.split('\n')
    start = next(k for k, l in enumerate(lines) if re.match(r'^a +\.>', l))
    end = next(k for k, l in enumerate(lines) if l.startswith('333333'))
    head = ' '.join(lines[:start])
    m = SIGNATURE.search(head.strip())
    if not m:
        raise ValueError('no key and time signature at the end of the title page')
    key0 = keysig_value(m.group(1))
    metre = meter(m.group(2))
    pars, cur = [], None
    pending_key, pending_text = None, []
    for raw in lines[start:end]:
        if not raw.strip():
            continue
        m = re.match(r'^([a-j]+) +((?:\.>|_>).*)$', raw)
        if m:
            cur = {'num': braille_number(m.group(1)), 'lines': [m.group(2)], 'key': pending_key,
                   'text': pending_text}
            pending_key, pending_text = None, []
            pars.append(cur)
            continue
        st = raw.strip()
        if re.match(r'^ {2,6}(\.>|_>)', raw):
            cur['lines'].append(st); continue
        if KEYLINE.match(st):
            pending_key = keysig_value(st); continue
        if st.startswith(','):
            pending_text.append(st.replace(',', '')); continue
        prev = cur['lines'][-1]                     # continuation of the previous line
        cur['lines'][-1] = prev[:-1] + st if prev.endswith('"') else prev + ' ' + st
    for p in pars:                                  # a music hyphen inside a line joins across the space
        p['lines'] = [l.replace('" ', '') for l in p['lines']]
    return key0, metre, pars

# ---------------------------------------------------------------- pass A: tokens -> items

def place(step, prev, octave):
    """Octave of a note: its octave mark, else the one BANA's rules give from the previous note."""
    if octave is not None:
        return octave
    if prev is None:
        raise ValueError('first note has no octave mark')
    ps, po = prev
    fourth_fifth = None
    for o in (po - 1, po, po + 1):
        d = (step + 7 * o) - (ps + 7 * po)
        if abs(d) <= 2:
            return o
        if abs(d) in (3, 4) and o == po:
            fourth_fifth = o
    return fourth_fifth

class Voice:
    """Reading state of one voice: octave reference, doublings, grace and slur runs."""
    def __init__(self, hand):
        self.hand = hand
        self.prev = None
        self.doubled = {}            # interval -> small
        self.grace_run = False
        self.slur_run = False
        self.small_run = False       # a passage of small (cue-size) notes
    def copy(self):
        v = Voice(self.hand)
        v.prev, v.doubled, v.grace_run, v.slur_run = self.prev, dict(self.doubled), self.grace_run, self.slur_run
        v.small_run = self.small_run
        return v

def add_interval(chord, n, hand, small, acc=None, octave=None):
    ws, wo = chord['notes'][0]['step'], chord['notes'][0]['oct']
    idx = ws + 7 * wo + (-n if hand == 'R' else n)
    s2, o2 = idx % 7, idx // 7
    if octave is not None:
        o2 = octave
    chord['notes'].append({'step': s2, 'oct': o2, 'acc': acc, 'octave_of': n == 7 and octave is None,
                           'small': small})

def close_chord(chord, v):
    if chord is None or chord['kind'] != 'chord':
        return
    written = chord.pop('written_iv')
    for n, small in chord.pop('active_doubled').items():
        if n not in written:
            add_interval(chord, n, chord['hand'], small)

def voice_items(toks, v):
    """One voice's tokens -> items: chords, rests, repeats; markers ride on the next timed item."""
    items, markers, artic = [], [], []
    acc = octv = small = tuplet = small_note = None
    comma = False
    grace = False
    cur = None
    for ti, t in enumerate(toks):
        k = t[0]
        nxt = toks[ti + 1] if ti + 1 < len(toks) else None
        if k in ('note', 'rest', 'repeat'):
            close_chord(cur, v)
        if k == 'hand':
            v.hand = t[1]
        elif k == 'hairpin' and t[1] == 'end' and cur is not None:
            cur['markers'].append(t)
        elif k in ('ped', 'word', 'hairpin', 'arpeggio', 'repeat_start', 'repeat_end', 'ending', 'bar'):
            markers.append(t)
        elif k == 'artic':
            if nxt is not None and nxt[0] == 'stem' and cur is not None:
                cur['artic'].append(t[1])          # an accent on a stemmed melody note
            else:
                artic.append(t[1])
        elif k == 'grace':
            grace = True
            v.grace_run = t[1]
        elif k == 'comma':
            comma = True
        elif k == 'small':
            ahead = next((u for u in toks[ti + 1:] if u[0] not in ('acc', 'oct', 'artic')), None)
            if ahead is not None and ahead[0] == 'note':
                # before a note: a small note; doubled, the first of a passage of them, which a single
                # sign before its last note closes
                if t[1]:
                    v.small_run = True
                    small_note = 'one'
                else:
                    small_note = 'last' if v.small_run else 'one'
            else:
                small = t
        elif k == 'tuplet':
            tuplet = t
        elif k == 'oct':
            octv = t[1]
        elif k == 'acc':
            acc = t[1]
        elif k == 'note':
            step, form, dots = t[1], t[2], t[3]
            o = place(step, v.prev, octv)
            v.prev = (step, o)
            is_small = v.small_run or small_note is not None
            if small_note == 'last':
                v.small_run = False
            small_note = None
            cur = {'kind': 'chord', 'notes': [{'step': step, 'oct': o, 'acc': acc, 'octave_of': False,
                                               'small': is_small}], 'small': is_small, 'comma': comma,
                   'form': form, 'dots': dots, 'hand': v.hand, 'grace': grace or v.grace_run,
                   'markers': markers, 'artic': artic, 'tuplet': tuplet,
                   'slur': 'run' if v.slur_run else None,
                   'written_iv': set(), 'active_doubled': dict(v.doubled)}
            items.append(cur)
            markers, artic = [], []
            acc = octv = tuplet = None
            grace = comma = False
        elif k == 'interval':
            n, dbl = t[1], t[2]
            is_small = small is not None or cur.get('small', False)
            add_interval(cur, n, v.hand, is_small, acc, octv)
            cur['written_iv'].add(n)
            if dbl:
                v.doubled[n] = is_small or bool(small and small[1])
            else:
                v.doubled.pop(n, None)
            acc = octv = small = None
        elif k == 'rest':
            cur = {'kind': 'rest', 'form': t[1], 'dots': t[2], 'markers': markers, 'tuplet': tuplet,
                   'hand': v.hand}
            items.append(cur)
            markers = []
            octv = tuplet = None
        elif k == 'repeat':
            cur = {'kind': 'repeat', 'oct': octv, 'markers': markers}
            items.append(cur)
            markers = []
            octv = None
        elif k == 'stem':
            cur['stem'] = t[1]
        elif k == 'tie':
            cur['tie'] = t[1]
        elif k == 'slur':
            if t[1] == 'open':
                v.slur_run = True
                if cur is not None and cur['kind'] == 'chord':
                    cur['slur'] = 'run'
            elif t[1] == 'close':
                v.slur_run = False
            elif t[1] == 'cross':
                if cur is not None and cur['kind'] == 'chord':
                    cur['slur'] = cur.get('slur') or 'note'
            elif t[1] == 'double':
                v.slur_run = True
                cur['slur'] = 'run'
            else:
                if v.slur_run:
                    v.slur_run = False
                cur['slur'] = 'note'
        elif k == 'fermata':
            cur['fermata'] = True
        elif k == 'alternate':
            cur['alternate'] = t[1]
        else:
            raise ValueError(f'unhandled token {t}')
    close_chord(cur, v)
    if markers:
        items.append({'kind': 'marker', 'markers': markers})
    return items

def split_on(toks, kind):
    out, cur = [], []
    for t in toks:
        if t[0] == kind:
            out.append(cur); cur = []
        else:
            cur.append(t)
    out.append(cur)
    return out

def measure_structure(toks, v):
    """A measure's tokens for one line -> list of voices; a voice is a list of blocks, each block
    either ('seq', items) or ('par', [items, items, ...]).  v is the main voice's state."""
    voices = []
    for vi, vt in enumerate(split_on(toks, 'inacc')):
        vs = v if vi == 0 else v.copy()
        blocks = []
        for bt in split_on(vt, 'mdiv'):
            parts = split_on(bt, 'pinacc')
            if len(parts) == 1:
                blocks.append(('seq', voice_items(bt, vs)))
            else:
                start = vs.copy()
                first = voice_items(parts[0], vs)
                rest = [voice_items(p, start.copy()) for p in parts[1:]]
                blocks.append(('par', [first] + rest))
        voices.append(blocks)
    return voices

# ---------------------------------------------------------------- durations

# the two values each note shape stands for (8th or 128th, quarter or 64th, ...), the likelier first
VALUES = [[F(1, 8), F(1, 128)], [F(1, 4), F(1, 64)], [F(1, 2), F(1, 32)], [F(1, 16), F(1, 1)]]

def dotted(val, dots):
    return val * (2 - F(1, 2 ** dots))

def timed(items):
    return [it for it in items if it['kind'] in ('rest', 'repeat') or it['kind'] == 'chord' and not it['grace']]

class Choice:
    """Enumerates the ambiguous readings of a measure, in order of preference."""
    def __init__(self, choices):
        self.choices = choices
        self.k = {}
    def get(self, key, options):
        if key not in self.choices:
            self.choices[key] = options
        return options[self.k.get(key, 0)]

def tuplet_spans(n):
    """How many of the written value n tuplet notes may stand for, likeliest first."""
    p = 1
    while p * 2 < n:
        p *= 2
    return [p] + [m for m in (4, 3, 2, 6, 8, 16) if m != p]

def durations(items, ch, pos0, tag):
    """Give every timed item a 'dur' (and repeats their unit), reading choices from ch.
    Returns the voice's total length."""
    pos = pos0
    group = False
    last_val = None
    tup_left, tup_scale, tup_dbl = 0, F(1), False
    seq = timed(items)
    for idx, it in enumerate(seq):
        if it['kind'] == 'repeat':
            prev = [p for p in seq[:idx] if p['kind'] != 'repeat']
            if not prev:
                it['dur'] = None                  # a whole-measure repeat, resolved later
                return None
            # the unit: the last j items before the repeat sign (consecutive signs repeat the same unit)
            j0 = idx
            while j0 > 0 and seq[j0 - 1]['kind'] == 'repeat':
                j0 -= 1
            cands = list(range(1, len([p for p in seq[:j0]]) + 1))
            # likeliest first: a unit of a beat, or of the tuplet group just ended
            span = lambda j: sum(u['dur'] for u in seq[j0 - j:j0] if u.get('dur'))
            tup_group = [j for j in cands if seq[j0 - j].get('tuplet')]
            beat = [j for j in cands if span(j) == BEAT]
            pref = tup_group[:1] + [j for j in beat if j not in tup_group[:1]]
            cands = pref + [j for j in cands if j not in pref]
            j = ch.get((tag, idx, 'rep'), cands)
            unit = seq[j0 - j:j0]
            it['unit'] = unit
            it['dur'] = sum(u['dur'] for u in unit)
            pos += it['dur']
            continue
        form, dots = it['form'], it['dots']
        opts = VALUES[form]
        if it['kind'] == 'rest':
            if form == 3 and len(seq) == 1:
                val = MEASURE                      # a whole rest fills the measure
            else:
                if last_val is not None and last_val == min(opts):
                    opts = sorted(opts)            # a rest among short notes is likely as short
                val = ch.get((tag, idx, 'val'), opts)
            group = False
        elif form == 0 and group and not it.get('comma'):
            val = group                            # the rest of a group of short notes
        else:
            after = seq[idx + 1:idx + 3]
            if form and len(after) == 2 and all(a['kind'] == 'chord' and a['form'] == 0 for a in after):
                opts = sorted(opts)                # likely the first of a group of short notes
            val = ch.get((tag, idx, 'val'), opts)
            nxt = seq[idx + 1] if idx + 1 < len(seq) else None
            # a group of short notes: this one in its own value, the next in the 8th shape (a music
            # comma ends the group)
            group = val if (val < F(1, 8) and nxt and nxt['kind'] == 'chord' and nxt['form'] == 0 and
                            not nxt.get('comma') and ch.get((tag, idx, 'grp'), [True, False])) else False
        last_val = val
        d = dotted(val, dots)
        tp = it.get('tuplet')
        if tp:
            n = tp[1]
            if n == 3:
                tup_scale = F(2, 3)
            else:
                m = ch.get((tag, idx, 'tup'), tuplet_spans(n))
                tup_scale = F(m, n)
            # a group usually has n notes, but may hold longer ones (a quarter and an eighth
            # under a triplet sign)
            count = ch.get((tag, idx, 'tupn'), [n] + [k for k in range(1, n) if k != n])
            tup_left, tup_dbl = count, tp[2]
        if tup_left:
            d *= tup_scale
            tup_left -= 1
            if tup_left == 0 and tup_dbl:
                tup_left = 3
        it['dur'] = d
        pos += d
        if group and not tup_left and (pos - pos0) % BEAT == 0 and pos != pos0:
            group = False                          # a 16th group runs to the beat, or to the tuplet's end
        alt = it.get('alternate')
        if alt and idx + 1 < len(seq):
            # a fingered tremolo: both notes are written with the whole span
            seq[idx + 1]['alt_pair'] = True
    total = pos - pos0
    # the second note of a fingered tremolo takes no time of its own
    for it in seq:
        if it.get('alt_pair'):
            total -= it['dur']
    return total

def block_lengths(blocks, ch, tag):
    total = F(0)
    for bi, (kind, body) in enumerate(blocks):
        if kind == 'seq':
            d = durations(body, ch, total, (tag, bi))
            if d is None:
                return None
            total += d
        else:
            ds = [durations(p, ch, total, (tag, bi, pi)) for pi, p in enumerate(body)]
            if any(x is None for x in ds):
                return None
            if len(set(ds)) != 1:
                return 'mismatch'
            total += ds[0]
    return total

def readings(choices, keys, depth):
    """Every assignment that departs from the likeliest reading at exactly `depth` decisions."""
    for sub in itertools.combinations(keys, depth):
        for picks in itertools.product(*[range(1, len(choices[k])) for k in sub]):
            yield dict(zip(sub, picks))

def solve_voice(blocks, vi, expect, max_depth=5):
    """The reading of one voice that fills the measure, departing from the likeliest values as
    little as possible.  Returns (picks, length) or (None, length of the likeliest reading)."""
    choices = {}
    ch = Choice(choices)
    for regroup in (False, True):            # break up a group of short notes only as a last resort
        for depth in range(max_depth + 1):
            seen = -1
            while seen != len(choices):      # deciding may turn up new decisions; look again
                seen = len(choices)
                keys = [k for k in choices if regroup or k[-1] != 'grp']
                if math.comb(len(keys), depth) > 200000:
                    break
                for k in readings(choices, keys, depth):
                    ch.k = k
                    r = block_lengths(blocks, ch, vi)
                    if r is None or r == expect:
                        return k, r
    ch.k = {}
    return None, block_lengths(blocks, ch, vi)

def solve_measure(voices, expect=None, free=False, max_depth=5):
    """Find the reading in which every voice fills the measure.  Returns (ok, lengths).
    Each voice's length is None where it is a whole-measure repeat sign.  With free, a voice
    may run past the measure (a cadenza): it takes its likeliest reading."""
    expect = MEASURE if expect is None else expect
    res, ok = [], True
    for vi, b in enumerate(voices):
        if free:
            ch = Choice({})
            r = block_lengths(b, ch, vi)
            ok = ok and r is not None and r != 'mismatch' and r >= expect
            res.append(r)
            continue
        k, r = solve_voice(b, vi, expect, max_depth)
        if k is None:
            ok = False
        else:                                # lay the voice out again with the reading that fits
            ch = Choice({}); ch.k = k
            r = block_lengths(b, ch, vi)
        res.append(r)
    return ok, res

# ---------------------------------------------------------------- pass B: times and pitches

def measures_of_line(line):
    ms = [m for m in split_on(tokenize(line), 'sep') if m]
    if len(ms) > 1 and all(t[0] == 'hand' for t in ms[0]):
        ms = [ms[0] + ms[1]] + ms[2:]
    return ms

def lay_out(items, t0, out, voice):
    """Put a sequence of items on the measure's time line; returns the end time."""
    t = t0
    graces = []
    for it in items:
        k = it['kind']
        if k == 'marker':
            out.append({'t': t, 'kind': 'marker', 'markers': it['markers'], 'voice': voice})
            continue
        if k == 'chord' and it['grace']:
            graces.append(it)
            continue
        if k == 'repeat':
            unit = copy.deepcopy(it['unit'])
            if it['oct'] is not None:
                first = next(u for u in unit if u['kind'] == 'chord')
                shift = it['oct'] - first['notes'][0]['oct']
                for u in unit:
                    for n in u.get('notes', []):
                        n['oct'] += shift
            for u in unit:
                u['markers'] = []
                u.pop('alt_pair', None)
            ends = [mk for mk in it['markers'] if mk == ('hairpin', 'end')]
            if len(ends) < len(it['markers']):
                out.append({'t': t, 'kind': 'marker', 'markers': [mk for mk in it['markers'] if mk not in ends],
                            'voice': voice})
            t = lay_out(unit, t, out, voice)
            if ends:                             # a hairpin that closes after the repeated notes
                out.append({'t': t, 'kind': 'marker', 'markers': ends, 'voice': voice})
            continue
        for g in graces:
            out.append(dict(g, t=t, voice=voice))
        graces = []
        ev = dict(it, t=t, voice=voice)
        out.append(ev)
        if not it.get('alternate'):          # a fingered tremolo's two notes share one span
            t += it['dur']
    return t

def measure_events(voices):
    out = []
    for vi, blocks in enumerate(voices):
        t = F(0)
        for bi, (kind, body) in enumerate(blocks):
            if kind == 'seq':
                t = lay_out(body, t, out, (vi, bi, 0))
            else:
                ends = [lay_out(p, t, out, (vi, bi, pi)) for pi, p in enumerate(body)]
                t = ends[0]
    return out

def pitch_of(step, octv, alter):
    return 12 * (octv + 1) + DIATONIC[step] + alter

def resolve_pitches(events, key, carried):
    """Fill in 'pitches' on chord events (time order), from accidentals, the key and ties."""
    mem = dict(carried)
    chords = sorted((e for e in events if e['kind'] == 'chord'), key=lambda e: (e['t'], e['voice']))
    for e in chords:
        ps = []
        w = e['notes'][0]
        wp = None
        for n in e['notes']:
            if n['octave_of'] and n['acc'] is None and wp is not None:
                p = wp + 12 * (n['oct'] - w['oct'])
            else:
                kk = (n['step'], n['oct'])
                if n['acc'] is not None:
                    mem[kk] = n['acc']
                alter = mem.get(kk, key.get(n['step'], 0))
                p = pitch_of(n['step'], n['oct'], alter)
            if wp is None:
                wp = p
            ps.append(p)
        e['pitches'] = ps
    # what a tie carries into the next measure
    out = {}
    for e in chords:
        if e.get('tie'):
            for n, p in zip(e['notes'], e['pitches']):
                out[(n['step'], n['oct'])] = p - pitch_of(n['step'], n['oct'], 0)
    return out

def build(text):
    """Read the score.  Returns (measures, order): measures is a list of
    {'num', 'alt', 'key', 'text', 'lines': {hand: events}}, order the playback order (indices)."""
    global MEASURE, BEAT
    key0, (MEASURE, BEAT), pars = read_parallels(text)
    states, measures = {}, []
    key = key0
    last_events = {}
    carried = {}
    for p in pars:
        if p['key'] is not None:
            key = p['key']
        per_line = {}
        for line in p['lines']:
            h = 'R' if line.startswith('.>') else 'L'
            v = states.setdefault(h, Voice(h))
            v.hand = h
            per_line[h] = measures_of_line(line)
        count = max(len(x) for x in per_line.values())
        alt = bool(measures) and p['num'] == measures[-1]['num']
        for k in range(count):
            m = {'num': p['num'] + k, 'alt': alt and k == 0, 'key': key, 'text': p['text'] if k == 0 else [],
                 'lines': {}}
            for h, ms in per_line.items():
                if k >= len(ms):
                    continue
                v = states[h]
                voices = measure_structure(ms[k], v)
                cadenza = any(('fermata',) in x[k] or any(u[0] == 'small' for u in x[k])
                              for x in per_line.values() if k < len(x))
                # a bar with a cadenza may still be in time; look for that reading only briefly
                ok, res = solve_measure(voices, max_depth=1 if cadenza else 5)
                if not ok and cadenza:
                    ok, res = solve_measure(voices, free=True)      # a cadenza: under a fermata, or in small notes
                if not ok:
                    raise ValueError(f'measure {m["num"]} {h}: lengths {res}')
                m['len'] = max([m.get('len', MEASURE)] + [r for r in res if r is not None])
                m.setdefault('lengths', {})[h] = max([r for r in res if r is not None], default=MEASURE)
                evs, copied = [], []
                for vi, r in enumerate(res):
                    if r is not None:
                        continue
                    # a voice that is a repeat sign: that voice of the previous measure again
                    rep = next(it for b in voices[vi] for it in b[1] if it['kind'] == 'repeat')
                    src = [copy.deepcopy(e) for e in last_events[h] if e['voice'][0] == vi]
                    if not src and vi > 0:
                        src = [copy.deepcopy(e) for e in last_events[h] if e['voice'][0] == 0]
                        for e in src:
                            e['voice'] = (vi,) + e['voice'][1:]
                    if rep['oct'] is not None:
                        first = next(e for e in src if e['kind'] == 'chord')
                        shift = 12 * (rep['oct'] - first['notes'][0]['oct'])
                        for e in src:
                            if e['kind'] == 'chord':
                                e['pitches'] = [x + shift for x in e['pitches']]
                    for e in src:
                        e['markers'] = []
                    marks = [mk for b in voices[vi] for it in b[1] for mk in it.get('markers', [])]
                    if marks:
                        src.append({'t': F(0), 'kind': 'marker', 'markers': marks, 'voice': (vi, 0, 0)})
                    copied += src
                live = [b if r is not None else [] for b, r in zip(voices, res)]
                evs = measure_events(live)
                carried[h] = resolve_pitches(evs, key_alters(key), carried.get(h, {}))
                evs += copied
                m['lines'][h] = evs
                last_events[h] = evs
            if len(set(m.get('lengths', {}).values())) > 1:   # a free bar: the hands must still agree
                raise ValueError(f'measure {m["num"]}: the hands differ in length {m["lengths"]}')
            measures.append(m)
    return measures, playback_order(measures)

def markers_of(m):
    for evs in m['lines'].values():
        for e in evs:
            for mk in e.get('markers', []):
                yield mk

def playback_order(measures):
    """Indices in performance order: each repeat taken once, the first ending the first time
    through and the second ending (a measure with 'alt' set) the second."""
    order, i, start, repeated = [], 0, 0, set()
    while i < len(measures):
        m = measures[i]
        mks = list(markers_of(m))
        if ('repeat_start',) in mks and i not in repeated:
            start = i
        if ('repeat_end',) in mks:
            if i not in repeated:
                order.append(i)
                repeated.add(i)
                i = start
            else:
                i += 1                       # the first ending, the second time through
            continue
        if m['alt'] and (i - 1) not in repeated:
            i += 1
            continue
        order.append(i)
        i += 1
    return order

# ---------------------------------------------------------------- command line

NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B']

def note_name(p):
    return NAMES[p % 12] + str(p // 12 - 1)

def main():
    import argparse
    ap = argparse.ArgumentParser(description='Print the decoded notes of a braille keyboard score, bar by bar.')
    ap.add_argument('brf')
    ap.add_argument('first', type=int, nargs='?', default=1)
    ap.add_argument('last', type=int, nargs='?', default=10 ** 6)
    a = ap.parse_args()
    measures, order = build(open(a.brf, encoding='ascii').read())
    for m in measures:
        if not a.first <= m['num'] <= a.last:
            continue
        print(f"m.{m['num']}{' (2nd ending)' if m['alt'] else ''}")
        for h in ('R', 'L'):
            evs = sorted((e for e in m['lines'].get(h, []) if e['kind'] == 'chord'),
                         key=lambda e: (e['t'], e['voice']))
            cells = []
            for e in evs:
                tag = ('g' if e['grace'] else '') + ('~' if e.get('tie') else '') + \
                      (f"[{e['hand']}]" if e['hand'] != h else '')
                cells.append(f"{float(e['t'] * 8):g}:{'/'.join(note_name(p) for p in e['pitches'])}"
                             f"({float(e.get('dur', 0) * 8):.3g}){tag}")
            marks = [mk for e in m['lines'].get(h, []) for mk in e.get('markers', [])]
            print(f'  {h}: ' + ' '.join(cells) + (f'   {marks}' if marks else ''))
    print(f'{len(measures)} measures, {len(order)} in performance order')

if __name__ == '__main__':
    main()
