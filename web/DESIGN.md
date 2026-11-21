# Frontend design notes

## What the page is for

One reader: an engineer, maybe an interviewer, who has five minutes and wants to see that the
backend does what the README says. One job: follow a single backdated raise all the way through.
The fact changes, the right results go stale, workers recompute under leases, corrections come out
of the feed. Everything on the page is read from the running backend. When it isn't connected,
it shows a recording of a real run, labelled as one.

## References looked at (2026-11-21)

- Codrops, Shopify Editions Spring '26 case study: one shared canvas behind the page, with frame
  buffers, so scenes don't each spin up their own WebGL context. Adopted: one R3F canvas per
  scene at most, and the scenes are frameloop="demand".
- Codrops, Efecto (ASCII and dithering shaders), and Paper Shaders: texture from a shader, not
  from images. Adopted for the paper grain and carbon transfer, kept subtle.
- Awwwards SOTD, AI in Design Report 2026: a report turned into an editorial page where data and
  motion share one visual language. That is the bar for the feed and numbers sections.

## Three directions

**A. Carbon copy.** Payroll offices kept corrections on carbon paper and ledger sheets. Each
knowledge version is a sheet in a stack. A fact is a rectangle on its sheet: wide as its valid
range, and present on every sheet from `tx_from` until `tx_to`. That is the textbook bitemporal
diagram, made physical. Corrections are red pen. Pending work is carbon blue. Ledger-ruled paper.

**B. Strata.** Knowledge time as sediment, valid time as the horizontal. A backdate is a fault
line through the layers. Earth tones, survey-plate type. It's pretty, but the metaphor stops at
recomputation: rock doesn't have leases.

**C. Time clock.** Punch cards and a factory time clock: valid time is when you worked, knowledge
time is when the card got punched. It's strong on the two axes, but it gets novelty-heavy once
you need a dependency graph and a feed.

**Pick: A.** It's the only one where the metaphor *is* the data model. The sheet stack is the
bitemporal plane, and red ink on a struck-through figure is a restatement. Its vocabulary (sheet,
carbon, ruling, red pen, posting) covers every section.

## Tokens

| Name | Light | Dark (carbon sheet) | Use |
|---|---|---|---|
| paper | `#EDF1E7` | `#1A2140` | page |
| ruling | `#BCCDB6` | `#33406E` | ledger lines, grid |
| graphite | `#262820` | `#DCE2F4` | text, fresh results |
| carbon | `#2B3A9C` | `#8FA2FF` | pending, in-flight, knowledge axis |
| redpen | `#C0281A` | `#FF6B5B` | changed ranges, stale, deltas |

Type: Archivo (variable, wdth 62 to 125), and nothing else. Headings use the expanded width,
dense tables use the condensed width, all figures are tabular. The width axis does the work a
second family usually would.

Layout: left-aligned on a ledger grid. A narrow left gutter column holds the knowledge version,
the way a ledger's date column does, so the numbers in the margin really are versions. The
sections run in the order a backdate happens, so numbering them is honest.

```
| v | backdate                                   [sheet stack, 3D]     |
|---|-------------------------------------------------------------------|
| 1 | Correct a salary     form + simulated months, "Post" goes live    |
| 2 | What went stale      graph: facts -> gross -> withholding         |
| 3 | Recompute            live lease table, fencing replay             |
| 4 | The feed             ledger lines, scrub by version               |
| 5 | Measured             benchmark table                              |
```

## Checked against the defaults

- Not cream with terracotta: the paper is green-ruled ledger stock, and the accent is a red-pen
  red that only ever marks a change.
- Not near-black with acid green: dark mode is carbon-paper blue, from the same metaphor.
- No eyebrows, no all-caps labels, no mono for small labels, no icon tiles, no glass, no
  fade-up-on-scroll. Motion happens once on load (the sheets settle into the stack). After that,
  things only move because data changed or the reader did something.
- I first wanted IBM Plex. I swapped it for Archivo, because the width axis lets one family
  carry both the display type and the ledger tables.
