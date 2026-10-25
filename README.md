# Liszt: Un sospiro (Trois études de concert, S.144 No. 3)

An expressive MIDI performance, decoded from a braille transcription of the score. The
braille was made for this project from Ferruccio Busoni's edition for the Franz Liszt
Foundation (Leipzig: Breitkopf & Härtel, 1911).

| File | What it is |
|---|---|
| `sospiro.brf` | The score in North American ASCII music braille, bar-over-bar, 40 cells to the line: a new transcription of the Busoni edition ([IMSLP #55307](https://imslp.org/wiki/3_%C3%89tudes_de_concert,_S.144_(Liszt,_Franz))), checked against the Kistner first edition of 1849 (IMSLP #14111) |
| `brf.py` | Reads the braille into timed notes (the subset of the BANA Music Braille Code the file uses); prints the decoded notes bar by bar |
| `perform.py` | Turns the notes into the performance: tempo, rubato, dynamics, voicing, articulation, pedal |
| `render.swift` | Plays a MIDI file through the macOS sampler, offline, into an `.m4a` |
| `liszt-un-sospiro.mid` | The performance |
| `liszt-un-sospiro.m4a` | The performance as audio |
| `LICENSE-MIT` | The MIT license, for the code |
| `LICENSE-CC-BY-SA-4.0` | Creative Commons Attribution-ShareAlike 4.0 International, for the braille, the performances and the rest |

The Python needs only the standard library (3.11 or later); `render.swift` needs macOS and
Swift (the Xcode command-line tools).

```
python3 perform.py sospiro.brf -o liszt-un-sospiro.mid
swift render.swift liszt-un-sospiro.mid liszt-un-sospiro.m4a
python3 brf.py sospiro.brf 53 56      # the decoded notes of bars 53-56
```

`perform.py --report` prints the tempo, loudness and markings of every bar; `--tempo` sets the
quarter-note tempo (72), and `--rubato` scales how much the tempo gives and takes (1).

## Listening

For a better piano, open the `.mid` in GarageBand: **File › Open**, or drag it into an empty
project. When GarageBand asks *Also import tempo information?*, click **Import Tempo**: the
rubato lives in the tempo map, and without it the piece plays metronomically. If the track
does not come up as a piano, pick **Piano › Steinway Grand Piano** in the Library. Bars and
key changes line up with the score; the five cadenza bars carry time signatures of their own
length.

## The braille

No braille edition of *Un sospiro* is freely available: IMSLP has none, and Hu Haipeng's
Braille Orchestra and Open Braille Music catalogue, the source of the Tarantelle that started
this, has some thirty Liszt works but not this one. So the score was transcribed here, bar by
bar, from the 600 dpi scan: note heads were located against the staff lines by image analysis,
and accidentals, rhythms and markings read from close crops, with doubtful places compared
with the first edition. The decoder then checks every bar: each voice of each hand has to fill
the 4/4 measure exactly, and in the five free bars both hands have to come out the same length.

The transcriber's notes at the head of the file give the conventions:

- The right-hand part carries the upper staff and the melody, the left-hand part the staves
  below it. Arpeggios that the print divides between the hands are written in the left-hand
  part, with hand signs where the right hand takes over.
- The print's unnumbered groups are written as tuplets of their size: 14 sixteenths to the half
  bar in the opening arpeggios, 12 to 18 thirty-seconds in the coda's, six sixteenths to the
  beat in the *Un poco più mosso*. The three thirty-seconds before a dotted eighth in the
  *quasi arpa* bar are written in the time of two, the only reading in which the beat adds up.
- Bars 29, 37, 52, 61 and 70 hold cadenzas or fermatas and run longer than the measure. Their
  small notes are marked as such, and a music comma ends a group of short notes before a longer
  one.
- Passages marked *8va* are written at pitch. Slurs over the arpeggios and fingerings are left
  out.

Both editions agree on two places that look like misprints and are kept: in bars 46–48 the
left hand's G♯ dominant seventh has B♯ while the right hand's chord has B♮, and in bar 60 a
diminished seventh (C♭ D♮ F A♭) sounds over a G♭ pedal.

`brf.py` began as the Tarantelle's decoder and was generalized for this score: the time
signature comes from the title page, tuplets of any size take their span from the measure,
groups of thirty-seconds and passages of small notes are read, a bar with a cadenza may run
long, the music comma breaks a group, and among the readings that fill a measure it prefers
the one closest to the likeliest note values, breaking up a group of short notes only as a last
resort.

## The performance

Everything beyond the notes is an interpretation layered over the score's own markings:

- **Tempo**: *Allegro affettuoso* at ♩ = 72, with a little weight on beat one and on the half
  bar. The rubato is wide, as the piece asks:
  - **Phrases**: each of the 31 phrases settles in, presses on by up to about 9% through its
    middle and gives by up to about 30% at its close, so the opening's phrases move between
    roughly ♩ = 57 and 85.
  - **Hairpins** move the tempo too: on into a crescendo, relaxing through a diminuendo.
  - **Look-ahead**: the tempo anticipates what is coming. It presses on through the last two
    bars before a louder or faster arrival, such as the *f* of bar 27 and the *ff* of bar 30,
    with a breath just before it. It broadens over the last half bar into a softer or slower
    section, a key change or a section end, the more the bigger the change, and it eases over
    the beat before a fermata.
  - **Grace notes in the melody** (bars 11, 24 and 26) are moments to linger. The tempo gives
    over the beat before one and stays held back through the rest of its bar (for a grace on the
    downbeat, through its long note), then relaxes over half a bar; after it, the phrase no
    longer presses on but breathes out to its close. So bar 11 eases to about ♩ = 50 from its
    grace to the bar line, and bar 12 recovers gently before its own cadence. In the
    *affrettando* (bar 26) the give is slight.
  - **Tempo words**: *rit.* and *smorz.* slow. A slowing is prepared: it begins half a bar
    before its word and eases in, and two slowing words on one note count once, so bar 21
    winds down through its last two beats into the fermata instead of stopping short. *In tempo*
    returns, *affrettando* presses about
    18% into the *agitato* and the *impetuoso* climax, *acceler.* runs into the *Presto* cadenza
    of bar 37, which then *dimin. e rallent.*, *languendo* gives for a moment, and
    *leggierissimo volante* and its *acceler.* lighten and quicken. The *velocissimo* cadenza
    of bar 52 flies, and the unmarked runs of bars 29 and 61 move on once past their measured
    beats. *Un poco più mosso* is about 15% faster, *poco a poco rallentando* slows into the
    *più lento*, and the last line broadens further.
  - **Fermatas** are held about twice their length, a long final note about one and a half
    times. However the effects compound, outside a fermata the music never slows past 35%
    more than its tempo words call for.
- **Dynamics**: the printed levels (*p*, *f*, *ff*, *ppp*, *pp*), *cresc.*, *più cresc.*,
  *con forza* and *dimin.* (ramping to the next printed level), and hairpins as swells. Where
  the print gives no level, the coda's melody in chords enters *mp* and the *più lento* is *p*.
  *Sotto voce*, *languendo*, *leggierissimo* and *velocissimo* are softer, *impetuoso*,
  *con forza* and *marcato* louder.
- **Voicing**: the melody sings over the figuration, whether it is the opening's single notes
  passed between the hands, the octaves of the climax, the stemmed thumb notes and accented
  left-hand notes of the *più mosso*, or the coda's chords. The arpeggios and runs recede,
  the left hand's most, and swell a little toward their peaks; the top of each right-hand chord
  leads, inner notes recede, and the bass is firm. A bass note held under the left hand's
  arpeggio (the low C, A and B-flat of bars 9 and 10) stays close to the arpeggio's level, and a
  note that is both the arpeggio's first and the held bass is struck once.
- **Chords**: no chord lands all at once. Each hand places its chord separately, and within a
  hand the notes fan out, mostly from the bottom up, over about 10 ms for an octave to 20–40 ms
  for a big chord, wider the more notes and the wider the stretch, with the melody note leading
  in the right hand and the bass in the left. Printed arpeggios roll from the bottom.
- **Touch**: legato throughout, with staccato short and the *non legato egualmente* figuration
  a little detached.
- **Pedal**: *sempre pedale*. The pedal is down from the first note and changes, just after the
  beat, wherever the harmony moves, judged by how little a beat's notes have in common with the
  beat before: an arpeggio climbing through one chord keeps its bass, a chromatic run is
  cleared beat by beat.
- **Ornaments**: grace notes come just before the beat, a melody grace unhurried and held into
  its note; in the *quasi arpa* bar the left hand's runs of graces roll up from the bass like a
  harp, with the pedal changed ahead of them.
- **Variation**: the timing wanders slowly by a few milliseconds, and velocities and releases
  vary a little from note to note. The randomness is seeded, so every build is the same.
- 76 bars, about 4¾ minutes.

## License

The code (`brf.py`, `perform.py`, `render.swift`) is under the [MIT license](LICENSE-MIT).

The braille transcription in `sospiro.brf`, the MIDI and audio performances, and the rest of
the repository (this README included) are shared under the Creative Commons
Attribution-ShareAlike 4.0 license: [CC BY-SA 4.0](LICENSE-CC-BY-SA-4.0). Liszt's music and
the Busoni (1911) and Kistner (1849) prints the transcription follows are in the public domain.
