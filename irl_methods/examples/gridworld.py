# -*- coding: utf-8 -*-
"""
Simple gridworld implementation from 'Algorithms for Inverse Reinforcement
Learning' by Ng and Russell, 2000

Copyright 2018 Aaron Snoswell
"""


import copy
import math
import numpy as np

import gym
from gym.utils import seeding


class GridWorldEnv(gym.Env):
    """A simple GridWorld MDP

    Based on the GridWorld described in 'Algorithms for Inverse Reinforcement
    Learning' by Ng and Russell, 2000
    """

    metadata = {
        'render.modes': ['human', 'rgb_array'],
        'video.frames_per_second': 30
    }


    # Edge mode static enum
    EDGE_MODE_CLAMP = 0
    EDGE_MODE_WRAP = 1

    # Sytax sugar enum for actions
    ACTION_NORTH = 0
    ACTION_EAST = 1
    ACTION_SOUTH = 2
    ACTION_WEST = 3


    def __init__(
        self,
        *,
        N = 5,
        wind = 0.3,
        edge_mode = EDGE_MODE_CLAMP,
        initial_state = (4, 0),
        goal_states = [(0, 4)],
        per_step_reward = 0,
        goal_reward = 1
        ):
        """
        Constructor for the GridWorld environment

        NB: All methods and internal representations use the y-first, y-down
        coordinate system so that printing any numpy array matches the 

        @param N - The size of the grid world
        @param wind - The chance of a uniform random action being taken each
            step
        @param edge_mode - Edge of world behaviour, one of
            GridWorldEnv.EDGE_MODE_CLAMP or GridWorldEnv.EDGE_MODE_WRAP
        @param initial_state - Starting state for the agent
        @param goal_states - List of goal states
        @param per_step_reward - Reward given every step
        @param goal_reward - Reward upon reaching the goal
        """

        assert edge_mode == GridWorldEnv.EDGE_MODE_WRAP \
            or edge_mode == GridWorldEnv.EDGE_MODE_CLAMP, \
                "Invalid edge_mode: {}".format(edge_mode)
        
        # Size of the gridworld
        self._N = N

        # Wind percentage (chance of moving randomly each step)
        self._wind = wind

        # Edge of world behaviour
        self._edge_mode = edge_mode

        # Set of states
        # NB: We store y first, so that the numpy array layout, when shown
        # using print(), matches the 'y-is-vertical' expectation
        self._S = [
            (y, x) for y in range(self._N) for x in range(self._N)
        ]

        # Lambda to apply boundary condition to an x, y state
        self._apply_edge_mode = lambda x, y: (
                min(max(x, 0), self._N-1) if \
                    (self._edge_mode == GridWorldEnv.EDGE_MODE_CLAMP) \
                        else x % N,
                min(max(y, 0), self._N-1) if \
                    (self._edge_mode == GridWorldEnv.EDGE_MODE_CLAMP) \
                        else y % N,
            )

        # Lambda to get the state index of an x, y pair
        self._state_index = lambda x, y: \
            self._apply_edge_mode(x, y)[1] * N + \
            self._apply_edge_mode(x, y)[0]

        # Set of actions
        # NB: The y direction is inverted so that the numpy array layout, when
        # shown using print(), matches the 'up is up' expectation
        self._A = [
            # North
            (-1, 0),

            # East
            (0, 1),

            # South
            (1, 0),

            # West
            (0, -1),

        ]

        # Transition matrix
        self._T = np.zeros(shape=(len(self._S), len(self._A), len(self._S)))

        # Loop over initial states
        for si in [
                self._state_index(x, y) \
                    for x in range(self._N) for y in range(self._N)
            ]:

            # Get the initial state details
            state = self._S[si]
            x = state[1]
            y = state[0]

            # Loop over actions
            for ai in range(len(self._A)):

                # Get action details
                action = self._A[ai]
                dx = action[1]
                dy = action[0]

                # Update probability for desired action
                self._T[
                    si,
                    ai,
                    self._state_index(x + dx, y + dy)
                ] += (1 - wind)

                # Update probability for stochastic alternatives
                for wind_action in self._A:

                    wind_dx = wind_action[1]
                    wind_dy = wind_action[0]

                    self._T[
                        si,
                        ai,
                        self._state_index(x + wind_dx, y + wind_dy)
                    ] += wind / len(self._A)

        # Gym visualisation object                        
        self.viewer = None

        # Gym action space object (index corresponds to entry in self._A list)
        self.action_space = gym.spaces.Discrete(len(self._A))

        # Gym observation space object (observations are an index indicating
        # the current state)
        self.observation_space = gym.spaces.Discrete(self._N * self._N)

        # Starting state
        self._initial_state = initial_state
        self.state = self._initial_state

        # Goal states
        self._goal_states = goal_states

        # Per step reward
        self._per_step_reward = per_step_reward

        # Goal reward
        self._goal_reward = goal_reward

        # Store true reward
        self._R = np.array([
            self._per_step_reward + self._goal_reward \
                if (y, x) in self._goal_states \
                    else self._per_step_reward \
                        for y in range(self._N) for x in range(self._N)
        ])

        # Reset the MDP
        self.seed()
        self.reset()


    def seed(self, seed = None):
        """
        Set the random seed for the environment
        """

        self.np_random, seed = seeding.np_random(seed)

        return [seed]


    def step(self, action):
        """
        Take one step in the environment
        """

        assert self.action_space.contains(action), \
            "%r (%s) invalid" % (action, type(action))

        # Get current x and y coordinates
        x = self.state[1]
        y = self.state[0]

        # Sample subsequent state from transition matrix
        self.state = np.random.choice(
            range(self._N * self._N),
            p = T[self._state_index(x, y), action, :]
        )

        # Check if we're done or not
        done = self.state in self._goal_states

        # Compute reward
        reward = self._per_step_reward
        if done:
            reward += self._goal_reward 

        # As per the Gym.Env definition, return a (s, r, done, status) tuple
        return self.state, reward, done, {}


    def reset(self):
        """
        Reset the environment to it's initial state
        """

        self.state = self._initial_state
        
        return self.state


    def render(self, mode = 'human'):
        """
        Render the environment

        TODO ajs 29/Apr/18 Implement viewer functionality
        """

        """
        screen_width = 600
        screen_height = 400

        if self.viewer is None:
            from gym.envs.classic_control import rendering
            self.viewer = rendering.Viewer(screen_width, screen_height)
        
        return self.viewer.render(return_rgb_array = (mode == 'rgb_array'))
        """

        return None


    def close(self):
        """
        Close the environment
        """

        if self.viewer:
            self.viewer.close()


    def order_transition_matrix(self, policy):
        """Computes a sorted transition matrix for the GridWorld MDP

        Given a policy, defined as a 2D numpy array of unicode string arrows,
        computes a sorted transition matrix T[s, a, s'] such that the 0th
        action corresponds to the policy's action, and the ith action (i!=0)
        corresponds to the ith non-policy action, for some arbitrary but
        consistent ordering of actions.

        E.g.

        pi_star = [
            ['→', '→', '→', '→', ' '],
            ['↑', '→', '→', '↑', '↑'],
            ['↑', '↑', '↑', '↑', '↑'],
            ['↑', '↑', '→', '↑', '↑'],
            ['↑', '→', '→', '→', '↑'],
        ]

        is the policy used in Ng and Russell's 2000 IRL paper. NB: a space
        indicates a terminal state.

        Args:
            policy (numpy array) - Expert policy 'a1'. See the example above.

        Returns:
            A sorted transition matrix T[s, a, s'], where the 0th action
            T[:, 0, :] corresponds to following the expert policy, and the
            other action entries correspond to the remaining action options,
            sorted according to the ordering in GridWorldEnv._A

        """

        A = copy.copy(self._A)
        T = copy.copy(self._T)
        for y in range(self._N):
            for x in range(self._N):

                si = self._state_index(x, y)
                a = policy[y][x]

                if a == '↑':
                    # Expert chooses north
                    # North is already first in the GridWorldEnv._A ordering
                    pass
                elif a == '→':
                    # Expert chooses east
                    tmp = T[si, 0, :]
                    T[si, 0, :] = T[si, 1, :]
                    T[si, 1, :] = tmp
                elif a == '↓':
                    # Expert chooses south
                    tmp = T[si, 0:1, :]
                    T[si, 0, :] = T[si, 2, :]
                    T[si, 1:2, :] = tmp
                elif a == '←':
                    # Expert chooses west
                    tmp = T[si, 0:2, :]
                    T[si, 0, :] = T[si, 3, :]
                    T[si, 1:3, :] = tmp
                else:
                    # Expert doesn't care / does nothing
                    pass

        return T


    def plot_reward(self, R):
        """
        Plots a given reward vector
        """

        import matplotlib.pyplot as plt

        fig = plt.gcf()
        ax = plt.gca()

        line_width = 0.75
        line_color = "#efefef"

        plt.pcolor(
            np.reshape(R, (self._N, self._N)),
            edgecolors=line_color
        )
        plt.gca().invert_yaxis()
        
        ax.set_aspect("equal", adjustable="box")
        ax.tick_params(length=0, labelbottom=False, labelleft=False)

        # Figure is now ready for display or saving
        return fig
