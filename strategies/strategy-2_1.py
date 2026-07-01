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
        volume_lookback=20,
        volatility_window=30,
        percentile_window=100,
        spread_percentile=75,
        volume_percentile=70,
        flow_imbalance_percentile=65,
        momentum_window=10,
        momentum_threshold=0.5,
        base_position_size=0.5,
        max_position_size=0.95,
        stop_loss_atr_mult=1.5,
        take_profit_atr_mult=2.5,
        trailing_stop_activation=1.5,
        trailing_stop_distance=0.7,
        partial_profit_pct=0.5,
        partial_profit_target=0.5,
        max_holding_bars=10,
        mtf_multiplier=4,
        kelly_fraction=0.25,
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
        
        self.momentum = bt.indicators.MomentumOscillator(
            self.dataclose, period=self.params.momentum_window
        )
        
        self.order = None
        self.entry_price = None
        self.stop_price = None
        self.target_price = None
        self.trailing_stop_price = None
        self.bars_since_entry = 0
        self.partial_exit_done = False
        self.spread_history = []
        self.volume_ratio_history = []
        self.flow_imbalance_history = []
        self.signal_strength = 0

    def next(self):
        """
        Called on each new data point (bar).
        Add your trading logic here.
        """
        if self.order:
            return
            
        current_position = self.position.size
        
        spread = self.datahigh[0] - self.datalow[0]
        avg_spread = np.mean([self.datahigh[-i] - self.datalow[-i] 
                             for i in range(1, min(10, len(self)))])
        
        if avg_spread > 0:
            spread_ratio = spread / avg_spread
        else:
            spread_ratio = 1.0
            
        volume_ratio = self.datavolume[0] / self.sma_volume[0] if self.sma_volume[0] > 0 else 1.0
        
        flow_imbalance = 0
        if len(self) > 5:
            recent_moves = [self.dataclose[-i] - self.dataclose[-i-1] for i in range(5)]
            recent_volumes = [self.datavolume[-i] for i in range(5)]
            
            up_volume = sum([v for i, v in enumerate(recent_volumes) if recent_moves[i] > 0])
            down_volume = sum([v for i, v in enumerate(recent_volumes) if recent_moves[i] <= 0])
            total_volume = up_volume + down_volume
            
            if total_volume > 0:
                flow_imbalance = abs(up_volume - down_volume) / total_volume
        
        self.spread_history.append(spread_ratio)
        self.volume_ratio_history.append(volume_ratio)
        self.flow_imbalance_history.append(flow_imbalance)
        
        if len(self.spread_history) > self.params.percentile_window:
            self.spread_history.pop(0)
            self.volume_ratio_history.pop(0)
            self.flow_imbalance_history.pop(0)
        
        if current_position == 0:
            if len(self.spread_history) >= self.params.percentile_window:
                spread_threshold = np.percentile(self.spread_history, self.params.spread_percentile)
                volume_threshold = np.percentile(self.volume_ratio_history, self.params.volume_percentile)
                flow_threshold = np.percentile(self.flow_imbalance_history, self.params.flow_imbalance_percentile)
                
                spread_signal = spread_ratio > spread_threshold
                volume_signal = volume_ratio > volume_threshold
                flow_signal = flow_imbalance > flow_threshold
                
                momentum_value = (self.momentum[0] - 100) / 100
                momentum_signal = abs(momentum_value) > self.params.momentum_threshold
                
                mtf_confirmation = True
                if len(self) > self.params.mtf_multiplier * 5:
                    mtf_moves = [self.dataclose[-i*self.params.mtf_multiplier] - 
                                self.dataclose[-(i+1)*self.params.mtf_multiplier] 
                                for i in range(5)]
                    mtf_volumes = [self.datavolume[-i*self.params.mtf_multiplier] for i in range(5)]
                    
                    mtf_up_volume = sum([v for i, v in enumerate(mtf_volumes) if mtf_moves[i] > 0])
                    mtf_down_volume = sum([v for i, v in enumerate(mtf_volumes) if mtf_moves[i] <= 0])
                    mtf_total = mtf_up_volume + mtf_down_volume
                    
                    if mtf_total > 0:
                        mtf_imbalance = abs(mtf_up_volume - mtf_down_volume) / mtf_total
                        mtf_confirmation = mtf_imbalance > 0.4
                
                if spread_signal and volume_signal and flow_signal and momentum_signal and mtf_confirmation:
                    self.signal_strength = (
                        (spread_ratio / spread_threshold - 1) * 0.3 +
                        (volume_ratio / volume_threshold - 1) * 0.3 +
                        (flow_imbalance / flow_threshold - 1) * 0.2 +
                        abs(momentum_value) * 0.2
                    )
                    
                    volatility_percentile = 50
                    if len(self) > self.params.volatility_window:
                        vol_history = [self.volatility[-i] for i in range(min(self.params.percentile_window, len(self)))]
                        current_vol_percentile = np.searchsorted(np.sort(vol_history), self.volatility[0]) / len(vol_history) * 100
                        volatility_percentile = current_vol_percentile
                    
                    volatility_adjustment = 1.0 - (volatility_percentile / 100) * 0.5
                    
                    position_size = self.params.base_position_size + (
                        (self.params.max_position_size - self.params.base_position_size) * 
                        min(1.0, self.signal_strength) * volatility_adjustment * self.params.kelly_fraction
                    )
                    
                    direction = 1 if up_volume > down_volume and momentum_value > 0 else -1
                    
                    if direction == 1:
                        size = (self.broker.getcash() * position_size) / self.dataclose[0]
                        self.order = self.buy(size=size)
                        self.entry_price = self.dataclose[0]
                        self.stop_price = self.entry_price - (self.atr[0] * self.params.stop_loss_atr_mult)
                        self.target_price = self.entry_price + (self.atr[0] * self.params.take_profit_atr_mult)
                    else:
                        size = (self.broker.getcash() * position_size) / self.dataclose[0]
                        self.order = self.sell(size=size)
                        self.entry_price = self.dataclose[0]
                        self.stop_price = self.entry_price + (self.atr[0] * self.params.stop_loss_atr_mult)
                        self.target_price = self.entry_price - (self.atr[0] * self.params.take_profit_atr_mult)
                    
                    self.bars_since_entry = 0
                    self.partial_exit_done = False
                    self.trailing_stop_price = None
                    
        elif current_position != 0:
            self.bars_since_entry += 1
            
            if current_position > 0:
                profit_pct = (self.dataclose[0] - self.entry_price) / self.entry_price
                
                if not self.partial_exit_done and profit_pct >= (self.params.partial_profit_target * self.params.take_profit_atr_mult * self.atr[0] / self.entry_price):
                    partial_size = abs(current_position) * self.params.partial_profit_pct
                    self.order = self.sell(size=partial_size)
                    self.partial_exit_done = True
                    return
                
                if profit_pct >= (self.params.trailing_stop_activation * self.atr[0] / self.entry_price):
                    new_trailing_stop = self.dataclose[0] - (self.atr[0] * self.params.trailing_stop_distance)
                    if self.trailing_stop_price is None or new_trailing_stop > self.trailing_stop_price:
                        self.trailing_stop_price = new_trailing_stop
                        self.stop_price = max(self.stop_price, self.trailing_stop_price)
                
                if self.dataclose[0] <= self.stop_price or self.dataclose[0] >= self.target_price or self.bars_since_entry >= self.params.max_holding_bars:
                    self.order = self.close()
                    self.entry_price = None
                    self.stop_price = None
                    self.target_price = None
                    self.trailing_stop_price = None
                    self.bars_since_entry = 0
                    self.partial_exit_done = False
                    
            else:
                profit_pct = (self.entry_price - self.dataclose[0]) / self.entry_price
                
                if not self.partial_exit_done and profit_pct >= (self.params.partial_profit_target * self.params.take_profit_atr_mult * self.atr[0] / self.entry_price):
                    partial_size = abs(current_position) * self.params.partial_profit_pct
                    self.order = self.buy(size=partial_size)
                    self.partial_exit_done = True
                    return
                
                if profit_pct >= (self.params.trailing_stop_activation * self.atr[0] / self.entry_price):
                    new_trailing_stop = self.dataclose[0] + (self.atr[0] * self.params.trailing_stop_distance)
                    if self.trailing_stop_price is None or new_trailing_stop < self.trailing_stop_price:
                        self.trailing_stop_price = new_trailing_stop
                        self.stop_price = min(self.stop_price, self.trailing_stop_price)
                
                if self.dataclose[0] >= self.stop_price or self.dataclose[0] <= self.target_price or self.bars_since_entry >= self.params.max_holding_bars:
                    self.order = self.close()
                    self.entry_price = None
                    self.stop_price = None
                    self.target_price = None
                    self.trailing_stop_price = None
                    self.bars_since_entry = 0
                    self.partial_exit_done = False