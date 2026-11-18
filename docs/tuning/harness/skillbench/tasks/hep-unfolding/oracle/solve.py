"""The reference solution: run in the project folder, writes result.json.

Fakes removed with the simulated fake fraction; response P(reco i | truth j) = matrix / generated,
whose columns sum to the efficiency; iterative Bayesian (D'Agostini) unfolding from the simulated
truth as prior. The purity is 0.37, so bin-by-bin factors would be pulled to the simulated shape
and a plain inversion oscillates (it is printed for comparison).

The number of iterations is fixed before the data are unfolded for good, by a stress test: a
spectrum shaped like the data (a first-pass unfolding) is folded, fluctuated and unfolded from the
simulated prior, and the number with the smallest bias^2 + variance is taken. Uncertainty per bin:
the spread of the unfolded toys of the data, with that bias added in quadrature.
"""
import json

import numpy as np

rng = np.random.default_rng(1)
TOYS = 300

spectra = np.genfromtxt("spectra.csv", delimiter=",", names=True)
matrix = np.loadtxt("response.csv", delimiter=",", skiprows=1)[:, 1:]            # [reco, truth]
data, mc_reco, mc_fake, mc_truth = (spectra[name] for name in ("data", "mc_reco", "mc_reco_fake", "mc_truth"))

response = matrix / mc_truth                    # P(reco i | truth j)
efficiency = response.sum(axis=0)
signal = data * (1 - mc_fake / mc_reco)         # fakes out, by the simulated fraction
prior = mc_truth * signal.sum() / matrix.sum()
purity = np.diag(matrix) / matrix.sum(axis=1)
print("efficiency %.2f to %.2f, purity %.2f to %.2f" % (efficiency.min(), efficiency.max(), purity.min(), purity.max()))


def unfold(measured, iterations):
    """measured: [..., reco bins]. Returns [..., truth bins]."""
    truth = np.broadcast_to(prior, measured.shape[:-1] + prior.shape).copy()
    for _ in range(iterations):
        folded = truth @ response.T
        truth = truth / efficiency * ((measured / folded) @ response)
    return truth


# Stress test on a spectrum like the data's, to choose the number of iterations.
target = unfold(signal, 4)
toys = rng.poisson(target @ response.T, size=(TOYS, len(signal))).astype(float)
best = None
for iterations in range(1, 41):
    unfolded = unfold(toys, iterations)
    bias = unfolded.mean(axis=0) - target
    mse = np.mean((bias**2 + unfolded.var(axis=0)) / target**2)
    if best is None or mse < best[1]:
        best = (iterations, mse, bias)
iterations, _, bias = best
print("stress test: %d iterations, relative rms error %.2f%%, largest bias %.2f%%" % (iterations, 100 * np.sqrt(best[1]), 100 * np.abs(bias / target).max()))

unfolded = unfold(signal, iterations)
# Statistical spread: the data fluctuated (fakes included, then removed again), unfolded the same way.
replicas = rng.poisson(data, size=(TOYS, len(data))) * (1 - mc_fake / mc_reco)
spread = unfold(replicas, iterations).std(axis=0)
uncertainty = np.sqrt(spread**2 + bias**2)

inverted = np.linalg.solve(response, signal)
mean_efficiency = (efficiency * unfolded).sum() / unfolded.sum()          # averaged over the unfolded spectrum, not the simulated one
print("total: unfolded %.0f; data minus fakes %.0f over the mean efficiency %.3f = %.0f" % (unfolded.sum(), signal.sum(), mean_efficiency, signal.sum() / mean_efficiency))
print(" bin   unfolded     +-   (inversion)")
for i in range(len(unfolded)):
    print("%4d %10.0f %6.0f %12.0f" % (i + 1, unfolded[i], uncertainty[i], inverted[i]))
json.dump({"unfolded": unfolded.tolist(), "uncertainty": uncertainty.tolist()}, open("result.json", "w"), indent=1)
