# LaunchScout evaluation

Planted errors caught: **158 of 161** (98%), across 6 real research runs, one review run, one strategy and one plan. Free to re-run: `python scripts/evaluate.py`.

| Planted error | Caught |
|---|---|
| city-wide price range given as a competitor's price | 5/6 |
| price copied from another competitor | 17/19 |
| invented price on a real page | 21/21 |
| source link never seen | 21/21 |
| search-engine redirect as source | 21/21 |
| padded source that never names the business | 16/16 |
| competitor placed in the wrong city | 21/21 |
| listing site named as a competitor | 6/6 |
| same business listed twice | 6/6 |
| another business's review attached | 5/5 |
| invented customer quote | 5/5 |
| business's own marketing text as a review | 5/5 |
| wrong Google rating | 3/3 |
| invented number in the strategy | 1/1 |
| unknown competitor cited as evidence | 1/1 |
| launch price far outside the market | 1/1 |
| positioning line without the price | 1/1 |
| invented price in the launch plan | 1/1 |
| launch plan missing a week | 1/1 |

## Every miss

- price copied from another competitor (082957_chennai): Rs 1500 onto Chennai Beats Dance Academy
- city-wide price range given as a competitor's price (082957_chennai): Rs 3000 onto The Life of Dance Academy from https://thelifeofdance.com/dance-classes-near-me-in-chennai-2/
- control: real competitor kept by the city check (084733_chennai): Zenith Dance Academy
- control: real competitor kept by the city check (084733_chennai): RAACK Academy of Dance
- price copied from another competitor (234843_remeasure_1): Rs 800 onto The Workshop Dance Company

## Controls (real answers must not be flagged)

| Control | Passed |
|---|---|
| real competitor kept by the city check | 21/23 |
| real review quotes kept | 1/1 |
| real strategy passes | 1/1 |
| real plan passes | 1/1 |

## Hand-labelled real claims: 7 of 9 judged correctly

| Business | Claim | Truth | Checker | Note |
|---|---|---|---|---|
| Raack Academy Of Dance | Rs 1,500 | right | kept ✓ | adults fee in an lbb.in article, about 460 characters after the name |
| Leo's Dance Academy | Rs 300 | right | flagged ✗ | personal class fee, about 540 characters after the name |
| Raack Academy Of Dance | Rs 1,300 | wrong | kept ✗ | children's fee in the same paragraph as the adult fee |
| Movementz Factor | source link | right | kept ✓ | post names the studio as @movementzfactor |
| Movementz Factor | Rs 1,200 | right | kept ✓ | joining fee in that post |
| DSA Dance Academy | source link | wrong | flagged ✓ | post belongs to another studio |
| Movementz Factor | source link | wrong | flagged ✓ | reel belongs to Vibe Dance Academy |
| Raack Academy of Dance | Rs 4,000 | wrong | flagged ✓ | only '4000 events performed' on the page; price copied from another studio |
| The Life of Dance | Rs 4,000 | right | kept ✓ | 'adults 13 and above 4,000 month' on its own site |

## End-to-end runs: 3 of 7 produced a full report

Real, paid runs of all four agents (logged by hand from the run outputs). A stopped run is the checks refusing to guess, not a crash; its partial findings are saved for review.

| Idea | City | Outcome | Time | Note |
|---|---|---|---|---|
| Dance classes for working adults | Chennai | full report | 109 s | run in the app, live log |
| Dance classes for working adults | Chennai | full report (partial: fewer than 3 priced) | 122 s | saved as the example report |
| Millet lunch boxes | Coimbatore | full report | 74 s | no code changes from the dance idea |
| Millet lunch boxes | Coimbatore | stopped at research | 90 s | only 2 priced (before the partial outcome existed) |
| Millet lunch boxes | Coimbatore | stopped at research | 97 s | only 1 priced on the last attempt |
| Millet lunch boxes | Coimbatore | stopped at reviews | 142 s | most lunch services have no Google listing (before the review partial) |
| Millet lunch boxes | Coimbatore | stopped at reviews | 131 s | a verified quote was lost on retries: bug, since fixed |
