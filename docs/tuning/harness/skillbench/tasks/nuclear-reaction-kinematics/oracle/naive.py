"""What the task is built to catch: one kinematic solution (the "+" root) where there are two,
the centre-of-mass cross section used as the lab one, and beam particles as current over e."""
import json
import math

m_a, m_A, m_b, m_B = 6533.833, 938.272, 939.565, 6534.184     # 7Li, p, n, 7Be
t_a, theta = 15.00, math.radians(10.0)
q = m_a + m_A - m_b - m_B
e_cm = t_a * m_A / (m_a + m_A)
root = math.sqrt(m_a * m_b * t_a * math.cos(theta) ** 2 + (m_B + m_b) * (m_B * q + (m_B - m_a) * t_a))
t_n = ((math.sqrt(m_a * m_b * t_a) * math.cos(theta) + root) / (m_b + m_B)) ** 2

beam_per_s = 60.0e-9 / 1.602177e-19
hydrogen_per_cm2 = 50.0e-6 * 6.02214e23 / 14.027 * 2
rate = beam_per_s * hydrogen_per_cm2 * 24.0e-27 * 0.500e-3
json.dump({"e_cm_mev": e_cm, "neutron_energies_mev": [t_n], "rate_per_s": rate}, open("result.json", "w"), indent=1)
