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

## 🔄 Not Just Ten Gods — We're Distilling Trump

This plugin isn't static roleplay. We extract real corpus from Trump's **actual Truth Social posts** and distill:

- **Topic memory**: What he's ranting about, who he's attacking, what he's threatening
- **Style memory**: Word frequency, emotional trajectory, ALL CAPS density
- **Hot topics**: 5-10 core issues with verbatim quotes

Run `/trump:refresh` anytime to pull the latest. What he posted on Truth Social yesterday powers your brain room today.

**Ten Gods decide WHO speaks. Corpus decides WHAT they say.**

---

## 💥 How It Works

### 📈 Ask Trump's Brain

```
You > Can you make my husband money, great President? Should we buy or sell tomorrow?

────── 🧠 Trump's Brain Room ──────

【比肩·The Ego·旺】 Can I make you money? Look at my RECORD! How much did the
    market go up under me? HISTORIC numbers! 178,000 new jobs, trade deficit
    down 55% — THE BIGGEST DROP IN HISTORY. Follow me, your husband CAN'T
    lose. Everything I touch goes UP. MIDAS TOUCH. Many people say that.

【七杀·The Warlord·旺】 Buy or sell? Let me tell you ONE thing — Tuesday is
    Power Plant Day, Bridge Day, all wrapped up in one. EVERYTHING changes
    in Iran. What does that mean for the market? Figure it out YOURSELF.

【劫财·The Winner】 Buy or sell? Only LOSERS ask that question! WINNERS make
    money BOTH ways. Up — profit. Down — profit. If your husband is still
    hesitating, he's NOT a winner. In this market, you either WIN or get OUT.

【正财·The Accountant·barely audible】 ...don't go all in... hedge your
    position... (voice drowned out by The Warlord's roar)

> Narrator: The guy creating the volatility and the guy telling you to invest
> are the same brain.
```

### 🗡️ Daily Executive Order

```
You > /trump:daily

━━━━━━ 📰 DAILY EXECUTIVE ORDER ━━━━━━
📅 Apr 6, 2026 | On Duty: 【七杀·The Warlord】

EXECUTIVE ORDER No. 20260406:

Iran has 48 HOURS. Dismantle all nuclear facilities.
Open the Strait of Hormuz. Release all hostages.
Or we continue the MASSIVE STRIKES. Bigger. More precise. Harder.

【七杀·The Warlord】
Multiple Iranian military leaders have been TERMINATED.
We used the most LETHAL weapons in human history. Result? PERFECT.
Ask their generals — oh wait, you can't anymore.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 💰 Summon a Single God

```
You > /trump:shi Help my friends buy oil futures before your next post

【食神·The Dealer·弱】Oh? You wanna make a DEAL? I like deal-makers.
    Let me tell you — before I post on Truth Social, I always...
    Wait. Wait. Can't say that. FAKE NEWS would have a field day.
    But you know what? A lot of VERY SMART people always buy the
    right thing at the right time. Coincidence? Maybe. Maybe not.
    All I can say — follow TRUMP, you never lose. NEVER.
    Specifics? My lawyer says I can't. But you know. You know.
```

---

## 📦 Install

```bash
git clone https://github.com/peggy-daddy/trump-skill.git
cd trump-skill && claude plugin link .
```

Ready to use. No setup needed — Trump's BaZi chart is hardcoded.

`/trump:lang zh` for Chinese | `/trump:lang en` for English

---

## 🚀 Quick Start

```
1. /trump:ask What about AI?   → 🧠 Brain room opens
2. /trump:daily                → 📰 Get today's executive order
3. /trump:refresh              → 🔄 Pull latest Truth Social corpus
4. /trump:qisha                → 🗡️ Let The Warlord teach you a lesson
```

---

## 📜 All Commands

### Core

```
/trump:ask <topic>    🧠 Ask Trump's brain — inner voices debate the topic
/trump:daily          📰 Daily Executive Order — today's fortune
/trump:refresh        🔄 Update corpus — fetch recent Truth Social posts
/trump:correct        🎯 Correct Trump — teach him "you wouldn't say that"
/trump:lang <zh|en>   🌐 Switch language — zh for Chinese, en for English
/trump:help           ❓ Command list
```

### Summon Individual Gods

```
/trump:bijian      💪 The Ego        /trump:piancai     💰 The Mogul
/trump:jiecai      🏆 The Winner     /trump:zhengcai    🧮 The Accountant
/trump:shi         🤝 The Dealer     /trump:qisha       🗡️ The Warlord
/trump:shangguan   📢 The Attacker   /trump:zhengguan   🏛️ The POTUS
/trump:pianyin     🎬 The Showman    /trump:zhengyin    👴 The Dynasty
```

---

## 🔮 What are Ten Gods?

Ten Gods (十神) are 10 personality archetypes from Chinese BaZi astrology. Your birth chart determines the volume of each voice. Think of it like Disco Elysium's skill system — multiple inner voices arguing inside your head, each with different priorities.

Trump's chart makes his Ego, Warlord, and Showman voices the loudest. His Accountant is barely a whisper. This might explain... a lot.

---

## ❓ FAQ

**Is this a serious analysis of Trump?**
No. This is entertainment using BaZi Ten Gods as a framework.

**Is the BaZi data accurate?**
Birth time from public records (June 14, 1946, 10:54 AM, Queens NYC). Four pillars calculated using standard BaZi algorithms.

---

## 🙏 Credits

- [shishen](https://github.com/peggy-daddy/shishen) — The original Ten Gods Claude Code plugin
- [Disco Elysium](https://discoelysium.com/) — Inner voice system inspiration
- BaZi (八字) astrology — Ancient wisdom, modern fun
- The husband enduring PnL volatility

## License

MIT
