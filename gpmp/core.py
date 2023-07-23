# --------------------------------------------------------------
# Author: Emmanuel Vazquez <emmanuel.vazquez@centralesupelec.fr>
# Copyright (c) 2022-2023, CentraleSupelec
# License: GPLv3 (see LICENSE)
# --------------------------------------------------------------
import warnings
import gpmp.num as gnp


class Model:
    """GP Model class

    This class implements a Gaussian Process (GP) model for function
    approximation.

    Attributes
    ==========

    mean : callable
        A function that returns the mean of the Gaussian Process
        (GP). The function is called as follows:
        P = self.mean(x, self.meanparam),
        where x a (n x d) array of data points. It returns a (n x q) matrix,
        where q is the number of basis functions.

    covariance : callable
        A function that returns the covariance of the Gaussian
        Process (GP). The function is called as follows:
        K = self.covariance(x, y, self.covparam, pairwise),
        where x and y are (n x d) and (m x d) arrays of data points,
        and pairwise indicates if an (n x m) covariance matrix
        (pairwise == False) or an (n x 1) vector (n == m, pairwise =
        True) should be returned

    meanparam : array_like, optional
        The parameters for the mean function, specified as a
        one-dimensional array of values.

    covparam : array_like, optional
        The parameters for the covariance function, specified as a
        one-dimensional array of values.

    Example
    =======
            FIXME
            mean = lambda x, meanparam: meanparam[0] + meanparam[1] * x
            covariance = lambda x, y, covparam: covparam[0] * gnp)
            model = Model(mean, covariance, meanparam=[0.5, 0.2], covparam=[1.0, 0.1])

    """

    def __init__(self, mean, covariance, meanparam=None, covparam=None):
        """
        Parameters
        ----------
        mean : callable
            A function that returns the mean of the Gaussian Process (GP).
        covariance : callable
            A function that returns the covariance of the Gaussian Process (GP).
        meanparam : array_like, optional
            The parameters for the mean function, specified as a one-dimensional array of values.
        covparam : array_like, optional
            The parameters for the covariance function, specified as a one-dimensional array of values.

        Examples
        --------
        >>> mean = lambda x, meanparam: meanparam[0] + meanparam[1] * x
        >>> covariance = lambda x, y,
        """
        self.mean = mean
        self.covariance = covariance

        self.meanparam = meanparam
        self.covparam = covparam

    def __repr__(self):
        output = str("<gpmp.core.Model object> " + hex(id(self)))
        return output

    def __str__(self):
        output = str("<gpmp.core.Model object>")
        return output

    def kriging_predictor_with_zero_mean(self, xi, xt, return_type=0):
        """Compute the kriging predictor with zero mean"""
        Kii = self.covariance(xi, xi, self.covparam)
        Kit = self.covariance(xi, xt, self.covparam)

        if gnp._gpmp_backend_ == 'jax' or gnp._gpmp_backend_ == 'numpy':
            lambda_t = gnp.solve(
                Kii, Kit, sym_pos=True, overwrite_a=True, overwrite_b=True
            )
        elif gnp._gpmp_backend_ == 'torch':
            lambda_t = gnp.solve(Kii, Kit)

        if return_type == -1:
            zt_posterior_variance = None
        elif return_type == 0:
            zt_prior_variance = self.covariance(xt, None, self.covparam, pairwise=True)
            zt_posterior_variance = zt_prior_variance - gnp.einsum(
                "i..., i...", lambda_t, Kit
            )
        elif return_type == 1:
            zt_prior_variance = self.covariance(xt, None, self.covparam, pairwise=False)
            zt_posterior_variance = zt_prior_variance - gnp.matmul(lambda_t.T, Kit)

        return lambda_t, zt_posterior_variance

    def kriging_predictor(self, xi, xt, return_type=0):
        """Compute the kriging predictor with non-zero mean

        Parameters
        ----------
        xi : ndarray(ni, d)
            Observation points
        xt : ndarray(nt, d)
            Prediction points
        return_type : -1, 0 or 1
            If -1, returned posterior variance is None. If 0
            (default), return the posterior variance at points xt. If
            1, return the posterior covariance.

        Notes
        -----
        If return_type==1, then the covariance function k must be
        built so that k(xi, xi, covparam) returns the covariance
        matrix of observations, and k(xt, xt, covparam) returns the
        covariance matrix of the predictands. This means that the
        information of which are the observation points and which are
        the prediction points must be coded in xi / xt

        """
        # LHS
        Kii = self.covariance(xi, xi, self.covparam)
        Pi = self.mean(xi, self.meanparam)
        (ni, q) = Pi.shape
        # build [ [K P] ; [P' 0] ]
        LHS = gnp.vstack(
            (gnp.hstack((Kii, Pi)), gnp.hstack((Pi.T, gnp.zeros((q, q)))))
        )

        # RHS
        Kit = self.covariance(xi, xt, self.covparam)
        Pt = self.mean(xt, self.meanparam)
        RHS = gnp.vstack((Kit, Pt.T))

        # lambdamu_t = RHS^(-1) LHS
        lambdamu_t = gnp.solve(LHS, RHS, overwrite_a=True, overwrite_b=True)

        lambda_t = lambdamu_t[0:ni, :]

        # posterior variance
        if return_type == -1:
            zt_posterior_variance = None
        elif return_type == 0:
            zt_prior_variance = self.covariance(xt, None, self.covparam, pairwise=True)
            zt_posterior_variance = zt_prior_variance - gnp.einsum(
                "i..., i...", lambdamu_t, RHS
            )
        elif return_type == 1:
            zt_prior_variance = self.covariance(xt, None, self.covparam, pairwise=False)
            zt_posterior_variance = zt_prior_variance - gnp.matmul(lambdamu_t.T, RHS)

        return lambda_t, zt_posterior_variance

    def predict(self, xi, zi, xt, return_lambdas=False, zero_neg_variances=True, convert_in=True, convert_out=True):
        """Performs a prediction at target points xt given the data (xi, zi).

        Parameters
        ----------
        xi : ndarray(ni,dim)
            observation points
        zi : ndarray(ni,1)
            observed values
        xt : ndarray(nt,dim)
            prediction points
        return_lambdas : bool, optional
            Set return_lambdas=True if lambdas should be returned, by default False
        zero_neg_variances : bool, optional
            Whether to zero negative posterior variances (due to numerical errors), default=True
        convert : bool, optional
            Whether to return numpy arrays or keep _gpmp_backend_ types

        Returns
        -------
        z_posterior_mean : ndarray
            2d array of shape nt x 1
        z_posterior variance : ndarray
            2d array of shape nt x 1

        Notes
        -----
        From a Bayesian point of view, the outputs are respectively
        the posterior mean and variance of the Gaussian process given
        the data (xi, zi).

        """
        if convert_in:
            xi_ = gnp.asarray(xi)
            zi_ = gnp.asarray(zi)
            xt_ = gnp.asarray(xt)

        # posterior variance
        if self.mean is None:
            lambda_t, zt_posterior_variance_ = self.kriging_predictor_with_zero_mean(
                xi_, xt_
            )
        else:
            lambda_t, zt_posterior_variance_ = self.kriging_predictor(xi_, xt_)

        if gnp.any(zt_posterior_variance_ < 0.):
            warnings.warn(
                "In predict: negative variances detected. Consider using jitter.", RuntimeWarning
            )
        if zero_neg_variances:
            zt_posterior_variance_ = gnp.maximum(zt_posterior_variance_, 0.)

        # posterior mean
        zt_posterior_mean_ = gnp.einsum("i..., i...", lambda_t, zi_)

        # outputs
        if convert_out:
            zt_posterior_mean = gnp.to_np(zt_posterior_mean_)
            zt_posterior_variance = gnp.to_np(zt_posterior_variance_)
        else:
            zt_posterior_mean = zt_posterior_mean_
            zt_posterior_variance = zt_posterior_variance_

        if not return_lambdas:
            return (zt_posterior_mean, zt_posterior_variance)
        else:
            return (zt_posterior_mean, zt_posterior_variance, lambda_t)

    def loo_with_zero_mean(self, xi, zi):
        """
        Compute the leave-one-out (LOO) prediction error assuming a zero mean.

        This method computes the LOO prediction error using the "virtual cross-validation" formula,
        which allows for efficient computation of LOO predictions without re-fitting the model.

        Parameters
        ----------
        xi : array_like, shape (n, d)
            Input data points used for fitting the GP model, where n is the number of points and d is the dimensionality.
        zi : array_like, shape (n, )
            Output (response) values corresponding to the input data points xi.

        Returns
        -------
        zloo : array_like, shape (n, )
            Leave-one-out predictions for each data point in xi.
        sigma2loo : array_like, shape (n, )
            Variance of the leave-one-out predictions.
        eloo : array_like, shape (n, )
            Leave-one-out prediction errors for each data point in xi.

        Examples
        --------
        >>> xi = np.array([[1, 2], [3, 4], [5, 6]])
        >>> zi = np.array([1.2, 2.5, 4.2])
        >>> model = Model(mean, covariance, meanparam=[0.5, 0.2], covparam=[1.0, 0.1])
        >>> zloo, sigma2loo, eloo = model.loo_with_zero_mean(xi, zi)
        """
        xi_ = gnp.asarray(xi)
        zi_ = gnp.asarray(zi)

        n = xi_.shape[0]
        K = self.covariance(xi_, xi_, self.covparam)

        # Use the "virtual cross-validation" formula
        if gnp._gpmp_backend_ == 'jax' or gnp._gpmp_backend_ == 'numpy':
            C, lower = gnp.cho_factor(K)
            Kinv = gnp.cho_solve((C, lower), gnp.eye(n))
        elif gnp._gpmp_backend_ == 'torch':
            C = gnp.cholesky(K)
            Kinv = gnp.cholesky_solve(gnp.eye(n), C, upper=False)

        # e_loo,i  = 1 / Kinv_i,i ( Kinv  z )_i
        Kinvzi = gnp.matmul(Kinv, zi_)
        Kinvdiag = gnp.diag(Kinv)
        eloo = Kinvzi / Kinvdiag

        # sigma2_loo,i = 1 / Kinv_i,i
        sigma2loo = 1. / Kinvdiag

        # zloo_i = z_i - e_loo,i
        zloo = zi_ - eloo

        return zloo, sigma2loo, eloo

    def loo(self, xi, zi):
        """
        Compute the leave-one-out (LOO) prediction error.

        This method computes the LOO prediction error using the "virtual cross-validation" formula,
        which allows for efficient computation of LOO predictions without re-fitting the model.

        Parameters
        ----------
        xi : array_like, shape (n, d)
            Input data points used for fitting the GP model, where n is the number of points and d is the dimensionality.
        zi : array_like, shape (n, )
            Output (response) values corresponding to the input data points xi.

        Returns
        -------
        zloo : array_like, shape (n, )
            Leave-one-out predictions for each data point in xi.
        sigma2loo : array_like, shape (n, )
            Variance of the leave-one-out predictions.
        eloo : array_like, shape (n, )
            Leave-one-out prediction errors for each data point in xi.

        Examples
        --------
        >>> xi = np.array([[1, 2], [3, 4], [5, 6]])
        >>> zi = np.array([1.2, 2.5, 4.2])
        >>> model = Model(mean, covariance, meanparam=[0.5, 0.2], covparam=[1.0, 0.1])
        >>> zloo, sigma2loo, eloo = model.loo(xi, zi)
        """

        xi_ = gnp.asarray(xi)
        zi_ = gnp.asarray(zi)

        n = xi_.shape[0]
        K = self.covariance(xi_, xi_, self.covparam)
        P = self.mean(xi_, self.meanparam)

        # Use the "virtual cross-validation" formula
        # Qinv = K^-1 - K^-1P (Pt K^-1 P)^-1 Pt K^-1
        if gnp._gpmp_backend_ == 'jax' or gnp._gpmp_backend_ == 'numpy':
            C, lower = gnp.cho_factor(K)
            Kinv = gnp.cho_solve((C, lower), gnp.eye(n))
            KinvP = gnp.cho_solve((C, lower), P)
        elif gnp._gpmp_backend_ == 'torch':
            C = gnp.cholesky(K)
            Kinv = gnp.cholesky_solve(gnp.eye(n), C, upper=False)
            KinvP = gnp.cholesky_solve(P, C, upper=False)

        PtKinvP = gnp.einsum("ki, kj->ij", P, KinvP)

        R = gnp.solve(PtKinvP, KinvP.T)
        Qinv = Kinv - gnp.matmul(KinvP, R)

        # e_loo,i  = 1 / Q_i,i ( Qinv  z )_i
        Qinvzi = gnp.matmul(Qinv, zi_)
        Qinvdiag = gnp.diag(Qinv)
        eloo = Qinvzi / Qinvdiag

        # sigma2_loo,i = 1 / Qinv_i,i
        sigma2loo = 1. / Qinvdiag

        # z_loo
        zloo = zi_ - eloo

        return zloo, sigma2loo, eloo

    def negative_log_likelihood(self, covparam, xi, zi):
        """Computes the negative log-likelihood of the model

        Parameters
        ----------
        xi : ndarray(ni,d)
            points
        zi : ndarray(ni,1)
            values
        covparam : _type_
            _description_

        Returns
        -------
        nll : scalar
            negative log likelihood
        """
        K = self.covariance(xi, xi, covparam)
        n = K.shape[0]

        if gnp._gpmp_backend_ == 'jax' or gnp._gpmp_backend_ == 'numpy':
            C, lower = gnp.cho_factor(K)
            Kinv_zi = gnp.cho_solve((C, lower), zi)
        elif gnp._gpmp_backend_ == 'torch':
            C = gnp.cholesky(K)
            Kinv_zi = gnp.cholesky_solve(zi.reshape(-1, 1), C, upper=False)
        
        norm2 = gnp.einsum("i..., i...", zi, Kinv_zi)
    
        ldetK = 2. * gnp.sum(gnp.log(gnp.diag(C)))

        L = 0.5 * (n * gnp.log(2. * gnp.pi) + ldetK + norm2)

        return L.reshape(())

    def negative_log_restricted_likelihood(self, covparam, xi, zi):
        """
        Compute the negative log-restricted likelihood of the GP model.

        This method calculates the negative log-restricted likelihood, which is used for
        parameter estimation in the Gaussian Process model.

        Parameters
        ----------
        covparam : array_like
            Covariance parameters for the Gaussian Process.
        xi : array_like, shape (n, d)
            Input data points used for fitting the GP model, where n is the number of points and d is the dimensionality.
        zi : array_like, shape (n, )
            Output (response) values corresponding to the input data points xi.

        Returns
        -------
        L : float
            Negative log-restricted likelihood value.

        Examples
        --------
        >>> xi = np.array([[1, 2], [3, 4], [5, 6]])
        >>> zi = np.array([1.2, 2.5, 4.2])
        >>> model = Model(mean, covariance, meanparam=[0.5, 0.2], covparam=[1.0, 0.1])
        >>> covparam = np.array([1.0, 0.1])
        >>> L = model.negative_log_restricted_likelihood(covparam, xi, zi)
        """
        K = self.covariance(xi, xi, covparam)
        P = self.mean(xi, self.meanparam)
        Pshape = P.shape
        n, q = Pshape

        # Compute a matrix of contrasts
        [Q, R] = gnp.qr(P, "complete")
        W = Q[:, q:n]

        # Contrasts (n-q) x 1
        Wzi = gnp.matmul(W.T, zi)

        # Compute G = W' * (K * W), the covariance matrix of contrasts
        G = gnp.matmul(W.T, gnp.matmul(K, W))

        # Cholesky factorization: G = U' * U, with upper-triangular U
        # Compute G^(-1) * (W' zi)
        if gnp._gpmp_backend_ == 'jax' or gnp._gpmp_backend_ == 'numpy':
            C, lower = gnp.cho_factor(G)
            WKWinv_Wzi = gnp.cho_solve((C, lower), Wzi)
        elif gnp._gpmp_backend_ == 'torch':
            try:
                C = gnp.cholesky(G)
            except RuntimeError:  # Use LinAlgError instead of raising RuntimeError for linalg operations https://github.com/pytorch/pytorch/issues/64785
                # https://stackoverflow.com/questions/242485/starting-python-debugger-automatically-on-error
                # extype, value, tb = __import__("sys").exc_info()
                # __import__("traceback").print_exc()
                # __import__("pdb").post_mortem(tb)
                inf_tensor = gnp.tensor(float('inf'), requires_grad=True)
                return inf_tensor  # returns inf with None gradient

            WKWinv_Wzi = gnp.cholesky_solve(Wzi.reshape(-1, 1), C, upper=False)

        # Compute norm2 = (W' zi)' * G^(-1) * (W' zi)
        norm2 = gnp.einsum("i..., i...", Wzi, WKWinv_Wzi)
    
        # Compute log(det(G)) using the Cholesky factorization
        ldetWKW = 2. * gnp.sum(gnp.log(gnp.diag(C)))

        L = 0.5 * ((n - q) * gnp.log(2. * gnp.pi) + ldetWKW + norm2)

        return L.reshape(())

    def norm_k_sqrd_with_zero_mean(self, xi, zi, covparam):
        """
        Compute the squared norm of the residual vector with zero mean.

        This method calculates the squared norm of the residual vector (zi - mean(xi)) using
        the inverse of the covariance matrix K.

        Parameters
        ----------
        xi : array_like, shape (n, d)
            Input data points used for fitting the GP model, where n is the number of points and d is the dimensionality.
        zi : array_like, shape (n, )
            Output (response) values corresponding to the input data points xi.
        covparam : array_like
            Covariance parameters for the Gaussian Process.

        Returns
        -------
        norm_sqrd : float
            Squared norm of the residual vector.

        Examples
        --------
        >>> xi = np.array([[1, 2], [3, 4], [5, 6]])
        >>> zi = np.array([1.2, 2.5, 4.2])
        >>> model = Model(mean, covariance, meanparam=[0.5, 0.2], covparam=[1.0, 0.1])
        >>> covparam = np.array([1.0, 0.1])
        >>> norm_sqrd = model.norm_k_sqrd_with_zero_mean(xi, zi, covparam)
        """
        K = self.covariance(xi, xi, covparam)
        if gnp._gpmp_backend_ == 'jax' or gnp._gpmp_backend_ == 'numpy':
            C, lower = gnp.cho_factor(K)
            Kinv_zi = gnp.cho_solve((C, lower), zi)
        elif gnp._gpmp_backend_ == 'torch':
            C = gnp.cholesky(K)
            Kinv_zi = gnp.cholesky_solve(zi.reshape(-1, 1), C, upper=False)
            
        norm_sqrd = gnp.einsum("i..., i...", zi, Kinv_zi)
        
        return norm_sqrd

    def norm_k_sqrd(self, xi, zi, covparam):
        """
        Compute the squared norm of the residual vector after applying the contrast matrix W.

        This method calculates the squared norm of the residual vector (Wz) using the inverse of
        the covariance matrix (WKW), where W is a matrix of contrasts.

        Parameters
        ----------
        xi : ndarray, shape (ni, d)
            Input data points used for fitting the GP model, where ni is the number of points and d is the dimensionality.
        zi : ndarray, shape (ni, 1)
            Output (response) values corresponding to the input data points xi.
        covparam : array_like
            Covariance parameters for the Gaussian Process.

        Returns
        -------
        float
            The squared norm of the residual vector after applying the contrast matrix W: (Wz)' (WKW)^-1 Wz.
        """
        K = self.covariance(xi, xi, covparam)
        P = self.mean(xi, self.meanparam)
        n, q = P.shape

        # Compute a matrix of contrasts
        [Q, R] = gnp.qr(P, "complete")
        W = Q[:, q:n]

        # Contrasts (n-q) x 1
        Wzi = gnp.matmul(W.T, zi)

        # Compute G = W' * (K * W), the covariance matrix of contrasts
        G = gnp.matmul(W.T, gnp.matmul(K, W))

        # Cholesky factorization: G = U' * U, with upper-triangular U
        # Compute G^(-1) * (W' zi)
        if gnp._gpmp_backend_ == 'jax' or gnp._gpmp_backend_ == 'numpy':
            C, lower = gnp.cho_factor(G)
            WKWinv_Wzi = gnp.cho_solve((C, lower), Wzi)
        elif gnp._gpmp_backend_ == 'torch':
            C = gnp.cholesky(G)
            WKWinv_Wzi = gnp.cholesky_solve(Wzi.reshape(-1, 1), C, upper=False)
            
        # Compute norm_2 = (W' zi)' * G^(-1) * (W' zi)
        norm_sqrd = gnp.einsum("i..., i...", Wzi, WKWinv_Wzi)

        return norm_sqrd

    def sample_paths(self, xt, nb_paths, method='chol', check_result=True):
        """
        Generates nb_paths sample paths on xt from the GP model GP(0, k),
        where k is the covariance specified by Model.covariance.

        Parameters
        ----------
        xt : ndarray, shape (nt, d)
            Input data points where the sample paths are to be generated, where nt is the number of points and d is the dimensionality.
        nb_paths : int
            Number of sample paths to generate.
        method : str, optional, default: 'chol'
            Method used for the factorization of the covariance matrix. Options are 'chol' for Cholesky decomposition and 'svd' for singular value decomposition.
        check_result : bool, optional, default: True
            If True, checks if the Cholesky factorization is successful.

        Returns
        -------
        ndarray, shape (nt, nb_paths)
            Array containing the generated sample paths at the input points xt.

        Examples
        --------
        >>> xt = np.array([[1, 2], [3, 4], [5, 6]])
        >>> model = Model(mean, covariance, meanparam=[0.5, 0.2], covparam=[1.0, 0.1])
        >>> nb_paths = 10
        >>> sample_paths = model.sample_paths(xt, nb_paths)
        """
        xt_ = gnp.asarray(xt)
        
        K = self.covariance(xt_, xt_, self.covparam)

        # Factorization of the covariance matrix
        if method == "chol":
            C = gnp.cholesky(K, lower=True, overwrite_a=True)
            if check_result:
                if gnp.isnan(C).any():
                    raise AssertionError(
                        "In sample_paths: Cholesky factorization failed. Consider using jitter or the sdv switch."
                    )
        elif method == "svd":
            u, s, vt = gnp.svd(K, full_matrices=True, hermitian=True)
            C = gnp.matmul(u * gnp.sqrt(s), vt)

        # Generates samplepaths
        zsim = gnp.matmul(C, gnp.randn(K.shape[0], nb_paths))

        return zsim

    def conditional_sample_paths(self, ztsim, xi_ind, zi, xt_ind, lambda_t):
        """
        Generates conditional sample paths on xt from unconditional
        sample paths ztsim, using the matrix of kriging weights
        lambda_t, which is provided by kriging_predictor() or predict().

        Conditioning is done with respect to ni observations, located
        at the indices given by xi_ind in ztsim, with corresponding
        observed values zi. xt_ind specifies indices in ztsim
        corresponding to conditional simulation points.

        NOTE: the function implements "conditioning by kriging" (see,
        e.g., Chiles and Delfiner, Geostatistics: Modeling Spatial
        Uncertainty, Wiley, 1999).

        Parameters
        ----------
        ztsim : ndarray, shape (n, nb_paths)
            Unconditional sample paths.
        zi : ndarray, shape (ni, 1)
            Observed values corresponding to the input data points xi.
        xi_ind : ndarray, shape (ni, 1), dtype=int
            Indices of observed data points in ztsim.
        xt_ind : ndarray, shape (nt, 1), dtype=int
            Indices of prediction data points in ztsim.
        lambda_t : ndarray, shape (ni, nt)
            Kriging weights.

        Returns
        -------
        ztsimc : ndarray, shape (nt, nb_paths)
            Conditional sample paths at the prediction data points xt.

        Examples
        --------
        >>> ztsim = np.random.randn(10, 5)
        >>> zi = np.array([[1], [2], [3]])
        >>> xi_ind = np.array([[0], [3], [7]])
        >>> xt_ind = np.array([[1], [2], [4], [5], [6], [8], [9]])
        >>> lambda_t = np.random.randn(3, 7)
        >>> ztsimc = model.conditional_sample_paths(ztsim, xi_ind, zi, xt_ind, lambda_t)
        """
        zi_ = gnp.asarray(zi)
        ztsim_ = gnp.asarray(ztsim)

        d = zi_.reshape((-1, 1)) - ztsim_[xi_ind, :]

        ztsimc = ztsim_[xt_ind, :] + gnp.einsum("ij,ik->jk", lambda_t, d)

        return ztsimc
