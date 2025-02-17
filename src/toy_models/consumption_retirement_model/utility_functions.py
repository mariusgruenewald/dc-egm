import jax.numpy as jnp


def utiility_func_log_crra(
    consumption: jnp.array, choice: int, params_dict: dict
) -> jnp.array:
    """Compute the agent's utility in case of theta equal to 1.

    Args:
        consumption (jnp.array): Level of the agent's consumption.
            Array of shape (i) (n_quad_stochastic * n_grid_wealth,)
            when called by :func:`~dcgm.call_egm_step.map_exog_to_endog_grid`
            and :func:`~dcgm.call_egm_step.get_next_period_value`, or
            (ii) of shape (n_grid_wealth,) when called by
            :func:`~dcgm.call_egm_step.get_current_period_value`.
        choice (int): Choice of the agent, e.g. 0 = "retirement", 1 = "working".
        params_dict (dict): Dictionary containing model parameters.
            Relevant here is the CRRA coefficient theta.

    Returns:
        utility (jnp.array): Agent's utility . Array of shape
            (n_quad_stochastic * n_grid_wealth,) or (n_grid_wealth,).

    """
    delta = params_dict["delta"]
    return jnp.log(consumption) - (1 - choice) * delta


def utility_func_crra(
    consumption: jnp.array, choice: int, params_dict: dict
) -> jnp.array:
    """Computes the agent's current utility based on a CRRA utility function.

    Args:
        consumption (jnp.array): Level of the agent's consumption.
            Array of shape (i) (n_quad_stochastic * n_grid_wealth,)
            when called by :func:`~dcgm.call_egm_step.map_exog_to_endog_grid`
            and :func:`~dcgm.call_egm_step.get_next_period_value`, or
            (ii) of shape (n_grid_wealth,) when called by
            :func:`~dcgm.call_egm_step.get_current_period_value`.
        choice (int): Choice of the agent, e.g. 0 = "retirement", 1 = "working".
        params_dict (dict): Dictionary containing model parameters.
            Relevant here is the CRRA coefficient theta.

    Returns:
        utility (jnp.array): Agent's utility . Array of shape
            (n_quad_stochastic * n_grid_wealth,) or (n_grid_wealth,).

    """
    theta = params_dict["theta"]
    delta = params_dict["delta"]

    utility_consumption = (consumption ** (1 - theta) - 1) / (1 - theta)

    utility = utility_consumption - (1 - choice) * delta

    return utility


def marginal_utility_crra(consumption: jnp.array, params_dict: dict) -> jnp.array:
    """Computes marginal utility of CRRA utility function.

    Args:
        consumption (jnp.array): Level of the agent's consumption.
            Array of shape (n_quad_stochastic * n_grid_wealth,).
        params_dict (dict): Dictionary containing model parameters.
            Relevant here is the CRRA coefficient theta.

    Returns:
        marginal_utility (jnp.array): Marginal utility of CRRA consumption
            function. Array of shape (n_quad_stochastic * n_grid_wealth,).

    """
    theta = params_dict["theta"]
    marginal_utility = consumption ** (-theta)

    return marginal_utility


def inverse_marginal_utility_crra(
    marginal_utility: jnp.array,
    params_dict: dict,
) -> jnp.array:
    """Computes the inverse marginal utility of a CRRA utility function.

    Args:
        marginal_utility (jnp.array): Level of marginal CRRA utility.
            Array of shape (n_grid_wealth,).
        params_dict (dict): Dictionary containing model parameters.

    Returns:
        inverse_marginal_utility(jnp.array): Inverse of the marginal utility of
            a CRRA consumption function. Array of shape (n_grid_wealth,).

    """
    theta = params_dict["theta"]
    inverse_marginal_utility = marginal_utility ** (-1 / theta)

    return inverse_marginal_utility
