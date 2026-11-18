"""What the task is built to catch: the model without its nuisance parameters. CLs from the Poisson
count with the background fixed at 50 and the signal at 35 per fb, and the expected limits from
the quantiles of a Poisson of mean 50 - as if the +-10 on the background were not there."""
import csv
import json

from scipy import optimize, stats

rows = {row["quantity"]: float(row["value"]) for row in csv.DictReader(open("yields.csv"))}
n_obs, b, s1 = int(rows["observed"]), rows["background"], rows["signal_per_fb"]


def limit(n):
    cls = lambda mu: stats.poisson.cdf(n, mu * s1 + b) / stats.poisson.cdf(n, b)
    return optimize.brentq(lambda mu: cls(mu) - 0.05, 1e-4, 10.0)


low, median, high = (int(stats.poisson.ppf(q, b)) for q in (0.1587, 0.5, 0.8413))
answer = {"obs_limit_fb": limit(n_obs), "exp_limit_fb": limit(median), "exp_minus1_fb": limit(low), "exp_plus1_fb": limit(high)}
json.dump(answer, open("result.json", "w"), indent=1)
print(answer)
