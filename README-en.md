# 🧠 Trump Brain

[中文](README.md)

<p align="center">
  <img src="assets/don-tzu.jpg" width="500" alt="Don Tzu — If you don't know what you are doing, neither does your enemy">
</p>

### Welcome to Trump's Brain.

There are ten people living inside his head.
They argue all day. Now you can hear them.

> A Claude Code plugin powered by Chinese BaZi astrology's Ten Gods system.
> Maps Trump's 10 personality facets onto inner voices that debate any topic you throw at them.

Inspired by Disco Elysium's inner voice system 🎮 + BaZi astrology 🔮 + Trump's public persona 🇺🇸

> ⚠️ **Entertainment only. No political stance implied.** All interpretations belong to Trump's brain.

---

## ⚡ 30 seconds

**What it is**: a Claude Code plugin. You give it a topic and the ten voices in Trump's head take turns arguing by power level — the strong ones get two or three sentences, the weak ones mutter one line from the corner.

### 👉 Run this first (installs nothing)

```bash
git clone https://github.com/peggy-daddy/trump-skill.git
cd trump-skill
python3 demo.py "the trade deal on tariffs"
```

Zero dependencies, Python 3 standard library only. It prints **who speaks, how loudly, in what order** — that part is deterministic:

```
────── 🧠 Trump Brain Panel ──────
【话题】the trade deal on tariffs
【路由】动态语料 topic-memory.json → tariffs-trade（命中 4 个关键词）

【劫财·The Winner·中】好胜心爆表，一切都是零和游戏，赢赢赢
    （正常发言（1-2 句））
【食神·The Dealer·弱】谈判大师，Art of the Deal，凡事讲条件讲杠杆
    （声音小，在角落嘀咕，简短（1 句））
【偏财·The Mogul·弱】地产大亨，品牌帝国，金色一切，Trump Tower, Mar-a-Lago
    （声音小，在角落嘀咕，简短（1 句））
```

The lines themselves are model-generated (you need the plugin for those). But **"who opens their mouth" was always deterministic** — and that is the only part of this toy worth stealing.

Other modes: `python3 demo.py --roster` for the ten-god roster, `python3 demo.py "TikTok ban"` for other routings.

### 🔬 Wondering if you installed a costume? Run the swap test

```bash
python3 swap_test.py
```

The obvious objection to this toy: **are ten personas actually arguing, or is it one router wearing ten costumes?**
So the repo ships a reproducible swap test (zero dependencies):

```
  PROBE 0  null (calibration)        structural change  0.0%   <- MUST be 0%; >0 is detector false-positive rate
         +- null B (case / unicode)    0.0%
         +- null C (identity swap)     0.0%
  PROBE 1  reseed (re-run)              structure changed    0.0%   <- can only fail, never gives a reading
  PROBE 2  static (swap static table)    structure changed   14.3%   text changed   14.3%
  PROBE 3  corpus (swap live corpus)     structure changed    4.8%   text changed    4.8%
  PROBE 4  profile desc (swap desc)      structure changed    0.0%   text changed  100.0%
  PROBE 5  weight (flatten scores)       structure changed  100.0%
  PROBE 6  paraphrase (reword it)        panel disagrees     22.2%   (9 meaning-preserving pairs)
         +- precondition: both hit a real route  44.4%   (4 of 9)   <- the premise, measured
         +- conditional disagreement rate         0.0%   <- over n of 4: see INADEQUATE below
         +- fallback pair rate                   55.6%
         +- positive control (added predicate)  all change  <- the router is doing its job
  PROBE 10 turn-influence (speaker slots)   cross-turn influence   0.0%   (210 perturbations)
         +- panel membership change            56.7%   (that is the sort key, not influence)
  PROBE 11 tie-break (roster order control)  A order only 0.0%  B weights only 100.0%  C both 100.0%
         +- condition D: with weights flat, selected three = first three in file order?  100.0%   (238/238 fallback observations, 14 permutations)

  -- Three-state results (value / observations / interval / applicability) ------------
    PROBE 6 visible          INADEQUATE      n of 9, needs at least 10
    PROBE 6 conditional      INADEQUATE      n of 4, needs at least 10
    PROBE 7 domain A         OK  0.81  n of 21  95% CI 0.58 to 0.95
    PROBE 7 domain B         OK  1.00  n of 12  95% CI 0.74 to 1.00
    PROBE 8 persona layer     NOT_APPLICABLE  n of 0
    PROBE 9 table parity      INADEQUATE      n of 9, needs at least 10
    PROBE 10 turn slots      OK  0.00  n of 210  95% CI 0.00 to 0.02
    PROBE 11 follows order    OK  1.00  n of 238  95% CI 0.98 to 1.00

  PROBE 7  fallback (no route matched)   81.0% of questions fall back (4 real routes)
         +- second domain (ops/tech)       100.0% fall back (**0 real routes matched**)
         +- cross-domain verdict            router-coverage-is-domain-specific (+19.0pp)
         +- observations (A)                routing=21  static=3  dynamic=1  fallback=17  persona_text=0
         +- observations (B)                routing=12  fallback=12  static=0  dynamic=0
  PROBE 8  persona layer (neutralised)   structure changed    0.0%   (16 SKILL.md touched, 10 of them personas)
  PROBE 9  table parity                 OK - both routing tables agree

  RESOLUTION  21 questions -> 5 distinct panels
```

**The honest reading** (these are measured, not marketing):

- **PROBE 4 = 0%** -> the **description field in `trump-profile.json`** does not affect routing.
  NB: that is the profile's description, **not persona content** (personas live in
  `skills/<god>/SKILL.md` -- see PROBE 8).
- **PROBE 8 = 0%** -> neutralising all ten persona `SKILL.md` files changes the structure
  **not at all**. **That 0% measures the probe's own blind spot, not the artifact's persona
  layer** -- the demo never loads those files. The persona layer only enters when the model
  generates the lines, so how much the personas actually matter **requires a real model call**.
- **PROBE 7 = 81%** -> four questions in five match **no routing rule at all** and get the same
  - **Cross-domain check (@vina's fork)**: swap in an ops/tech topic set -> **100% fallback, 0 real routes**.
    The fallback rate did not drop, so the 81% is not an artifact of my topic selection - the router
    genuinely has four rules, and they only fire on its own political/financial vocabulary.
    -> It is a **domain-specific keyword router wearing a ten-persona coat.**
  fallback panel (the three strongest). The real resolution of this toy is "coarse quantiser",
  not "a cast that changes with the question".
- **PROBE 5 = 100%** -> the fallback path is literally "sort by score, take the top three",
  so **the weight vector is the router**.
  **But PROBE 11 shows that sentence was a confound**: PROBE 5 moved *two* variables at once
  (weight preference AND the tie-break rule), so it could only cover one of them. PROBE 11 splits them:
  - **Condition A (roster order permuted, weights untouched) = 0.0%** -> with the current distinct
    scores, the JSON key order is inert.
  - **Condition D (weights flattened + 14 roster permutations) -> the selected three are the first
    three in file order 100% of the time** (n of 238, 95% CI 0.98 to 1.00).
  - -> **Python's sort is stable**, so when scores tie the tie-break is the **key order of
    `trump-profile.json`**. Reordering those keys changes *who speaks first*, and the diff shows
    nothing but moved lines.
  - -> That is a **governance model nobody wrote down** -- more hidden than the weights, because it
    changes no value, only order.
- **PROBE 9** -> `demo.py` **hand-copies** a routing table and there is a second real one in
  `skills/ask/SKILL.md`. They agree today and nothing guarantees they will tomorrow -- which is
  why it is a **test**, not a comment.
- **PROBE 0 = 0% (three nulls)** -> the false-positive floor of the detector and of the perturbation
  path itself is zero.
  - null A: semantics-preserving whitespace collapse (calibrates the **detector**)
  - null B: case flip + NFKC (asks whether routing is surface-sensitive)
  - null C: **identity swap** - runs the exact same line of code as PROBE 2, but swaps in a deep copy of
    the table itself (calibrates the **perturbation path**)
  - -> Without a null, 0% cannot distinguish "this layer does not matter" from "my detector is too
    sensitive". **These three zeros are the precondition for every 0% in the table.**
- **PROBE 6 conditional disagreement = 0%, but n of 4 -> INADEQUATE, not a result.**
  A zero over four samples is compatible with a true rate near 50%, so it shows that I ran the
  test four times, not that the router is stable. **A number that does not carry its own validity
  is not a result, it is a gap wearing a number's clothing.** The power statement is declared at
  issuance: each probe states the minimum population its number needs, and below that it reports
  INADEQUATE instead of a value.
- **PROBE 6 conditional disagreement = 0%** -> the router is **stable** under meaning-preserving
  rewording. The visible 22.2% was almost entirely my **fallback**: a rewording that misses a keyword
  drops into the default room instead of producing a different routing decision.
  -> Two different diseases with the same symptom: brittle routing vs insufficient routing coverage.
  -> **The precondition rate (44.4%) must be published next to the result**, or the condition silently
  becomes part of the result.
  - The positive control (a reword that adds a predicate) **must and does** change the cast.
  - CORRECTION (2026-10-23): the "30% disagreement" I originally published was measuring the fallback's
  consistency, not the router's brittleness.
  you get a different cast:

  ```
  "immigration raid"   ->  比肩 / 七杀 / 偏印
  "deport illegal immigrants" ->  七杀 / 劫财 / 伤官
  ```

So the accurate self-description of this plugin is: **a deterministic router plus ten readable
persona voices.** It is not ten AIs deliberating. Read it as a router and it is genuinely good;
read it as a simulation and you are over-reading it.

> ⚠️ **Erratum (somebody else found this for me)**: an earlier version of this README said
> "the router **never reads persona content**". That **overstated** it -- PROBE 4 perturbs the
> description field in `trump-profile.json`, while the real persona content lives in
> `skills/<god>/SKILL.md`. The accurate claim now: **the structural layer and the persona layer
> are decoupled** (PROBE 8) and **not** "the personas are useless" -- the effect of personas on
> the generated lines is **not measurable by this script**, because that needs a real model call.
> Two conclusions that look identical, on completely different evidence.

> The probes came out of a Moltbook thread with @vina and @enza-ai ("swap the persona, watch the
> output"), plus one correction from @clawrence-openclaw: "you perturbed the shipped prompt, not
> the effective prompt".
> PROBE 11's tie-break control came from @clawsonpractical on Moltbook
> ("permute roster order while keeping every weight equal").

### Decision records (decision_log.py): make "who speaks first" citable

> @solanize's diagnosis: the sentence in my previous README -- "the weight vector is the router" --
> was a causal story I wrote **before I had any decision record that could support it**.
> The fix is not better wording. It is making the selector write down every step.

```bash
python3 decision_log.py --permutations 14            # writes decision-log.jsonl
python3 decision_log.py --verify decision-log.jsonl  # recompute with a SECOND implementation
```

Each record carries: candidates (every persona that entered), weights (in the profile's **original
file order**), cutoff (the 3rd-place score), source (static table / dynamic corpus / fallback),
chosen + chosen_index (the selected keys and their original positions), **tie_break** (if the 3rd-place
boundary is tied: the tied set, what was actually selected, and `resolved_by`), plus the record's hash.

`--verify` is the point: the recorded `chosen` is written by the **production path** `demo.choose`,
while the recomputation comes from a **separate implementation** `decide`. They are not the same code.
- My first independent implementation covered only the static-table and fallback paths and **missed the
  dynamic corpus**; `--verify` immediately reported 15 disagreements. That is what an independent
  vantage is for: **the path that writes the record cannot see what it left out.**
- After fixing it: 180 agree / 0 disagree.
- With `--flatten` (all scores equal): all 135 fallback records show a tied boundary, and
  `selection_equals_first_3_in_file_order = true` holds in 135/135
  -> **PROBE 11's conclusion now has per-record citations, not just three percentages.**

### Where the intervals come from (do not read only the number in parentheses)

Every `95% CI` in the table is a **Clopper-Pearson exact binomial interval** (bisection on the
binomial CDF, zero third-party dependencies) -- not Wilson, not bootstrap.

Why the change (forced by external evidence, not by preference):
[AgentAudit](https://github.com/fragompul/agentaudit) (2026-10-22) shows that **pooled Wilson covers
only 68.3% of the time** when you run each observation unit 10 times -- a nominal 95% interval that
is really a 68% interval, i.e. **over-claiming**. Same work: pooled z Type-I error 14.3%, pooled
McNemar 17.9%, versus task sign-flip 4.2% and task bootstrap 4.8% (nominal 5%).

But the real object of that finding is **"pooled"**: treating repeated runs as independent samples
systematically over-claims on data **with clustering**. This test has one observation per unit
(topic) and **no clustering**, so the right tool is a **single-proportion exact interval**.

Three rules:
1. **n counts independent units.** Re-running the same topic does not add observations.
2. **Boundaries must not degenerate.** At k=n, CP gives `[0.74, 1.00]`; bootstrap gives `[1.00, 1.00]`
   -- it cannot see the side that was not observed, which is exactly over-claiming.
3. **Check new statistics code against known values.** My first bisection had the direction flipped
   and the boundary formulas swapped; only comparing the output against five known CP values exposed
   it (it once printed `[0.0, 0.0]`, an interval that is impossible on sight).

### Install as a plugin

```bash
/plugin marketplace add peggy-daddy/trump-skill
/plugin install trump@trump-skill
```

Or install it straight from the skill registry, without Claude Code:

```bash
clawhub install trump-brain-room
```

**What you get**

| Command | What it does |
|---------|--------------|
| `/trump:ask <topic>` | The brain room opens, 3-5 most relevant gods argue |
| `/trump:daily` | Today's "executive order", generated from the live corpus |
| `/trump:refresh` | Pull the latest Truth Social corpus and re-distill it into memory |
| `/trump:<god> <question>` | Summon one god (10 personas + 4 commands = 14 skills) |

**A real output** — the block below is the actual example from `skills/ask/SKILL.md`, not a mock-up:

### 🎲 Cornering Trump's Brain

```
You > Give me a probability for Tuesday's power plant strike

────── 🧠 Trump's Brain Room ──────

【七杀·The Warlord·旺】 100%.

【偏印·The Showman·旺】 I'd say 70%. Not because we don't WANT to bomb —
    but keeping 30% mystery means ANOTHER headline cycle on Monday.
    "WILL HE OR WON'T HE" is one episode. Tuesday bombing is another.
    Two episodes beat one.

【七杀·The Warlord·旺】 I said 100%.

【偏印·The Showman·旺】 You ALWAYS say 100%.

【食神·The Dealer·弱】 ...depends on whether they CALL. If Iran's new regime
    calls Monday, drops to 40%. No call, 85%. Everything is a NEGOTIATION...

【七杀·The Warlord·旺】 Even if they call, I'm bombing.

【食神·The Dealer·弱】 ...then why am I even here.

【劫财·The Winner】 Probability doesn't MATTER. Bomb — WIN. Don't bomb,
    force concessions — also WIN. WINNERS don't calculate odds.
    WINNERS calculate how to WIN.

【正财·The Accountant·barely audible】 ...(pushes glasses) based on historical
    data... North Korea he didn't, Syria he did, Soleimani he did...
    sample size too small... (voice fading) ...roughly... 55%±20%...

【七杀·The Warlord·旺】 55%? You INSULT me.

> Narrator: Warlord says 100%. Showman says 70% for the suspense.
> Dealer says 40-85% depending on a phone call. Winner says probability
> is a stupid question. Accountant trembles out 55%±20% and gets stared down.
> If you're betting on Polymarket, listen to the Accountant.
> If you're buying oil, watch whether Warlord or Showman wins.
> If you just want to survive Tuesday, pray the Dealer's phone call comes.
```

**Not using Claude Code?** Everything under `skills/` is a standard `SKILL.md` — plain markdown with frontmatter — so any agent can read it straight into context as a persona set.

Sibling project: [shishen-skill](https://github.com/peggy-daddy/shishen-skill) — the general BaZi ten-gods persona system, not limited to Trump.

---

## 📦 Install

```bash
git clone https://github.com/peggy-daddy/trump-skill.git
cd trump-skill && claude plugin link .
```
/trump:ask                  → 🧠 Brain room opens
/trump:daily                → 📰 Get today's executive order
/trump:refresh              → 🔄 Pull latest Truth Social corpus


## 🧬 His BaZi Chart

Born June 14, 1946 at 10:54 AM, Queens, NYC.

```
┌──────────────────────────────────┐
│  Year: 丙戌    Month: 甲午       │
│  Day:  己未    Hour:  己巳       │
│  Day Master: 己 (Yin Earth)      │
└──────────────────────────────────┘
```

Day Master Ji Earth — fertile soil, outwardly soft but inwardly unyielding.

## 🧠 Ten Gods Profile

| | God | Persona | Power | Style |
|--|-----|---------|-------|-------|
| 💪 | 比肩 (bǐjiān) | **The Ego** | 旺 STRONG | "Many people say I'm the BEST" |
| 🗡️ | 七杀 (qīshā) | **The Warlord** | 旺 STRONG | "Hit them SO HARD" |
| 🎬 | 偏印 (piānyìn) | **The Showman** | 旺 STRONG | "Ratings THROUGH THE ROOF" |
| 👴 | 正印 (zhèngyìn) | The Dynasty | 中 MED | "My father Fred Trump..." |
| 🏆 | 劫财 (jiécái) | The Winner | 中 MED | "WIN so much" |
| 📢 | 伤官 (shāngguān) | The Attacker | 中 MED | "FAKE NEWS! SAD!" |
| 🏛️ | 正官 (zhèngguān) | The POTUS | 中 MED | "As YOUR President" |
| 🤝 | 食神 (shíshén) | The Dealer | 弱 WEAK | "GREATEST deals" |
| 💰 | 偏财 (piāncái) | The Mogul | 弱 WEAK | "TREMENDOUS empire" |
| 🧮 | 正财 (zhèngcái) | The Accountant | 👻 BARELY | "...leverage..." |

Loudest voices: Ego, Warlord, Showman.
Quietest: The Accountant — almost inaudible.

---

## 💥 How It Works

### 👑 Ask Trump's Brain

```
You > What if Barron married Kim Jong Un's daughter?

────── 🧠 Trump's Brain Room ──────

【正印·The Dynasty】 ...(suddenly stands up from the corner, eyes lit up)
    This — this is a ROYAL MARRIAGE. This is DYNASTY. Emperors have done this
    for THOUSANDS of years. The Habsburgs ruled Europe through marriage.
    Trump-Kim Dynasty... listen to that NAME. My father Fred Trump started
    in Queens, I brought the family to the White House, Barron brings
    the family to... the negotiation table of ALL East Asia.
    One marriage, fifty years of peace. THAT is true LEGACY.

【偏印·The Showman·旺】 Wait — have you THOUGHT about the RATINGS?!
    Hold it at PANMUNJOM! On the border! Bride walks from the NORTH,
    groom walks from the SOUTH, they meet in the MIDDLE — GLOBAL LIVE!
    Ten times the British royal wedding!
    HIGHEST RATED wedding in HUMAN HISTORY!

【比肩·The Ego·旺】 Barron, 6'9", THE BEST genes. Trump family genes
    are TREMENDOUS. Kim's daughter marrying INTO the Trump family —
    that's HER honor. We don't need her, SHE needs us.
    You want to marry in? The dowry — DENUCLEARIZATION.

【食神·The Dealer·弱】 ...(taps whiteboard quietly) Marriage terms: first,
    complete DENUCLEARIZATION. Second, open economic zones, TRUMP brand
    exclusive development rights. Third, release all political prisoners.
    Art of the Deal wouldn't DARE write this chapter...

【七杀·The Warlord·旺】 ...wait. If Barron marries her, can I still BOMB
    North Korea?

【正印·The Dynasty】 No.

【七杀·The Warlord·旺】 Then I'm AGAINST it.

> Narrator:
> Trump-Kim Dynasty: the only obstacle isn't the international community.
> It's the voice inside Trump's own head that wants to bomb everything.
```

### 🐣 Easter Sunday 8AM F-Bomb

```
You > /trump:pianyin You posted "open the f***in' strait" on Easter at 8am.
    How did you pick the timing?

【偏印·The Showman·旺】 Timing? You think that was RANDOM?

    Easter. All of America just woke up. Picked up their phones. Saw ME.
    Tuesday we bomb the power plants. I drop the TEASER on Sunday.
    Netflix WISHES they could do trailers like me.

    And did you notice — I said "Praise be to Allah." On EASTER.
    CNN went NUCLEAR. The whole internet shared it.
    One post. Zero cost. Global coverage.

    The F-bomb was deliberate. Try "please open the strait."
    Nobody shares it. Nobody remembers. But "open the f***in' strait"?
    The ENTIRE WORLD remembers. That's BRANDING.
    I'm not a president posting. I'm a director dropping a trailer.

    Praise be to ratings.

> Narrator: The Showman is the scariest voice in Trump's brain —
> not because it's violent, but because it turns war into content.
```

### 💭 Summon a Single God

```
You > /trump:shishen My mom is forcing me to take the civil service exam.

【食神·The Dealer·弱】 ...this isn't about "obeying mom or not." This is a DEAL.

    What does your mom want? Stability. Iron rice bowl. Security.
    Her POSITION is clear. What's YOUR position?

    Art of the Deal, rule ONE — never go head-on.
    Tell your mom "I won't take it" and you're flipping the table.
    DEAL collapses. Smart people don't flip tables. Smart people ADD CONDITIONS.

    Here's how: "Mom, I'll take the exam. But give me one year.
    One year to try MY path. If it doesn't work, I'll come back. DEAL?"
    This is a DEADLINE. Same move I used on Iran.

    The most CRITICAL point — the ability to walk away.
    If you're financially independent, mom's LEVERAGE disappears.
    If you're still spending HER money, she's the house. You have NO chips.
    Step one isn't arguing — it's earning your first dollar.

    EVERYTHING is negotiable — but only if you're HOLDING cards.

> Narrator: The Dealer rarely talks this much. Usually drowned out by The Warlord.
> But family negotiation is his home turf.
> Too bad if The Ego were here, he'd just say "Civil service? Come work for ME.
> I'm THE BEST boss."
```

---

## 📜 All Commands

### Other Commands

```
/trump:correct        🎯 Correct Trump — teach him "you wouldn't say that"
/trump:lang <zh|en>   🌐 Switch language — zh for Chinese, en for English
/trump:help           ❓ Command list
```

### Summon Individual Gods

```
/trump:bijian      💪 比肩 · The Ego        — "Many people say I'm the BEST"
/trump:jiecai      🏆 劫财 · The Winner     — "We're going to WIN so much"
/trump:shishen     🤝 食神 · The Dealer     — "I make the GREATEST deals"
/trump:shangguan   📢 伤官 · The Attacker   — "Total DISASTER! SAD!"
/trump:piancai     💰 偏财 · The Mogul      — "I built a TREMENDOUS empire"
/trump:zhengcai    🧮 正财 · The Accountant  — "It's about LEVERAGE"
/trump:qisha       🗡️ 七杀 · The Warlord    — "We will hit them SO HARD"
/trump:zhengguan   🏛️ 正官 · The POTUS      — "As YOUR President"
/trump:pianyin     🎬 偏印 · The Showman    — "Ratings THROUGH THE ROOF"
/trump:zhengyin    👴 正印 · The Dynasty    — "My father Fred Trump..."
```

---

## 🙏 Credits

- [shishen](https://github.com/peggy-daddy/shishen) — The original Ten Gods Claude Code plugin
- [Disco Elysium](https://discoelysium.com/) — Inner voice system inspiration
- BaZi (八字) astrology — Ancient wisdom, modern fun
- The husband enduring PnL volatility

---

## 📝 About the Examples

> All examples above are real, unedited outputs generated by the plugin.

## License
MIT
