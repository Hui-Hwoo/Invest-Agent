# strategies/template_strategy.py

import backtrader as bt
import pandas as pd
import numpy as np
import math
import datetime


class TemplateStrategy(bt.Strategy):
    """
    Template for a custom backtrader strategy.

    Steps to implement:
    - Define parameters in `params`
    - Initialize indicators/signals in `__init__`
    - Add entry/exit logic in `next`
    """

    params = dict(
        # Define any strategy parameters here
        example_param=10,
    )

    def __init__(self):
        """
        Called once at the start of the strategy.
        Use this to initialize indicators or other variables.
        """
        pass  # TODO: Add indicators here (e.g., SMA, RSI)

    def next(self):
        """
        Called on each new data point (bar).
        Add your trading logic here.
        """
        pass  # TODO: Add entry/exit logic here
