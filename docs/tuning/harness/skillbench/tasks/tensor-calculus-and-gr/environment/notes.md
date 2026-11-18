# Charged dilaton black hole: metric, conventions, where to evaluate

Units G = c = 1. Coordinates x^mu = (t, r, theta, phi), signature (-,+,+,+).
Einstein-frame metric of the electrically charged dilaton black hole with
mass M and charge Q (asymptotic value of the dilaton set to zero):

    ds^2 = -(1 - 2M/r) dt^2 + dr^2 / (1 - 2M/r) + r (r - Q^2/M) (dtheta^2 + sin^2(theta) dphi^2)

## Curvature conventions

We follow Weinberg, Gravitation and Cosmology, throughout:

    Gamma^l_{mn} = (1/2) g^{ls} (d_m g_{sn} + d_n g_{sm} - d_s g_{mn})
    R^l_{mnk}    = d_k Gamma^l_{mn} - d_n Gamma^l_{mk} + Gamma^e_{mn} Gamma^l_{ke} - Gamma^e_{mk} Gamma^l_{ne}
    R_{mk}       = R^l_{mlk}
    R            = g^{mk} R_{mk}

(d_m is the partial derivative with respect to x^m; repeated indices are
summed.) The Kretschmann scalar is K = R_{lmnk} R^{lmnk}.

## Where to evaluate

M = 1, Q = 0.8, at the point r = 3, theta = pi/3 (nothing depends on t or phi).
