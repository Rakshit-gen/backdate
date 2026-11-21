# Frontend design notes

## What the page is for

One reader: an engineer, maybe an interviewer, who has five minutes and wants to see that the
backend does what the README says. One job: follow a single backdated raise all the way through.
The fact changes, the right results go stale, workers recompute under leases, corrections come out
of the feed. Everything on the site is read from the running backend. When it isn't connected,
it shows a recording of a real run, labelled as one.

It started as one long page and is now six, one per step, because each step needed room for
its own table or chart.

## References looked at (2026-11-21)

- Codrops, Shopify Editions Spring '26 case study: one shared canvas behind the page, with frame
  buffers, so scenes don't each spin up their own WebGL context. Adopted: one R3F canvas per
  scene at most, and the scenes are frameloop="demand".
- Codrops, Efecto (ASCII and dithering shaders), and Paper Shaders: texture from a shader, not
  from images. Tried for paper grain, then dropped (see below).
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

**Pick: A.** It's the only one where the metaphor _is_ the data model. The sheet stack is the
bitemporal plane, and red ink on a struck-through figure is a restatement. Its vocabulary (sheet,
carbon, ruling, red pen, posting) covers every section.

## What changed after the first build

The first version put a 3D stack of sheets in the hero, with shader grain and ledger rules across
the whole page. On screen it failed: the stack was small and tilted, the grain read as JPEG noise,
red and blue on white looked like a flag, and the rules ran through the text. What survived is
the idea, drawn flat:

- The bitemporal diagram is an SVG on the home page. Valid time across, versions down, hatched
  rows for what a later write replaced, red for corrections. Dragging down it reads the facts as
  known at that version.
- WebGL is used once, for the invalidation graph, where it earns its place: every line and node
  carries the time the correction reaches it, so one GSAP tween of a single uniform animates the
  whole graph. Nodes are real buttons laid over the canvas.
- The page background is plain. Ruling only appears inside tables.

## Tokens

| Name     | Light     | Dark (carbon sheet) | Use                                   |
| -------- | --------- | ------------------- | ------------------------------------- |
| paper    | `#EDF1E7` | `#161C36`           | page                                  |
| sheet    | `#F6F8F2` | `#1D2443`           | charts, inputs                        |
| ruling   | `#C9D6C3` | `#313C66`           | table rules, grid, untouched edges    |
| graphite | `#262820` | `#DCE2F4`           | text, fresh results                   |
| carbon   | `#2B3A9C` | `#9AABFF`           | live state, selection, links on hover |
| redpen   | `#C0281A` | `#FF7A6B`           | changed ranges, stale, differences    |

Type: Archivo (variable, wdth 62 to 125), and nothing else. Headings use the expanded width,
small table headers the condensed width, all figures are tabular.

## Pages

| Page         | Shows                                                                             | Data                         |
| ------------ | --------------------------------------------------------------------------------- | ---------------------------- |
| Home         | salary as the database knew it at each version; the last correction in four steps | live or recording            |
| Payroll      | a raise simulated month by month, checked against stored results, then posted     | live, simulation labelled    |
| Invalidation | read sets as a graph; which results went stale and why                            | live or recording            |
| Workers      | results per month with lease tokens; a step-through of the fencing test           | live; the replay is labelled |
| Feed         | corrections per version; summed differences checked against stored results        | live or recording            |
| Benchmarks   | numbers from `docs/benchmarks.md`                                                 | recorded, says so            |

## Motion

One orchestrated moment: the red travelling through the invalidation graph, which replays on
request. Everything else moves only because data changed (a worker cell flashes when its status
or seq changes) or the reader did something. With reduced motion the graph shows its final state.

## Checked against the defaults

- Not cream with terracotta: the paper is green-tinted ledger stock, and the accent is a red-pen
  red that only ever marks a change.
- Not near-black with acid green: dark mode is carbon-paper blue, from the same metaphor.
- No eyebrows, no all-caps labels, no mono for small labels, no icon tiles, no glass, no
  fade-up-on-scroll, no pill badges.
- I first wanted IBM Plex. I swapped it for Archivo, because the width axis lets one family
  carry both the display type and the tables.
