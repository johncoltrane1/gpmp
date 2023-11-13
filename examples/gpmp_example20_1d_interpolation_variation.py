"""
Plot and optimize the restricted negative log-likelihood

Author: Emmanuel Vazquez <emmanuel.vazquez@centralesupelec.fr>
Copyright (c) 2022-2023, CentraleSupelec
License: GPLv3 (see LICENSE)
"""

import gpmp.num as gnp
import gpmp as gp
import matplotlib.pyplot as plt


def generate_data():
    """
    Data generation.
    
    Returns
    -------
    tuple
        (xt, zt): target data
        (xi, zi): input dataset
    """
    dim = 1
    nt = 200
    box = [[-1], [1]]
    xt = gp.misc.designs.regulargrid(dim, nt, box)
    zt = gp.misc.testfunctions.twobumps(xt)

    ni = 6
    xi = gp.misc.designs.ldrandunif(dim, ni, box)
    zi = gp.misc.testfunctions.twobumps(xi)
   
    return xt, zt, xi, zi


def constant_mean(x, param):
    return gnp.ones((x.shape[0], 1))


def kernel(x, y, covparam, pairwise=False):
    p = 3
    return gp.kernel.maternp_covariance(x, y, p, covparam, pairwise)


def visualize_results(xt, zt, xi, zi, zpm, zpv):
    """
    Visualize the results using gp.misc.plotutils (a matplotlib wrapper).
    
    Parameters
    ----------
    xt : numpy.ndarray
        Target x values
    zt : numpy.ndarray
        Target z values
    xi : numpy.ndarray
        Input x values
    zi : numpy.ndarray
        Input z values
    zpm : numpy.ndarray
        Posterior mean
    zpv : numpy.ndarray
        Posterior variance
    """
    fig = gp.misc.plotutils.Figure(isinteractive=True)
    fig.plot(xt, zt, 'k', linewidth=1, linestyle=(0, (5, 5)))
    fig.plotdata(xi, zi)
    fig.plotgp(xt, zpm, zpv, colorscheme='simple')
    fig.xlabel('$x$')
    fig.ylabel('$z$')
    fig.title('Posterior GP with parameters selected by ReML')
    fig.show()


def main():
    xt, zt, xi, zi = generate_data()
    xi_ = gnp.asarray(xi)
    zi_ = gnp.asarray(zi)

    meanparam = None
    covparam0 = None
    model = gp.core.Model(constant_mean, kernel, meanparam, covparam0)

    # Parameter initial guess
    covparam0 = gp.kernel.anisotropic_parameters_initial_guess(model, xi, zi)

    # selection criterion
    def crit_(covparam):
        l = model.negative_log_restricted_likelihood(covparam, xi_, zi_)
        return l

    nlrl = gnp.jax.jit(crit_)
    dnlrl = gnp.jax.jit(gnp.grad(nlrl))
    
    nlrl, dnlrl = gp.kernel.make_selection_criterion_with_gradient(
        model.negative_log_restricted_likelihood, xi, zi
    )

    covparam_reml, info = gp.kernel.autoselect_parameters(
        covparam0, nlrl, dnlrl, silent=False, info=True
    )

    model.covparam = gnp.asarray(covparam_reml)
    info["covparam0"] = covparam0
    info["covparam"] = covparam_reml
    info["selection_criterion"] = nlrl

    gp.misc.modeldiagnosis.diag(model, info, xi, zi)

    # Prediction
    zpm, zpv = model.predict(xi, zi, xt)

    # Visualization
    print('\nVisualization')
    print('-------------')
    visualize_results(xt, zt, xi, zi, zpm, zpv)


if __name__ == '__main__':
    main()