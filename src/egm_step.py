"""Implementation of the EGM algorithm."""
import copy
from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

from scipy import interpolate


def do_egm_step(
    period: int,
    state: int,
    policy: np.ndarray,
    value: np.ndarray,
    savings_grid: np.ndarray,
    quad_points_normal: np.ndarray,
    quad_weights: np.ndarray,
    params: pd.DataFrame,
    options: Dict[str, int],
    utility_func: Callable,
    inv_marginal_utility_func: Callable,
    compute_next_period_marginal_utility: Callable,
    compute_next_period_value: Callable,
    compute_current_period_value: Callable,
    compute_expected_value: Callable,
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Runs the Endogenous-Grid-Method Algorithm (EGM step).

    Args:
        period (int): Current period t.
        state (int): State of the agent, e.g. 0 = "retirement", 1 = "working".
        policy (List[np.ndarray]): Nested list of np.ndarrays storing the
            choice-specific consumption policies. Dimensions of the list are:
            [n_periods][n_discrete_choices][2, *n_endog_wealth_grid*], where 
            *n_endog_wealth_grid* is of variable length depending on the number of 
            concurrent local optima for consumption. The arrays have shape
            [2, *n_endog_wealth_grid*] and are initialized to
            *endog_wealth_grid* = n_grid_wealth + 1. We include one additional
            grid point to the left of the endogenous wealth grid, which we set
            to zero (that's why we have n_grid_wealth + 1 initial points). 
            Position [0, :] of the arrays contain the endogenous grid over wealth M, 
            and [1, :] stores the corresponding value of the (consumption) policy 
            function c(M, d), for each time period and each discrete choice. 
        value (List[np.ndarray]): Nested list of np.ndarrays storing the
            choice-specific value functions. Dimensions of the list are:
            [n_periods][n_discrete_choices][2, *n_endog_wealth_grid*], where 
            *n_endog_wealth_grid* is of variable length depending on the number of 
            kinks and non-concave regions. The arrays have shape
            [2, *n_endog_wealth_grid*] and are initialized to
            *endog_wealth_grid* = n_grid_wealth + 1. We include one additional
            grid point to the left of the endogenous wealth grid, which we set
            to zero (that's why we have n_grid_wealth + 1 initial points). 
            Position [0, :] of the array contains the endogenous grid over wealth M, 
            and [1, :] stores the corresponding value of the value function v(M, d),
            for each time period and each discrete choice. 
        savings_grid (np.ndarray): Array of shape n_wealth_grid denoting the
            exogenous savings grid.
        quad_points_normal (np.ndarray): Array of shape (n_quad_stochastic,)
            containing (normally distributed) stochastic components.
        quad_weights (np.ndarray): Weights associated with the quadrature points.
            Will be used for integration over the stochastic income component
            in the Euler equation below. Also of shape (n_quad_stochastic,).
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
        options (dict): Options dictionary.
        utility_func (callable): The agent's utility function.
        inv_marginal_utility_func (callable): Inverse of the marginal utility
            function.
        compute_value_function (callable): Function to compute the agent's 
            next-period value function, which is an array of shape 
            (n_quad_points * n_grid_wealth,).
        compute_expected_value (callable): Function to compute the agent's
            expected value, which is an array of shape (n_grid_wealth,).
        compute_next_period_marginal_utilty (callable): Function to compute the
            the marginal utility of the next period, which is an array of
            shape (n_grid_wealth,).
        compute_current_period_consumption (callable): Function to compute the
            consumption in the current period, which is an array of shape
            (n_grid_wealth,).


    Returns:
        (tuple) Tuple containing
        
        - policy (List[np.ndarray]): Nested list of np.ndarrays storing the
            choice-specific consumption policies. Dimensions of the list are:
            [n_periods][n_discrete_choices][2, *n_endog_wealth_grid*]. 
        - value (List[np.ndarray]): Nested list of np.ndarrays storing the
            choice-specific value functions. Dimensions of the list are:
            [n_periods][n_discrete_choices][2, *n_endog_wealth_grid*].
    """
    # 1) Policy: Current period consumption
    matrix_next_period_wealth = get_next_period_wealth_matrix(
        period, state, savings_grid, quad_points_normal, params, options
    )
    matrix_marginal_wealth = get_next_period_marg_wealth_matrix(params, options)

    next_period_consumption = get_next_period_consumption(
        period, policy, matrix_next_period_wealth, options
    )

    next_period_value = compute_next_period_value(
        period, value, matrix_next_period_wealth, params, options, utility_func,
    )
    next_period_marginal_utility = compute_next_period_marginal_utility(
        state, next_period_consumption, next_period_value, params, options,
    )
    current_period_consumption = get_current_period_consumption(
        next_period_marginal_utility,
        matrix_next_period_wealth,
        matrix_marginal_wealth,
        quad_weights,
        params,
        inv_marginal_utility_func,
    )

    # 2) Value function: Current period value
    # current_period_utility = utility_func(current_period_consumption, params)
    expected_value = compute_expected_value(
        state,
        next_period_value,
        matrix_next_period_wealth,
        quad_weights,
        params,
        options,
    )
    current_period_value = compute_current_period_value(
        state, current_period_consumption, expected_value, params, utility_func
    )

    # 3) Endogenous wealth grid
    endog_wealth_grid = savings_grid + current_period_consumption

    # 4) Update policy and consumption function
    # If no discrete alternatives; only one state, i.e. one column with index = 0
    state_index = 0 if options["n_discrete_choices"] < 2 else state

    policy[period][state_index][0, 1:] = endog_wealth_grid
    policy[period][state_index][1, 1:] = current_period_consumption

    value[period][state_index][0, 1:] = endog_wealth_grid
    value[period][state_index][1, 1:] = current_period_value
    value[period][state_index][1, 0] = expected_value[0]

    return policy, value, expected_value


def get_next_period_wealth_matrix(
    period: int,
    state: int,
    savings: float,
    quad_points: float,
    params: pd.DataFrame,
    options: Dict[str, int],
) -> float:
    """Computes all possible levels of next period wealth M_(t+1)

    Args:
        period (int): Current period t.
        state (int): State of the agent, e.g. 0 = "retirement", 1 = "working".
        savings_grid (np.ndarray): Array of shape n_grid_wealth denoting the
            exogenous savings grid.
        quad_points (np.ndarray): Array of shape (n_quad_stochastic,)
            containing (normally distributed) stochastic components.
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
        options (dict): Options dictionary.

    Returns:
        next_period_wealth (np.ndarray): Array of all possible next period
            wealths with shape (n_quad_stochastic, n_grid_wealth).
    """
    r = params.loc[("assets", "interest_rate"), "value"]
    sigma = params.loc[("shocks", "sigma"), "value"]

    n_grid_wealth = options["grid_points_wealth"]
    n_quad_stochastic = options["quadrature_points_stochastic"]

    shocks = quad_points * sigma
    next_period_income = _calc_stochastic_income(period + 1, shocks, params, options)

    next_period_wealth = np.full(
        (n_grid_wealth, n_quad_stochastic), next_period_income * state,
    ).T + np.full((n_quad_stochastic, n_grid_wealth), savings * (1 + r))

    # Retirement safety net, only in retirement model
    consump_floor_index = ("assets", "consumption_floor")
    if (
        consump_floor_index in params.index
        or params.loc[consump_floor_index, "value"] > 0
    ):
        consump_floor = params.loc[consump_floor_index, "value"]
        next_period_wealth[next_period_wealth < consump_floor] = consump_floor

    return next_period_wealth


def get_next_period_marg_wealth_matrix(
    params: pd.DataFrame, options: Dict[str, int]
) -> np.ndarray:
    """Computes marginal next period wealth.

    Args:
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
        options (dict): Options dictionary.

    Returns:
        marginal_wealth (np.ndarray):  Array of all possible next period
            marginal wealths. Shape (n_quad_stochastic, n_grid_wealth).
    """
    n_grid_wealth = options["grid_points_wealth"]
    n_quad_stochastic = options["quadrature_points_stochastic"]
    r = params.loc[("assets", "interest_rate"), "value"]

    marginal_wealth = np.full((n_quad_stochastic, n_grid_wealth), (1 + r))

    return marginal_wealth


def get_next_period_consumption(
    period: int,
    policy: List[np.ndarray],
    matrix_next_period_wealth: np.ndarray,
    options: Dict[str, int],
) -> np.ndarray:
    """Computes consumption in the next period via linear interpolation.

    Extrapolate lineary in wealth regions to larger than max_wealth.

    Args:
        period (int): Current period t.
        policy (List[np.ndarray]): Nested list of np.ndarrays storing the
            choice-specific consumption policies. Dimensions of the list are:
            [n_periods][n_discrete_choices][2, *n_endog_wealth_grid*], where 
            *n_endog_wealth_grid* is of variable length depending on the number of 
            concurrent local optima for consumption. The arrays have shape
            [2, *n_endog_wealth_grid*] and are initialized to
            *endog_wealth_grid* = n_grid_wealth + 1. We include one additional
            grid point to the left of the endogenous wealth grid, which we set
            to zero (that's why we have n_grid_wealth + 1 initial points). 
            Position [0, :] of the arrays contain the endogenous grid over wealth M, 
            and [1, :] stores the corresponding value of the (consumption) policy 
            function c(M, d), for each time period and each discrete choice.
        matrix_next_period_wealth (np.ndarray): Array of all possible next period
            wealths with shape (n_quad_stochastic, n_grid_wealth).
        options (dict): Options dictionary.

    Returns:
        next_period_consumption_interp (np.ndarray): Array of next period
            consumption of shape (n_quad_stochastic * n_grid_wealth,).
    """
    n_choices = options["n_discrete_choices"]
    n_grid_wealth = options["grid_points_wealth"]
    n_quad_stochastic = options["quadrature_points_stochastic"]
    choice_range = [0] if n_choices < 2 else range(n_choices)

    next_period_consumption_interp = np.empty(
        (n_choices, n_quad_stochastic * n_grid_wealth)
    )

    for state_index in choice_range:
        next_period_wealth = policy[period + 1][state_index][0, :]
        next_period_consumption = policy[period + 1][state_index][1, :]

        interpolation_func = interpolate.interp1d(
            next_period_wealth,
            next_period_consumption,
            bounds_error=False,
            fill_value="extrapolate",
            kind="linear",
        )
        next_period_consumption_interp[state_index, :] = interpolation_func(
            matrix_next_period_wealth
        ).flatten("F")

    return next_period_consumption_interp


def get_current_period_consumption(
    next_period_marginal_utility: np.ndarray,
    matrix_next_period_wealth: np.ndarray,
    matrix_marginal_wealth: np.ndarray,
    quad_weights: np.ndarray,
    params: pd.DataFrame,
    inv_marginal_utility_func: Callable,
) -> np.ndarray:
    """Computes consumption in the current period.

    Args:
        rhs_euler (np.ndarray): Right-hand side of the Euler equation.
            Shape (n_grid_wealth,).
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
        inv_marginal_utility_func (callable): Inverse of the marginal utility
            function.

    Returns:
        current_period_consumption (np.ndarray): Consumption in the current
            period. Array of shape (n_grid_wealth,).
    """
    beta = params.loc[("beta", "beta"), "value"]

    # RHS of Euler Eq., p. 337 IJRS (2017)
    # Integrate out uncertainty over stochastic income y
    rhs_euler = _calc_rhs_euler(
        next_period_marginal_utility,
        matrix_next_period_wealth,
        matrix_marginal_wealth,
        quad_weights,
    )

    current_period_consumption = inv_marginal_utility_func(beta * rhs_euler, params)

    return current_period_consumption


def get_expected_value(
    next_period_value: np.ndarray,
    matrix_next_period_wealth: np.ndarray,
    quad_weights: np.ndarray,
) -> np.ndarray:
    """Computes the expected value of the next period.

    Args:
        next_period_value (np.ndarray): Array containing values of next period
            choice-specific value function.
            Shape (n_choices, n_quad_stochastic * n_grid_wealth)
        matrix_next_period_wealth (np.ndarray): Array of all possible next period
            wealths with shape (n_quad_stochastic, n_grid_wealth).
        quad_weights (np.ndarray): Weights associated with the stochastic
            quadrature points of shape (n_quad_stochastic,).

    Returns:
        expected_value (np.ndarray): Array of current period's expected value of
            next_period. Shape (n_grid_wealth,).
    """
    expected_value = np.dot(
        quad_weights.T,
        next_period_value[0, :].reshape(matrix_next_period_wealth.shape, order="F"),
    )

    return expected_value


def _calc_stochastic_income(
    period: int, shock: float, params: pd.DataFrame, options
) -> float:
    """Computes the current level of deterministic and stochastic income.

    Note that income is paid at the end of the current period, i.e. after
    the (potential) labor supply choice has been made. This is equivalent to
    allowing income to be dependent on a lagged choice of labor supply.

    The agent starts working in period t = 0.
    Relevant for the wage equation (deterministic income) are age-dependent
    coefficients of work experience:

    labor_income = constant + alpha_1 * age + alpha_2 * age**2

    They include a constant as well as two coefficents on age and age squared,
    respectively. Note that the last one (alpha_2) typically has a negative sign.

    Args:
        period (int): Curent period t.
        shock (float): Stochastic shock on labor income, which may or may not
            be normally distributed.
        params (pd.DataFrame): Model parameters indexed with multi-index of the
            form ("category", "name") and two columns ["value", "comment"].
            Relevant here are the coefficients of the wage equation.
        options (dict): Options dictionary.

    Returns:
        stochastic_income (float): End of period income composed of a
            deterministic component, i.e. age-dependent labor income, and a
            stochastic shock.
    """
    # For simplicity, assume current_age - min_age = experience
    # TODO: Allow age and work experience to differ,
    # i.e. allow for unemployment spells
    min_age = options["min_age"]
    age = period + min_age

    # Determinisctic component of income depending on experience
    # labor_income = constant + alpha_1 * age + alpha_2 * age**2
    exp_coeffs = np.asarray(params.loc["wage", "value"])
    labor_income = exp_coeffs @ (age ** np.arange(len(exp_coeffs)))

    stochastic_income = np.exp(labor_income + shock)

    return stochastic_income


def _calc_rhs_euler(
    next_period_marginal_utility: np.ndarray,
    matrix_next_period_wealth: np.ndarray,
    matrix_marginal_wealth: np.ndarray,
    quad_weights: np.ndarray,
) -> np.ndarray:
    """Computes the right-hand side of the Euler equation, p. 337 IJRS (2017).

    Args:
        next_period_marginal_utility (np.ndarray): Array of next period's
            marginal utility of shape (n_quad_stochastic * n_grid_wealth,).
        matrix_next_period_wealth(np.ndarray): Array of all possible next
            period wealths. Shape (n_quad_stochastic, n_wealth_grid).
        matrix_marginal_wealth(np.ndarray): Array of marginal next period wealths.
            Shape (n_quad_stochastic, n_wealth_grid).
        quad_weights (np.ndarray): Weights associated with the quadrature points
            of shape (n_quad_stochastic,). Used for integration over the
            stochastic income component in the Euler equation.

    Returns:
        rhs_euler (np.ndarray): Right-hand side of the Euler equation.
            Shape (n_grid_wealth,).
    """
    next_period_marginal_utility = next_period_marginal_utility.reshape(
        matrix_next_period_wealth.shape, order="F"
    )

    rhs_euler = np.dot(
        quad_weights.T,
        np.multiply(next_period_marginal_utility, matrix_marginal_wealth),
    )

    return rhs_euler
