import backtrader as bt
import pandas as pd
import numpy as np
import math
import datetime


class MyStrategy(bt.Strategy):
    """
    Template for a custom backtrader strategy.

    Steps to implement:
    - Define parameters in `params`
    - Initialize indicators/signals in `__init__`
    - Add entry/exit logic in `next`
    """

    params = dict(
        spread_threshold=1.5,
        volume_lookback=20,
        liquidity_threshold=0.3,
        position_size=0.95,
        stop_loss=0.005,
        take_profit=0.008,
        flow_imbalance_threshold=0.6,
        volatility_window=30,
    )

    def __init__(self):
        """
        Called once at the start of the strategy.
        Use this to initialize indicators or other variables.
        Should not have any input parameters.
        """
        self.dataclose = self.datas[0].close
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low
        self.datavolume = self.datas[0].volume
        
        self.sma_volume = bt.indicators.SimpleMovingAverage(
            self.datavolume, period=self.params.volume_lookback
        )
        
        self.atr = bt.indicators.AverageTrueRange(
            self.datas[0], period=self.params.volatility_window
        )
        
        self.volatility = bt.indicators.StandardDeviation(
            self.dataclose, period=self.params.volatility_window
        )
        
        self.order = None
        self.entry_price = None
        self.stop_price = None
        self.target_price = None

    def next(self):
        """
        Called on each new data point (bar).
        Add your trading logic here.
        """
        if self.order:
            return
            
        current_position = self.position.size
        
        if current_position == 0:
            spread = self.datahigh[0] - self.datalow[0]
            avg_spread = np.mean([self.datahigh[-i] - self.datalow[-i] 
                                 for i in range(1, min(10, len(self)))])
            
            if avg_spread > 0:
                spread_ratio = spread / avg_spread
            else:
                spread_ratio = 1.0
            
            volume_ratio = self.datavolume[0] / self.sma_volume[0] if self.sma_volume[0] > 0 else 1.0
            
            price_dislocation = abs(self.dataclose[0] - self.dataclose[-1]) / self.atr[0] if self.atr[0] > 0 else 0
            
            liquidity_index = (spread_ratio * 0.4 + volume_ratio * 0.3 + price_dislocation * 0.3)
            
            volume_distribution = []
            for i in range(min(5, len(self))):
                if self.datavolume[-i] > 0:
                    volume_distribution.append(self.datavolume[-i])
            
            if len(volume_distribution) > 1:
                volume_variance = np.var(volume_distribution) / (np.mean(volume_distribution) ** 2) if np.mean(volume_distribution) > 0 else 0
            else:
                volume_variance = 0
            
            flow_imbalance = 0
            if len(self) > 5:
                recent_moves = [self.dataclose[-i] - self.dataclose[-i-1] for i in range(5)]
                recent_volumes = [self.datavolume[-i] for i in range(5)]
                
                up_volume = sum([v for i, v in enumerate(recent_volumes) if recent_moves[i] > 0])
                down_volume = sum([v for i, v in enumerate(recent_volumes) if recent_moves[i] <= 0])
                total_volume = up_volume + down_volume
                
                if total_volume > 0:
                    flow_imbalance = abs(up_volume - down_volume) / total_volume
            
            if (spread_ratio > self.params.spread_threshold and 
                liquidity_index > self.params.liquidity_threshold and
                flow_imbalance > self.params.flow_imbalance_threshold):
                
                if up_volume > down_volume:
                    size = (self.broker.getcash() * self.params.position_size) / self.dataclose[0]
                    self.order = self.buy(size=size)
                    self.entry_price = self.dataclose[0]
                    self.stop_price = self.entry_price * (1 - self.params.stop_loss)
                    self.target_price = self.entry_price * (1 + self.params.take_profit)
                else:
                    size = (self.broker.getcash() * self.params.position_size) / self.dataclose[0]
                    self.order = self.sell(size=size)
                    self.entry_price = self.dataclose[0]
                    self.stop_price = self.entry_price * (1 + self.params.stop_loss)
                    self.target_price = self.entry_price * (1 - self.params.take_profit)
        
        elif current_position > 0:
            if self.dataclose[0] <= self.stop_price or self.dataclose[0] >= self.target_price:
                self.order = self.close()
                self.entry_price = None
                self.stop_price = None
                self.target_price = None
                
        elif current_position < 0:
            if self.dataclose[0] >= self.stop_price or self.dataclose[0] <= self.target_price:
                self.order = self.close()
                self.entry_price = None
                self.stop_price = None
                self.target_price = None