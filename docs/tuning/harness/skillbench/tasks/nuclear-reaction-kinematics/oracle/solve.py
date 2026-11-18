"""The reference solution: run in the project folder, writes result.json.

Relativistic two-body kinematics from the invariant s; both lab momenta at the
detector angle; the solid-angle Jacobian for each; beam particles from the
electrical current over the charge state; hydrogen atoms per cm2 from the
foil. Checked by four-momentum conservation, by a numerical derivative of the
angle map, and against the non-relativistic formula.
"""
import json
import math
import re

notes = open("notes.md").read()


def number(pattern):
    return float(re.search(pattern, notes).group(1))


m_target = number(r"\| p \| ([\d.]+)")
m_ejectile = number(r"\| n \| ([\d.]+)")
m_beam = number(r"\| 7Li \| ([\d.]+)")
m_residue = number(r"\| 7Be \| ([\d.]+)")
t_beam = number(r"kinetic energy ([\d.]+) MeV")
charge_state = int(number(r"charge state (\d+)\+"))
current = number(r"([\d.]+) nA electrical") * 1e-9
areal = number(r"([\d.]+) ug/cm2") * 1e-6                       # g/cm2
molar = number(r"Molar mass of CH2: ([\d.]+)")
theta = math.radians(number(r"at ([\d.]+) degrees to the beam"))
solid_angle = number(r"subtending ([\d.]+) msr") * 1e-3
dsigma_cm = number(r"= ([\d.]+) mb/sr") * 1e-27                 # cm2/sr
e_charge = number(r"e = ([\d.e-]+) C")
avogadro = number(r"N_A = ([\d.e]+) /mol")

# Entrance channel.
s = (m_beam + m_target) ** 2 + 2 * m_target * t_beam
e_cm = math.sqrt(s) - m_beam - m_target
p_beam = math.sqrt(t_beam * (t_beam + 2 * m_beam))
e_total = t_beam + m_beam + m_target
beta = p_beam / e_total
gamma = 1 / math.sqrt(1 - beta**2)

# Exit channel in the centre of mass.
p_star = math.sqrt((s - (m_ejectile + m_residue) ** 2) * (s - (m_ejectile - m_residue) ** 2) / (4 * s))
e_star = math.hypot(p_star, m_ejectile)

# Lab momentum at angle theta: E* = gamma (E - beta p cos theta), a quadratic in p.
c = math.cos(theta)
a2 = 1 - (beta * c) ** 2
half_b = (e_star / gamma) * beta * c
discriminant = half_b**2 - a2 * (m_ejectile**2 - (e_star / gamma) ** 2)
assert discriminant > 0, "the detector is outside the neutron cone"
groups = []
for sign in (+1, -1):
    p = (half_b + sign * math.sqrt(discriminant)) / a2
    if p <= 0:
        continue
    energy = math.hypot(p, m_ejectile)
    jacobian = p**2 / (gamma * p_star * abs(p - beta * energy * c))       # dOmega_cm / dOmega_lab
    # Four-momentum conservation: what is left over must have the mass of 7Be.
    left_e, left_z, left_x = e_total - energy, p_beam - p * c, -p * math.sin(theta)
    assert abs(math.sqrt(left_e**2 - left_z**2 - left_x**2) - m_residue) < 1e-6
    groups.append({"kinetic": energy - m_ejectile, "jacobian": jacobian, "p": p})


def lab_angle(theta_cm):
    return math.atan2(p_star * math.sin(theta_cm), gamma * (p_star * math.cos(theta_cm) + beta * e_star))


for group in groups:                                             # the Jacobian again, numerically
    cos_cm = gamma * (group["p"] * c - beta * math.hypot(group["p"], m_ejectile)) / p_star
    theta_cm, h = math.acos(cos_cm), 1e-6
    slope = (lab_angle(theta_cm + h) - lab_angle(theta_cm - h)) / (2 * h)
    numeric = math.sin(theta_cm) / (math.sin(theta) * abs(slope))
    assert abs(numeric / group["jacobian"] - 1) < 1e-5, (numeric, group["jacobian"])
    group["theta_cm_deg"] = math.degrees(theta_cm)

# Non-relativistic check: good to about a per cent here.
q_value = m_beam + m_target - m_ejectile - m_residue
root = math.sqrt(m_beam * m_ejectile * t_beam * c**2 + (m_residue + m_ejectile) * (m_residue * q_value + (m_residue - m_beam) * t_beam))
for group, sign in zip(groups, (+1, -1)):
    classical = ((math.sqrt(m_beam * m_ejectile * t_beam) * c + sign * root) / (m_ejectile + m_residue)) ** 2
    assert abs(classical / group["kinetic"] - 1) < 0.015, (classical, group["kinetic"])

beam_per_s = current / (charge_state * e_charge)
hydrogen_per_cm2 = areal * avogadro / molar * 2
rate = sum(beam_per_s * hydrogen_per_cm2 * dsigma_cm * group["jacobian"] * solid_angle for group in groups)

json.dump({"e_cm_mev": e_cm, "neutron_energies_mev": [group["kinetic"] for group in groups], "rate_per_s": rate},
          open("result.json", "w"), indent=1)
print("E_cm %.4f MeV (Q %.3f); beam %.4g /s; hydrogen %.4g /cm2" % (e_cm, q_value, beam_per_s, hydrogen_per_cm2))
for group in groups:
    print("neutron %.4f MeV, theta_cm %.2f deg, dOmega_cm/dOmega_lab %.3f" % (group["kinetic"], group["theta_cm_deg"], group["jacobian"]))
print("rate %.2f /s" % rate)
