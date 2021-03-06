# -*- coding: utf-8 -*-
"""
Simple 2D GridWorld MDP implementation

Based on the GridWorld from 'Algorithms for Inverse Reinforcement Learning'
by Ng and Russell, 2000

Copyright 2018 Aaron Snoswell
"""

import math
import copy
import numpy as np
import gym
from gym.utils import seeding
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from irl_methods.mdp.value_iteration import value_iteration


# Edge mode enum
EDGEMODE_CLAMP = 0
EDGEMODE_WRAP = 1
EDGEMODE_STRINGS = [
    "Clamped",
    "Wrapped"
]

# Syntax sugar helpers for actions
ACTION_NORTH = 0
ACTION_EAST = 1
ACTION_SOUTH = 2
ACTION_WEST = 3
ACTION_NOTHING = 4
ACTION_STRINGS = [
    "North",
    "East",
    "South",
    "West",
    "Nothing"
]

# Feature map enum
FEATUREMAP_COORD = 0
FEATUREMAP_IDENTITY = 1
FEATUREMAP_OTHER_DISTANCE = 2
FEATUREMAP_GOAL_DISTANCE = 3
FEATUREMAP_STRINGS = [
    "Coordinate",
    "Identity",
    "Other Distance",
    "Goal Distance"
]


class GridWorldDiscEnv(gym.Env):
    """A simple GridWorld MDP

    Based on the GridWorld described in 'Algorithms for Inverse Reinforcement
    Learning' by Ng and Russell, 2000
    """

    metadata = {
        'render.modes': ['human', 'ansi']
    }

    def __init__(
        self,
        *,
        size=5,
        wind=0.3,
        edge_mode=EDGEMODE_CLAMP,
        initial_state=(0, 0),
        goal_states=((4, 4),),
        per_step_reward=0,
        goal_reward=1
    ):
        """
        Constructor for the GridWorld environment

        NB: All methods and internal representations that work with GridWorld
        indices use an (x, y) coordinate system where +x is to the right and
        +y is up.

        @param size - The size of the grid world
        @param wind - The chance of a uniform random action being taken each
            step
        @param edge_mode - Edge of world behaviour, one of EDGEMODE_CLAMP or
            EDGEMODE_WRAP
        @param initial_state - Starting state as an (x, y) tuple for the agent
        @param goal_states - List of tuples of (x, y) goal states
        @param per_step_reward - Reward given every step
        @param goal_reward - Reward upon reaching the goal
        """

        assert edge_mode == EDGEMODE_WRAP \
               or edge_mode == EDGEMODE_CLAMP, \
            "Invalid edge_mode: {}".format(edge_mode)
        
        # Size of the gridworld
        self._size = size

        # Wind percentage (chance of moving randomly each step)
        self._wind = wind

        # Edge of world behaviour
        self._edge_mode = edge_mode

        # Set of states
        self._S = [
            (x, y) for y in range(self._size) for x in range(self._size)
        ]

        # Lambda to apply boundary condition to an x, y state
        self._apply_edge_mode = lambda x, y: (
                min(max(x, 0), self._size - 1) if
                (self._edge_mode == EDGEMODE_CLAMP)
                else x % size,
                min(max(y, 0), self._size - 1) if
                (self._edge_mode == EDGEMODE_CLAMP)
                else y % size,
            )

        # Lambda to get the state index of an x, y pair
        self._xy2s = lambda x, y: \
            math.floor(
                self._apply_edge_mode(x, y)[1] * size +
                self._apply_edge_mode(x, y)[0]
            )

        # Lambda to convert a state to an x, y pair
        self._s2xy = lambda s: (s % self._size, s // self._size)

        # Set of actions
        # NB: The y direction is inverted so that the numpy array layout, when
        # shown using print(), matches the 'up is up' expectation
        self._A = [
            # North
            (0, 1),

            # East
            (1, 0),

            # South
            (0, -1),

            # West
            (-1, 0),

            # Nothing
            (0, 0)
        ]

        # Transition matrix
        self.transition_tensor = np.zeros((
            len(self._S),
            len(self._A),
            len(self._S)
        ))

        # Loop over initial states
        for si, state in enumerate(self._S):

            # Get the initial state details
            x = state[0]
            y = state[1]

            # Loop over actions
            for ai, action in enumerate(self._A):

                # Get action details
                dx = action[0]
                dy = action[1]

                # Update probability for desired action
                self.transition_tensor[
                    si,
                    ai,
                    self._xy2s(x + dx, y + dy)
                ] += (1 - wind)

                # Update probability for stochastic alternatives
                for wind_action in self._A:

                    wind_dx = wind_action[0]
                    wind_dy = wind_action[1]

                    self.transition_tensor[
                        si,
                        ai,
                        self._xy2s(x + wind_dx, y + wind_dy)
                    ] += wind / len(self._A)

        # Gym action space object (index corresponds to entry in self._A list)
        self.action_space = gym.spaces.Discrete(len(self._A))

        # Gym observation space object (observations are an index indicating
        # the current state)
        self.observation_space = gym.spaces.Discrete(len(self._S))

        # Starting state
        self._initial_state = self._xy2s(*initial_state)
        self.state = self._initial_state

        # Goal states
        self._goal_states = [self._xy2s(*s) for s in goal_states]

        # Per step reward
        self._per_step_reward = per_step_reward

        # Goal reward
        self._goal_reward = goal_reward

        # Store true reward
        self.ground_truth_reward = np.array([
            self._per_step_reward + self._goal_reward
            if s in self._goal_states
            else self._per_step_reward
            for s in range(len(self._S))
        ])

        # Check if we're done or not
        self._done = lambda: self.state in self._goal_states

        # Members used for rendering
        self._fig = None
        self._ax = None
        self._goal_patches = None
        self._state_patch = None

        # Reset the MDP
        self.np_random = None
        self.seed()
        self.reset()

    def seed(self, seed=None):
        """
        Set the random seed for the environment
        """

        self.np_random, seed = seeding.np_random(seed)
        return [seed]

    def reset(self):
        """
        Reset the environment to it's initial state
        """

        self.state = self._initial_state

        return self.state

    def step(self, action):
        """
        Take one step in the environment
        """

        assert self.action_space.contains(action), \
            "%r (%s) invalid" % (action, type(action))

        # Sample subsequent state from transition matrix
        self.state = np.random.choice(
            range(len(self._S)),
            p=self.transition_tensor[self.state, action, :]
        )

        # Check if we're done or not
        done = self._done()

        # Compute reward
        reward = self._per_step_reward
        if done:
            reward += self._goal_reward 

        # As per the Gym.Env definition, return a (s, r, done, status) tuple
        return self.state, reward, done, {}

    def close(self):
        """Cleans up
        """
        if self._fig is not None:
            # Close our plot window
            plt.close(self._fig)

        self._fig = None
        self._ax = None
        self._goal_patches = None
        self._state_patch = None

    def render(self, mode="human"):
        """
        Render the environment
        """

        assert mode in self.metadata["render.modes"], "Invalid render mode"

        if mode == "ansi":
            # Render the gridworld text at the console
            # We draw goal states as '$', and the current state as '@'
            # We also draw boundaries around the world as '#' if the edge mode
            # is clamp, or '+' if the edge mode is wrap

            ret = ""

            edge_symbol = "#" if self._edge_mode == EDGEMODE_CLAMP else "+"

            # Add top boundary
            ret += edge_symbol * (self._size + 2) + "\n"

            # Iterate over grid
            for y in range(self._size-1, -1, -1):

                # Add left boundary
                ret += edge_symbol

                # Draw gridworld objects
                for x in range(self._size):
                    s = self._xy2s(x, y)
                    if s == self.state:
                        ret += "@"
                    elif s in self._goal_states:
                        ret += "$"
                    else:
                        ret += " "

                # Add right boundary
                ret += edge_symbol

                # Add newline
                ret += "\n"

            # Add bottom boundary
            ret += edge_symbol * (self._size + 2)

            return ret

        elif mode == "human":
            # Render using a GUI

            cell_size = 1/self._size
            s2coord = lambda s: np.array(self._s2xy(s)) / self._size + \
                                (cell_size/2, cell_size/2)

            if self._fig is None:
                self._fig = plt.figure()
                self._ax = self._fig.gca()

                # Render common elements
                self.configure_plot(self._ax)

                # Render the current position
                self._state_patch = mpatches.Circle(
                    s2coord(self.state),
                    0.025,
                    color="blue",
                    ec=None
                )
                self._ax.add_patch(self._state_patch)

            else:
                # We assume a stationary goal
                self._state_patch.center = np.array(s2coord(self.state))
                self._fig.canvas.draw()

            # Show the rendered GridWorld
            if self._done():
                # Plot and block
                plt.show()
            else:
                # Plot without blocking
                plt.pause(0.25)

            return None

        else:

            # Let super handle it
            super(GridWorldDiscEnv, self).render(mode=mode)

    def configure_plot(self, ax, *, line_color="#dddddd", render_goals=True):
        """Helper method to configure matplotlib axes, draw common elements

        Args:
            ax (matplotlib.axes.Axes): Axes to render to
            line_color (string): Line color
            render_goals (bool): Draw patches to indicate the goal position(s)
        """

        cell_size = 1/self._size
        s2coord = lambda s: np.array(self._s2xy(s)) / self._size + \
                            (cell_size / 2, cell_size / 2)

        # Render the goal patch(es)
        if render_goals:
            for g in self._goal_states:
                goal_patch = mpatches.Rectangle(
                    s2coord(g) - (cell_size/2, cell_size/2),
                    cell_size,
                    cell_size,
                    color="green",
                    alpha=0.5,
                    ec=None
                )
                ax.add_patch(goal_patch)

        # Render a grid
        line_width = 0.75
        for i in [x / self._size for x in range(self._size)]:
            ax.add_artist(plt.Line2D(
                (0, 1),
                (i, i),
                color=line_color,
                linewidth=line_width
            ))
            ax.add_artist(plt.Line2D(
                (i, i),
                (0, 1),
                color=line_color,
                linewidth=line_width
            ))

        # Set title
        ax.set_title(
            "Discrete {} GridWorld, wind = {}".format(
                EDGEMODE_STRINGS[self._edge_mode],
                self._wind
            )
        )

        # Set aspect
        ax.set_aspect(1, adjustable="box")

        # Configure x-axis
        ax.set_xlim([0, 1])
        ax.set_xticks(
            [s / self._size + cell_size / 2 for s in range(self._size)]
        )
        ax.set_xticklabels(
            [str(s + 1) for s in range(self._size)]
        )
        ax.xaxis.set_tick_params(size=0)

        # Configure y-axis
        ax.set_ylim([0, 1])
        ax.set_yticks(
            [s / self._size + cell_size / 2 for s in range(self._size)]
        )
        ax.set_yticklabels(
            [str(s + 1) for s in range(self._size)]
        )
        ax.yaxis.set_tick_params(size=0)

    def plot_reward(self, ax, rewards, *, r_min=None, r_max=None):
        """Plots a given reward (or value) vector

        Args:
            ax (matplotlib.axes.Axes): Axes to render to
            rewards (numpy array): Numpy array of rewards for each state index

            r_min (float): Minimum reward - used for color map scaling. None to
                infer from reward map.
            r_max (float): Maximum reward - used for color map scaling. None to
                infer from reward map.
        """

        # Set up plot
        self.configure_plot(ax, line_color="#666666", render_goals=False)

        y, x = np.mgrid[0:self._size+1, 0:self._size+1] / self._size
        z = np.reshape(rewards, (self._size, self._size))
        plt.pcolormesh(
            x,
            y,
            z,
            vmin=r_min,
            vmax=r_max
        )

    def plot_policy(self, ax, policy):
        """Plots a given policy function

        Args:
            ax (matplotlib.axes.Axes): Axes to render to
            policy (function): Policy p(s) -> a mapping state indices to actions
        """

        # Set up plot
        self.configure_plot(ax)

        # y, x = np.mgrid[0:self._size + 1, 0:self._size + 1] / self._size
        # u = np.zeros(shape=(self._size, self._size))
        # v = np.zeros(shape=(self._size, self._size))
        #
        # for state in range(len(self._S)):
        #     x, y = self._s2xy(state)


        cell_size = 1/self._size
        X, Y = np.mgrid[0:self._size, 0:self._size] / self._size + (cell_size/2)

        U = np.zeros(shape=X.shape)
        V = np.zeros(shape=X.shape)

        for x, y in list(zip(np.reshape(X, (-1,)), np.reshape(Y, (-1,)))):

            # Convert to x, y coordinate
            x_coord = math.floor(x * self._size)
            y_coord = math.floor(y * self._size)

            # Convert to state
            state = self._xy2s(x_coord, y_coord)

            # Get action from policy and convert to a delta
            action = policy(state)
            dx, dy = 0, 0
            if action == ACTION_NORTH:
                dy = 1
            elif action == ACTION_EAST:
                dx = 1
            elif action == ACTION_SOUTH:
                dy = -1
            elif action == ACTION_WEST:
                dx = -1

            U[x_coord, y_coord] = dx
            V[x_coord, y_coord] = dy

        plt.quiver(
            X,
            Y,
            U,
            V,
            pivot="mid",
            edgecolor="black",
            facecolor="white",
            linewidth=0.25
        )

    def get_state_features(self, *, s=None, feature_map=FEATUREMAP_COORD):
        """Returns a feature vector for the given state

        Args:
            s (int): State integer, or None to use the current state
            feature_map (int): Feature map to use. One of FEATURE_MAP_*
                defined at the top of this module

        Returns:
            (numpy array): Feature vector for the given state
        """

        s = s if s is not None else self.state

        if feature_map == FEATUREMAP_COORD:
            # Features are (x, y) coordinate tuples
            return np.array(self._s2xy(s))

        elif feature_map == FEATUREMAP_IDENTITY:
            # Features are zero arrays with a 1 indicating the location of
            # the state
            f = np.zeros(len(self._S))
            f[s] = 1
            return f

        elif feature_map == FEATUREMAP_OTHER_DISTANCE:
            # Features are an array indicating the L0 / manhattan distance to
            # each other state
            f = np.zeros(len(self._S))
            x0, y0 = self._s2xy(s)
            for other_state in range(len(self._S)):
                x, y = self._s2xy(other_state)
                f[other_state] = abs(x0 - x) + abs(y0 - y)
            return f

        elif feature_map == FEATUREMAP_GOAL_DISTANCE:
            # Features are an array indicating the L0 / manhattan distance to
            # each goal
            f = np.zeros(len(self._goal_states))
            x0, y0 = self._s2xy(s)
            for i, goal_state in enumerate(self._goal_states):
                x, y = self._s2xy(goal_state)
                f[i] = abs(x0 - x) + abs(y0 - y)
            return f

        else:
            assert False, "Invalid feature map: {}".format(feature_map)

    def get_optimal_policy(self):
        """Returns an optimal policy function for this MDP

        Returns:
            (function): An optimal policy p(s) -> a that maps states to
                actions
        """

        # Collect goal states as (x, y) indices
        _goal_states = [self._s2xy(g) for g in self._goal_states]

        # If we're in a wrapping gridworld, the nearest goal could outside the
        # world bounds. Add virtual goals to help the policy account for this
        if self._edge_mode == EDGEMODE_WRAP:
            for i in range(len(self._goal_states)):
                g = np.array(self._s2xy(self._goal_states[i]))
                _goal_states.append(tuple(g - (self._size, self._size)))
                _goal_states.append(tuple(g - (0, self._size)))
                _goal_states.append(tuple(g - (self._size, 0)))
                _goal_states.append(tuple(g + (self._size, self._size)))
                _goal_states.append(tuple(g + (0, self._size)))
                _goal_states.append(tuple(g + (self._size, 0)))

        def policy(state):
            """A simple expert policy to solve the continuous gridworld
            problem

            Args:
                state (tuple): The current MDP state integer

            Returns:
                (int): One of the ACTION_* globals defined in this module
            """

            # Pick the nearest goal
            nearest_goal = None

            if len(_goal_states) == 1:
                # We only have one goal to consider
                nearest_goal = _goal_states[0]

            else:
                # Find the nearest goal - it could be behind us
                smallest_distance = math.inf
                for g in _goal_states:
                    distance = np.linalg.norm(np.array(g) - self._s2xy(state))
                    if distance < smallest_distance:
                        smallest_distance = distance
                        nearest_goal = g

            # Find the distance to the goal
            dx, dy = np.array(nearest_goal) - self._s2xy(state)

            # If we're at the goal, do nothing
            if dx == dy == 0:
                return ACTION_NOTHING

            direction = None
            if abs(dx) == abs(dy):
                # x and y distances are equal - flip a coin to avoid bias in
                # the policy
                if np.random.uniform() > 0.5:
                    # Move vertically
                    direction = "horizontally"
                else:
                    # Move horizontally
                    direction = "vertically"

            if abs(dx) > abs(dy):
                # We need to move horizontally more than vertically
                direction = "horizontally"
            else:
                # We need to move vertically more than horizontally
                direction = "vertically"

            # Compute the actual movement
            if direction == "horizontally":
                return ACTION_EAST if dx > 0 \
                    else ACTION_WEST
            else:
                return ACTION_NORTH if dy > 0 \
                    else ACTION_SOUTH

        return policy

    def get_ordered_transition_tensor(self, policy):
        """Computes a sorted transition matrix for the GridWorld MDP

        Given a policy, defined as a function pi(s) -> a taking state
        integers and returning action integers, computes a sorted transition
        matrix T[s, a, s'] such that the 0th action corresponds to the
        policy's action, and the ith action (i!=0) corresponds to the ith
        non-policy action, for some arbitrary but consistent ordering of
        actions.

        Args:
            policy (function) - Expert policy 'a1' as a function pi(s) -> a

        Returns:
            (numpy array): A sorted transition matrix T[s, a, s'], where the
            0th action T[:, 0, :] corresponds to following the expert policy,
            and the other action entries correspond to the remaining action
            options, sorted according to the ordering in self._A
        """

        transitions_sorted = copy.copy(self.transition_tensor)
        for y in range(self._size):
            for x in range(self._size):

                si = self._xy2s(x, y)
                action = policy(si)

                if action == ACTION_NORTH:
                    # Expert chooses north
                    # North is already first in the GridWorldEnv._A ordering
                    pass
                elif action == ACTION_EAST:
                    # Expert chooses east
                    tmp = transitions_sorted[si, 0, :]
                    transitions_sorted[si, 0, :] = transitions_sorted[si, 1, :]
                    transitions_sorted[si, 1, :] = tmp
                elif action == ACTION_SOUTH:
                    # Expert chooses south
                    tmp = transitions_sorted[si, 0:1, :]
                    transitions_sorted[si, 0, :] = transitions_sorted[si, 2, :]
                    transitions_sorted[si, 1:2, :] = tmp
                elif action == ACTION_WEST:
                    # Expert chooses west
                    tmp = transitions_sorted[si, 0:2, :]
                    transitions_sorted[si, 0, :] = transitions_sorted[si, 3, :]
                    transitions_sorted[si, 1:3, :] = tmp
                else:
                    # Expert doesn't care / does nothing
                    pass

        return transitions_sorted

    def estimate_value(
            self,
            policy,
            discount,
            *,
            reward=None,
            tol=1e-6,
            max_iterations=float("inf")
    ):
        """Estimate the value of a policy over this GridWorld

        Args:
            policy (function): Policy pi(s) -> a
            discount (float): Discount factor

            reward (function): Alternate reward function to use. None to use
                default.
            tol (float): Convergence tolerance
            max_iterations (int): Maximum number of iterations

        Returns:
            (numpy array): Value vector v[s] -> float mapping states to
                estimated values, found using value iteration under the given
                policy
        """

        reward = reward if reward is not None else \
            lambda s: self.ground_truth_reward[s]

        return value_iteration(
            range(len(self._S)),
            self.transition_tensor,
            policy,
            reward,
            discount,
            tol=tol,
            max_iterations=max_iterations
        )

    def greedy_policy(self, value_vector):
        """Get policy that is greedy with respect to a value vector

        Args:
            value_vector (numpy array): Numpy array of values for each state

        Returns:
            (function): Policy function pi(s) -> a mapping states to actions
        """

        def greedy_policy(s):
            """Greedy policy function

            Args:
                s (any): Current state

            Returns:
                (any): New action
            """
            # Try each possible action and see what value we get in the next
            # state

            next_state_values = []
            for action in range(len(self._A)):
                self.reset()
                self.state = s
                s, r, d, i = self.step(action)
                next_state_values.append(value_vector[s])

            # Act greedily
            return next_state_values.index(max(next_state_values))

        return greedy_policy


class GridWorldCtsEnv(gym.Env):
    """A continuous GridWorld MDP

    Based on the GridWorld described in 'Algorithms for Inverse Reinforcement
    Learning' by Ng and Russell, 2000
    """

    metadata = {
        'render.modes': ['human']
    }

    def __init__(
            self,
            *,
            action_distance=0.2,
            wind_range=0.1,
            edge_mode=EDGEMODE_CLAMP,
            initial_state=(0.1, 0.1),
            goal_range=((0.8, 0.8), (1, 1)),
            per_step_reward=0,
            goal_reward=1
    ):
        """Constructor for the GridWorld environment

        NB: All methods and internal representations that work with GridWorld
        coordinates use an (x, y) coordinate system where +x is to the right and
        +y is up.
        """

        assert edge_mode == EDGEMODE_WRAP \
               or edge_mode == EDGEMODE_CLAMP, \
            "Invalid edge_mode: {}".format(edge_mode)

        # How far one step takes the agent
        self._action_distance = action_distance

        # Wind range (how far the wind can push the user each time step)
        self._wind_range = wind_range

        # Edge of world behaviour
        self._edge_mode = edge_mode

        # Set of actions
        self._A = [
            # North
            (0, 1),

            # East
            (1, 0),

            # South
            (0, -1),

            # West
            (-1, 0),

            # Nothing
            (0, 0)
        ]

        # Gym action space object (index corresponds to entry in self._A list)
        self.action_space = gym.spaces.Discrete(len(self._A))

        # Gym observation space object
        self.observation_space = gym.spaces.Box(
            low=np.array((0, 0)),
            high=np.array((1, 1)),
            dtype=float
        )

        # Starting state
        self._initial_state = initial_state
        self.state = self._initial_state

        # Goal state
        self._goal_space = gym.spaces.Box(
            low=np.array(goal_range[0]),
            high=np.array(goal_range[1]),
            dtype=float
        )

        # Per step reward
        self._per_step_reward = per_step_reward

        # Goal reward
        self._goal_reward = goal_reward

        # Ground truth reward function
        self.ground_truth_reward = lambda s: self._per_step_reward + \
            (self._goal_reward if self._goal_space.contains(np.array(s)) else 0)

        # Check if we're done or not
        self._done = lambda: self._goal_space.contains(np.array(self.state))

        # Members used for rendering
        self._fig = None
        self._ax = None
        self._goal_patch = None
        self._state_patch = None

        # Reset the MDP
        self.np_random = None
        self.seed()
        self.reset()

    def seed(self, seed=None):
        """
        Set the random seed for the environment
        """

        self.np_random, seed = seeding.np_random(seed)
        return [seed]

    def reset(self):
        """
        Reset the environment to it's initial state
        """

        self.state = self._initial_state

        return self.state

    def step(self, action):
        """Take one step in the environment

        Args:
            action (int): Action index
        """

        assert self.action_space.contains(action), \
            "%r (%s) invalid" % (action, type(action))

        # Copy current state
        new_state = np.array(self.state, dtype=float)

        # Apply user action
        new_state += np.array(self._A[action]) * self._action_distance

        # Apply wind
        new_state += np.random.uniform(
            low=-self._wind_range,
            high=self._wind_range,
            size=2
        )

        # Apply boundary condition
        if self._edge_mode == EDGEMODE_WRAP:
            self.state = np.array(tuple(new_state % 1.0))

        else:
            self.state = np.array(
                tuple(
                    map(
                        lambda a: min(max(0, a), 1),
                        new_state
                    )
                )
            )

        # Check done-ness
        done = self._done()

        # Compute reward
        reward = self._per_step_reward
        if done:
            reward += self._goal_reward

        # As per the Gym.Env definition, return a (s, r, done, status) tuple
        return self.state, reward, done, {}

    def close(self):
        """Cleans up
        """
        if self._fig is not None:
            # Close our plot window
            plt.close(self._fig)

        self._fig = None
        self._ax = None
        self._goal_patch = None
        self._state_patch = None

    def render(self, mode='human'):
        """Render the environment
        """

        if mode == "human":
            # Render using a GUI

            if self._fig is None:
                self._fig = plt.figure()
                self._ax = self._fig.gca()

                # Configure plot
                self.configure_plot(self._ax)

                # Render the current position
                self._state_patch = mpatches.Circle(
                    self.state,
                    0.025,
                    color="blue",
                    ec=None
                )
                self._ax.add_patch(self._state_patch)

            else:
                # We assume a stationary goal
                self._state_patch.center = self.state
                self._fig.canvas.draw()

            # Show the rendered GridWorld
            if self._done():
                # Plot and block
                plt.show()
            else:
                # Plot without blocking
                # plt.show(
                #     block=False
                # )
                plt.pause(0.25)

            return None

        else:
            # Let super handle it
            super(GridWorldCtsEnv, self).render(mode=mode)

    def configure_plot(self, ax, *, render_goal=True):
        """Helper method to configure matplotlib axes, draw common elements

        Args:
            ax (matplotlib.axes.Axes): Axes to render to

            render_goal (bool): Draw patch to indicate the goal space
        """

        # Render the goal patch
        if render_goal:
            goal_patch = mpatches.Rectangle(
                self._goal_space.low,
                self._goal_space.high[0] - self._goal_space.low[0],
                self._goal_space.high[1] - self._goal_space.low[1],
                color="green",
                alpha=0.5,
                ec=None
            )
            ax.add_patch(goal_patch)

        # Set title
        ax.set_title(
            "Continuous {} GridWorld, wind = {}".format(
                EDGEMODE_STRINGS[self._edge_mode],
                self._wind_range
            )
        )

        # Configure axes
        ax.set_aspect(1, adjustable="box")
        ax.set_xlim([0, 1])
        ax.xaxis.set_tick_params(size=0)
        ax.set_ylim([0, 1])
        ax.yaxis.set_tick_params(size=0)

    def plot_reward(
            self,
            ax,
            reward_fn,
            *,
            r_min=None,
            r_max=None,
            resolution=10):
        """Rasters a given reward function

        Args:
            ax (matplotlib.axes.Axes): Axes to render to
            reward_fn (function): Reward function r(s) -> float

            r_min (float): Minimum reward or None to infer from rasterisation.
                Used for color map scaling.
            r_max (float): Maximum reward or None to infer from rasterisation.
                Used for color map scaling.
            resolution (int): Raster resolution width/height
        """

        # Set up plot
        self.configure_plot(ax, render_goal=False)

        y, x = np.mgrid[0:resolution+1, 0:resolution+1] / resolution
        z = np.zeros(shape=(resolution, resolution))
        for yi in range(resolution):
            for xi in range(resolution):
                state = np.array((
                    xi/resolution + (1/resolution)/2,
                    yi/resolution + (1/resolution)/2
                ))
                z[yi, xi] = reward_fn(state)

        plt.pcolormesh(
            x,
            y,
            z,
            vmin=r_min,
            vmax=r_max
        )

    def plot_policy(self, ax, policy, *, resolution=10):
        """Plots a given policy function as quiver plot

        Args:
            ax (matplotlib.axes.Axes): Axes to render to
            policy (function): Policy p(s) -> a mapping state indices to actions

            resolution (int): Resolution to use when drawing policy vector field
        """

        # Set up plot
        self.configure_plot(ax)

        cell_size = 1/resolution
        x, y = np.mgrid[0:resolution, 0:resolution] / resolution + (cell_size/2)
        u = np.zeros(shape=x.shape)
        v = np.zeros(shape=x.shape)

        for sx, sy in list(zip(
                np.reshape(x, (-1,)),
                np.reshape(y, (-1,))
        )):

            # Convert to x, y coordinate
            x_coord = math.floor(sx * resolution)
            y_coord = math.floor(sy * resolution)

            # Get action from policy and convert to a delta
            state = np.array((sx, sy))
            action = policy(state)
            dx, dy = 0, 0
            if action == ACTION_NORTH:
                dy = 1
            elif action == ACTION_EAST:
                dx = 1
            elif action == ACTION_SOUTH:
                dy = -1
            elif action == ACTION_WEST:
                dx = -1

            u[x_coord, y_coord] = dx
            v[x_coord, y_coord] = dy

        plt.quiver(
            x,
            y,
            u,
            v,
            pivot="mid",
            edgecolor="black",
            facecolor="white",
            linewidth=0.24
        )

    def plot_trajectories(self, ax, trajectories, *, line_width=0.3, alpha=0.3):
        """Plots a collection of (s, a) trajectories

        TODO ajs 11/Jun/2018 Draw border intercept points when a trajectory
        crosses the x=0, x=1, y=0 or y=1 lines

        Args:
            ax (matplotlib.axes.Axes): Axes to render to
            trajectories (list): List of (s, a) trajectories

            line_width (float): Line width for trajectories
            alpha (float): Opacity for trajectories
        """

        # Float comparison epsillon
        eps = 1e-6

        # Set up plot
        self.configure_plot(ax)

        # Loop over trajectories
        for trajectory in trajectories:

            # Extract just the states
            state_trajectory = [sa[0] for sa in trajectory]
            action_trajectory = [sa[1] for sa in trajectory]

            # Determine if this trajectory was successful or not
            success = self._goal_space.contains(state_trajectory[-1])
            color = "C0" if success else "r"

            # Slice the trajectory up into chunks whenever it goes off the
            # edge of a wrapping gridworld
            chunks = []
            if self._edge_mode == EDGEMODE_WRAP:

                current_chunk = []

                for i, states in enumerate(
                        zip(state_trajectory[0:-1], state_trajectory[1:])
                ):
                    # Get states
                    s0 = states[0]
                    s1 = states[1]
                    action = action_trajectory[i]
                    dx, dy = 0, 0
                    if action == ACTION_NORTH:
                        dy = self._action_distance
                    elif action == ACTION_EAST:
                        dx = self._action_distance
                    elif action == ACTION_SOUTH:
                        dy = -self._action_distance
                    elif action == ACTION_WEST:
                        dx = -self._action_distance

                    # Add current state to chunk
                    current_chunk.append(s0)

                    x0, y0 = s0
                    delta = s1 - (s0 + (dx, dy))
                    dist = np.linalg.norm(delta)
                    if dist > 2 * self._wind_range + eps:
                        # This step was longer than possible given the wind and
                        # step size settings - assume the trajectory went off
                        # the edge of the map and split the trajectory here

                        chunks.append(current_chunk)
                        current_chunk = []

                # Add the final state and final chunk
                current_chunk.append(state_trajectory[-1])
                chunks.append(current_chunk)

            else:

                chunks.append(state_trajectory)

            # Draw all trajectory chunks
            for chunk in chunks:
                plt.plot(
                    np.array(chunk)[:, 0],
                    np.array(chunk)[:, 1],
                    color + "-",
                    linewidth=line_width,
                    alpha=alpha
                )

            # Highlight start point
            plt.plot(
                state_trajectory[0][0],
                state_trajectory[0][1],
                color + ".",
                alpha=alpha
            )

    def get_state_features(self, *, s=None, feature_map=FEATUREMAP_COORD):
        """Returns a feature vector for the given state

        Args:
            s (numpy array): State as a numpy array, or None to use the
                current state
            feature_map (string): Feature map to use. One of
                FEATUREMAP_COORD or FEATUREMAP_GOAL_DISTANCE

        Returns:
            (numpy array): Feature vector for the given state
        """

        s = s if s is not None else self.state

        if feature_map == FEATUREMAP_COORD:
            # Features are (x, y) coordinate tuples
            return np.array(s)

        elif feature_map == FEATUREMAP_GOAL_DISTANCE:
            # Feature is a value indicating the distance to the goal
            return np.linalg.norm(
                self._goal_space.low + self._goal_space.high - s
            )

        else:
            assert False, "Invalid feature map: {}".format(feature_map)

    def get_optimal_policy(self):
        """Returns an optimal policy function for this MDP

        Returns:
            (function): An optimal policy p(s) -> a that maps states to
                actions
        """

        goal_width, goal_height = np.abs(
            self._goal_space.high - self._goal_space.low
        )

        # Compute goal location
        goal_positions = [np.mean(
            np.vstack(
                (
                    self._goal_space.low,
                    self._goal_space.high
                )
            ),
            axis=0
        )]

        # If we're in a wrapping gridworld, the nearest goal could outside the
        # world bounds. Add virtual goals to help the policy account for this
        if self._edge_mode == EDGEMODE_WRAP:
            goal_positions.append(
                goal_positions[0] - (1, 1)
            )
            goal_positions.append(
                goal_positions[0] - (1, 0)
            )
            goal_positions.append(
                goal_positions[0] - (0, 1)
            )
            goal_positions.append(
                goal_positions[0] + (1, 1)
            )
            goal_positions.append(
                goal_positions[0] + (1, 0)
            )
            goal_positions.append(
                goal_positions[0] + (0, 1)
            )

        def policy(state):
            """A simple expert policy to solve the continuous gridworld
            problem

            Args:
                state (tuple): The current MDP state as an (x, y) tuple of
                    float

            Returns:
                (int): One of the ACTION_* globals defined in this module
            """

            # If we're at the goal, do nothing
            if self._goal_space.contains(np.array(state)):
                return ACTION_NOTHING

            # Pick the nearest goal
            nearest_goal = None

            if len(goal_positions) == 1:
                # We only have one goal to consider
                nearest_goal = goal_positions[0]

            else:
                # Find the nearest goal - it could be behind us
                smallest_distance = math.inf
                for g in goal_positions:
                    distance = np.linalg.norm(np.array(g) - state)
                    if distance < smallest_distance:
                        smallest_distance = distance
                        nearest_goal = g

            # Find the distance to the goal
            dx, dy = np.array(nearest_goal) - state

            if abs(dx) > abs(dy):
                # We need to move horizontally more than vertically
                return ACTION_EAST if dx > 0 \
                    else ACTION_WEST

            else:
                # We need to move vertically more than horizontally
                return ACTION_NORTH if dy > 0 \
                    else ACTION_SOUTH

        return policy

    def get_ordered_transition_function(self, policy):
        """Computes a sorted transition function for the GridWorld MDP

        Given a policy, defined as a function pi(s) -> a taking state
        integers and returning action integers, computes a sorted transition
        function T(s, a_i) -> s' such that the 0th action corresponds to the
        policy's action, and the ith action (i!=0) corresponds to the ith
        non-policy action, for some arbitrary but consistent ordering of
        actions.

        Args:
            policy (function) - Expert policy 'a1' as a function pi(s) -> a

        Returns:
            (function): A sorted transition function T(s, a_i) -> s', where the
            0th action T(:, 0) corresponds to following the expert policy,
            and the other action entries correspond to the remaining action
            options, sorted according to the ordering in self._A
        """

        def _T(s, a_i):
            """sorted transition function T(s, a_i) -> s'

            Args:
                s (int): State index
                a_i: Action index, where 0 corresponds to following the
                    expert policy

            Returns:
                (int): New state index
            """

            # Get expert action
            action = policy(s)

            # Re-order the list of possible actions
            all_actions = list(range(len(self._A)))
            all_actions.remove(action)
            all_actions.insert(0, action)

            # We actually take the ith action
            actual_action = all_actions[a_i]

            self.reset()
            self.state = s
            s, r, done, _ = self.step(actual_action)

            return s

        return _T

    def estimate_value(
            self,
            policy,
            discount,
            *,
            reward=None,
            resolution=10,
            transition_samples=100,
            tol=1e-6
    ):
        """Estimate the value of a policy over this GridWorld by discretisation

        Args:
            policy (function): Policy pi(s) -> a
            discount (float): Discount factor *in continuous space*

            reward (function): Alternate reward function to use. None to use
                default.
            resolution (int): Width/height of the discretisation to use
            transition_samples (int): Number of transition samples to use
                when estimated discrete transition matrix. If wind is 0,
                can be 1.
            tol (float): Convergence tolerance

        Returns:
            (numpy array): Value function v(s) -> float mapping states to
                approximate values, found using value iteration under the given
                policy over a discretised version of this gridworld
        """

        reward = reward if reward is not None else self.ground_truth_reward

        # Discretisation conversion lambdas
        index2xy = lambda i: np.array((
            (i % resolution)/resolution + (1/resolution)*0.5,
            (i // resolution)/resolution + (1/resolution)*0.5
        ))
        xy2index = lambda x, y: \
            int(max(min(y * resolution, resolution - 1), 0)) * resolution + \
            int(max(min(x * resolution, resolution - 1), 0))

        # Discretised state set
        num_states = resolution * resolution
        states = range(num_states)

        # Naïvely compute discretised transition tensor
        transition_tensor = np.zeros((
            num_states,
            len(self._A),
            num_states
        ), dtype=float)
        for start_state in states:
            for a in range(len(self._A)):
                for sample in range(transition_samples):
                    self.reset()
                    self.state = index2xy(start_state)
                    end_state, r, done, _ = self.step(a)
                    transition_tensor[start_state, a, xy2index(*end_state)] += 1

                # Normalise probabilities
                transition_tensor[start_state, a, :] /= transition_samples


        # Wrap policy with reverse-discretisation
        undiscretised_policy = lambda s: policy(index2xy(s))

        # Wrap reward with reverse-discretisation
        undiscretised_reward = lambda s: reward(index2xy(s))

        # Convert continuous discount to approximate discrete discount
        step_size = self._action_distance
        cell_size = 1 / resolution
        discount_disc = discount ** (cell_size / step_size)

        # Perform VI
        values = value_iteration(
            states,
            transition_tensor,
            undiscretised_policy,
            undiscretised_reward,
            discount_disc,
            tol=tol
        )

        # Reset MDP
        self.reset()

        # Wrap value function in discretisation
        return lambda s: values[xy2index(*s)]


def demo():
    """Simple example of how to use these classes
    """

    from mpl_toolkits.axes_grid1 import make_axes_locatable

    # Truncate numpy float decimal points
    np.set_printoptions(formatter={'float': lambda x: "{0:0.3f}".format(x)})

    # Exercise discrete gridworld
    print("Testing discrete GridWorld...")
    size = 5
    per_step_reward = -1
    goal_reward = 1
    gw_disc = GridWorldDiscEnv(
        size=size,
        per_step_reward=per_step_reward,
        goal_reward=goal_reward
    )
    policy = gw_disc.get_optimal_policy()

    print("Ordered transition matrix:")
    t_ordered = gw_disc.get_ordered_transition_tensor(policy)
    print(t_ordered)

    # Choose a feature map to use
    feature_map = FEATUREMAP_COORD
    print("Using feature map {}".format(FEATUREMAP_STRINGS[feature_map]))

    print(gw_disc.render(mode="ansi"))
    gw_disc.render(mode="human")
    reward = 0
    while True:
        action = policy(gw_disc.state)
        print("Observed f={}, taking action a={}".format(
            gw_disc.get_state_features(feature_map=feature_map),
            ACTION_STRINGS[action]
        ))
        s, r, done, status = gw_disc.step(action)
        print("Got reward {}".format(r))
        reward += r
        print(gw_disc.render(mode="ansi"))
        gw_disc.render(mode="human")

        if done:
            break

    gw_disc.close()
    print("Done, total reward = {}".format(reward))

    discount = 0.9
    disc_value_matrix = gw_disc.estimate_value(policy, discount)
    print("Estimated value function with discount={}:".format(discount))
    print(np.flipud(np.reshape(disc_value_matrix, (size, size))))

    fig = plt.figure()
    ax = plt.subplot(1, 2, 1)
    gw_disc.plot_reward(ax, gw_disc.ground_truth_reward)
    plt.title("Reward")
    plt.colorbar(
        cax=make_axes_locatable(ax).append_axes("right", size="5%", pad=0.05)
    )

    ax = plt.subplot(1, 2, 2)
    gw_disc.plot_reward(ax, disc_value_matrix)
    plt.title("Estimated value function")
    plt.colorbar(
        cax=make_axes_locatable(ax).append_axes("right", size="5%", pad=0.05)
    )
    plt.show()

    # Exercise cts gridworld
    print("Testing continuous GridWorld...")
    per_step_reward = -1
    goal_reward = 1
    gw_cts = GridWorldCtsEnv(
        per_step_reward=per_step_reward,
        goal_reward=goal_reward
    )
    policy = gw_cts.get_optimal_policy()

    # Choose a feature map to use
    feature_map = FEATUREMAP_COORD
    print("Using feature map {}".format(FEATUREMAP_STRINGS[feature_map]))

    gw_cts.render()
    reward = 0
    while True:
        action = policy(gw_cts.state)
        print("Observed f={}, taking action a={}".format(
            gw_cts.get_state_features(feature_map=feature_map),
            ACTION_STRINGS[action]
        ))
        s, r, done, status = gw_cts.step(action)
        print("Got reward {}".format(r))
        reward += r
        gw_cts.render()

        if done:
            break

    gw_cts.close()
    print("Done, total reward = {}".format(reward))

    discount = 0.9
    resolution = 10
    value_fn = gw_cts.estimate_value(
        policy,
        discount,
        resolution=resolution
    )
    cts_value_matrix = np.array([
        value_fn((
            x/resolution + (1/resolution)*0.5,
            y/resolution + (1/resolution)*0.5
        ))
        for y in range(resolution)
        for x in range(resolution)
    ])
    print("Estimated value function with discount={}, resolution={}:".format(
        discount,
        resolution
    ))
    print(np.flipud(np.reshape(cts_value_matrix, (resolution, resolution))))

    fig = plt.figure()
    ax = plt.subplot(1, 2, 1)
    gw_cts.plot_reward(
        ax,
        gw_cts.ground_truth_reward,
        r_min=per_step_reward,
        r_max=per_step_reward+goal_reward
    )
    plt.title("Reward")
    plt.colorbar(
        cax=make_axes_locatable(ax).append_axes("right", size="5%", pad=0.05)
    )

    ax = plt.subplot(1, 2, 2)
    gw_cts.plot_reward(
        fig.gca(),
        value_fn,
        r_min=min(cts_value_matrix),
        r_max=max(cts_value_matrix)
    )
    plt.title("Estimated value function")
    plt.colorbar(
        cax=make_axes_locatable(ax).append_axes("right", size="5%", pad=0.05)
    )
    plt.show()

    # Test trajectory rendering on a wrapping gridworld
    gw_cts = GridWorldCtsEnv(edge_mode=EDGEMODE_WRAP)
    fig = plt.figure()
    ax = fig.gca()
    gw_cts.plot_trajectories(
        ax,
        [
            [
                (np.array((0.3, 0.95)), None),
                (np.array((0.4, 0.05)), None),
            ],
            [
                (np.array((0.5, 0.05)), None),
                (np.array((0.6, 0.95)), None),
            ],
            [
                (np.array((0.95, 0.3)), None),
                (np.array((0.05, 0.4)), None),
            ],
            [
                (np.array((0.05, 0.5)), None),
                (np.array((0.95, 0.6)), None),
            ],
        ],
        alpha=1
    )
    plt.show()


if __name__ == "__main__":
    demo()
