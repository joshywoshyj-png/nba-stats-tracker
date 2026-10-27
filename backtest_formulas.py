"""Evaluate saved pregame predictions against simple season baselines.
Chronological holdout reports recent performance without training on test games.
Run after update_accuracy.py. Does not change prediction formulas.
"""
import csv
from collections import defaultdict
from pathlib import Path

STATS = ('points','rebounds','assists','three_pointers','steals','blocks')
path=Path('nba_prediction_results.csv')
if not path.exists():
    print('No prediction results CSV yet. Run update_accuracy.py first.')
    raise SystemExit(0)
with path.open(encoding='utf-8-sig',newline='') as f:
    rows=list(csv.DictReader(f))
rows=[r for r in rows if r.get('game_date') and r.get('player_id')]
rows.sort(key=lambda r:(r['game_date'],r.get('player_id','')))
if not rows:
    print('No scored pregame predictions yet.')
    raise SystemExit(0)
# Keep dates together across the split.
dates=sorted({r['game_date'] for r in rows})
if len(dates)<5:
    print('Only',len(dates),'game dates: results are preliminary. Aim for 5+ dates.')
split=max(1,int(len(dates)*.8))
test_dates=set(dates[split:]) if len(dates)>1 else set(dates)
print('COURTSIDE CHRONOLOGICAL EVALUATION')
print('Scored games:',len(rows),'| Holdout dates:',len(test_dates))
print('The baseline uses each snapshot’s saved season average (no future data).')
for stat in STATS:
    samples=[]
    for r in rows:
        if r['game_date'] not in test_dates:continue
        try:
            actual=float(r['actual_'+stat]); predicted=float(r['pred_'+stat]);baseline=float(r['baseline_'+stat])
        except (KeyError,ValueError,TypeError):continue
        samples.append((abs(predicted-actual),abs(baseline-actual)))
    if not samples:continue
    model=sum(x[0] for x in samples)/len(samples)
    base=sum(x[1] for x in samples)/len(samples)
    print(f'{stat:17} model MAE={model:.3f}  season baseline MAE={base:.3f}  n={len(samples)}')
print('Note: This compares existing formulas to season baselines, not alternative fitted weights.')
