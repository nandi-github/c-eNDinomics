
# filename: make_benchmarks.py
import json

# 1) Load your S&P 500 annual returns JSON (as you pasted above)
with open("sp500_total_return.json", "r", encoding="utf-8") as f:
    data = json.load(f)  # list of {"year":YYYY,"totalReturn":"NN.NN"}

# 2) Sort ascending by year
rows = sorted(data, key=lambda r: int(r["year"]))

# 3) Pick the last 30 years (adjust if you want a different window)
win = rows[-30:]

# 4) Build normalized level series (Year 1 = 1.0)
levels = []
cur = 1.0
for r in win:
    # totalReturn is a string percent, e.g., "17.88"; convert to decimal
    rr = float(r["totalReturn"]) / 100.0
    cur = cur * (1.0 + rr)
    levels.append(cur)

# 5) (Optional) normalize again to exactly 1.0 in the first year
if levels and levels[0] != 0:
    norm = [x / levels[0] for x in levels]
else:
    norm = levels

# 6) Write benchmarks.json in the format reporting.py expects
benchmarks = {
    "benchmarks": [
        {
            "name": "S&P 500 (Total Return)",
            "series": norm  # length 30, normalized to Year 1
        }
    ],
    "notes": [
        "Annual total-return levels normalized to 1.0 in the first year.",
        "Length must match simulation years; here we used the most recent 30 years."
    ]
}
with open("config/benchmarks.json", "w", encoding="utf-8") as f:
    json.dump(benchmarks, f, indent=2)
print("Wrote benchmarks.json with S&P 500 series.")

