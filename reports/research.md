# What predicts against the spread — research notes (2026-10-12)

Goal: decide which factors are worth testing in our walk-forward backtest.
Each item is a hypothesis to test, not a rule to adopt. A factor only enters the
model if it improves out-of-sample results across many weeks (CLAUDE.md).

## What the evidence says

1. **Closing lines are close to efficient.** Academic work finds the NFL closing
   spread hard to beat. Studies that find biases describe narrow situations,
   and the gains are small. Our backtest agrees: about 49% at the close for
   both leagues.
   ([Duke honors thesis](https://sites.duke.edu/djepapers/files/2017/06/shivgidumalrolandmuench-dje.pdf);
   [Applied Economics 2011](https://informahealthcare.com/doi/abs/10.1080/00036840600690314))

2. **Fixed, early lines are where edge lives.** In pick'em contests
   (e.g. the Westgate SuperContest), lines are posted Wednesday and frozen while
   the market keeps moving. The standard angle is to pick games where the market
   has since moved toward one side. Practitioners report gaps of 0.5–1+ points,
   but I found no rigorous public test.
   ([Rotogrinders](https://rotogrinders.com/articles/sharp-plays-from-supercontest-leaders-revealed-week-4-2681585);
   [SBR forum](https://www.sportsbookreview.com/forum/nfl-betting/1780007-westgate-supercontest-line-variance-results))
   Our own CFB opening-line backtest is the closest evidence we have: top-5 58.7%,
   CLV +2.7 pts. That's suggestive, from a small sample (2023+). **Your pool line
   is a fixed early line, so this is the most promising lever.**

3. **Quarterback changes are the biggest single injury factor.** Books move
   lines 3–7 points for a starting QB out, depending mostly on the backup.
   The spread usually adjusts quickly, so there's only an edge when news breaks
   after a line is frozen (your pickem line).
   ([Grantland](https://grantland.com/the-triangle/if-he-goes-down-we-go-down-nfl-injury-value-in-vegas/);
   [Review-Journal](https://develop.reviewjournal.com/?p=1964401))

4. **"Holdover bias" in early-season CFB.** Bettors overvalue last season's
   top-10 teams in their first game, most strongly against non-Power 5
   opponents. ([Bennett 2019, Atlantic Economic Journal](https://ideas.repec.org/a/kap/atlecj/v47y2019i1d10.1007_s11293-019-09611-y.html))

5. **Older biases have faded.** Home underdogs covered about 53.5% in 1989–2003,
   but only 47.8% in 2004–12. Published anomalies tend to disappear.
   ([inpredictable](https://www.inpredictable.com/2013/08/home-underdogs-are-no-longer-good-bet.html);
   [Levitt 2004](https://ideas.repec.org/a/ecj/econjl/v114y2004i495p223-246.html))

6. **Smaller, situational effects:** travel/time-zone (CFB late season)
   ([Coleman 2017](https://metatoc.com/papers/63650-team-travel-effects-and-the-college-football-betting-market)),
   teams that have clinched playoff seeding
   ([FSR 2014](https://openjournals.libs.uga.edu/fsr/article/view/3242)),
   and favorites being slightly overpriced in CFB
   ([Sinkey & Logan](https://aeaweb.org/conference/2010/retrieve.php?pdfid=406)).

## Test plan (in priority order)

| # | Candidate | How we test it | Data we have |
|---|---|---|---|
| 1 | Pickem line vs live line gap | Grade vs a fixed early line; rank by how far the market moved toward our side | CFB openers 2023+ (proxy); your PDFs going forward |
| 2 | Starting QB change | Flag games where the expected starter differs from last week's; check whether the frozen line missed it | nflverse starting QB per game (needs care: it records who actually started) |
| 3 | CFB holdover bias | Fade last season's top-10 in week 1, especially vs non-P5 | CFBD rankings + games |
| 4 | Early-season CFB edge | Backtest hit rate by week of season | Have it |
| 5 | Travel / time zone | Add distance and time-zone shift as features | CFBD venues; NFL stadium table needed |
| 6 | Late-season motivation | Clinched or eliminated teams, weeks 15+ | Derive from standings |

## Realistic expectations
A sustained 55% on the top of the list would be an excellent result. At 55% per
pick, a week with at least 5 of the top 6 correct happens about 16% of the time.
