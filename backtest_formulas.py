"""COURTSIDE — chronological out-of-sample blend comparison.
Candidate blends use saved pregame forecasts and saved season averages.
This does not fit or modify the underlying stat-specific model weights.
"""
import csv
from pathlib import Path
from statistics import mean

STATS = ('points','rebounds','assists','three_pointers','steals','blocks')
path = Path('nba_prediction_results.csv')
if not path.exists():
    print('No scored results file yet.')
    raise SystemExit(0)
with path.open(newline='', encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
rows = [r for r in rows if r.get('game_date') and r.get('player_id')]
dates = sorted({r['game_date'] for r in rows})
if len(dates) < 6:
    print('Need at least 6 distinct scored game dates to compare formulas on future dates.')
    raise SystemExit(0)
cut = max(1, min(len(dates)-1, int(len(dates)*.7)))
train_dates, test_dates = set(dates[:cut]), set(dates[cut:])
print('COURTSIDE CHRONOLOGICAL FORMULA COMPARISON')
print('Training dates:', len(train_dates), '| Later holdout dates:', len(test_dates))
print('Blend weights: 1.0 = Courtside, 0.0 = saved season average.')
print("No automatic deployment or future-data feature recomputation.")
for stat in STATS:
    valid=[]
    for r in rows:
        try:
            if any(str(r.get(prefix+stat, '')).strip()=='' for prefix in ('pred_','baseline_','actual_')): continue
            pred=float(r['pred_'+stat]); base=float(r['baseline_'+stat]); actual=float(r['actual_'+stat])
            if not all(__import__('math').isfinite(v) for v in (pred,base,actual)): continue
            valid.append((r['game_date'],pred,base,actual))
        except (ValueError, TypeError, KeyError): continue
    train=[x for x in valid if x[0] in train_dates]
    test=[x for x in valid if x[0] in test_dates]
    if len(train)<30 or len(test)<15:
        print(f'{stat:17} insufficient samples (train={len(train)}, test={len(test)})')
        continue
    def mae(samples,w): return mean(abs(w*p+(1-w)*b-a) for _,p,b,a in samples)
    weights=[0,.25,.5,.75,1]
    best=min(weights,key=lambda w:mae(train,w))
    print(f'{stat:17} train-chosen blend={best:.2f} | holdout MAE: '
          f'Courtside={mae(test,1):.3f}, season={mae(test,0):.3f}, '
          f'blend={mae(test,best):.3f} (n={len(test)})')
print('Holdout scores are exploratory; repeat on future unseen dates before changing production formulas.')
