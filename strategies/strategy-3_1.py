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
        ewm_span=20,
        min_signal_score=0.4,
        spread_weight=0.25,
        volume_weight=0.25,
        flow_weight=0.25,
        rsi_weight=0.25,
        momentum_window=10,
        rsi_period=14,
        rsi_oversold=30,
        rsi_overbought=70,
        base_position_size=0.5,
        max_position_size=0.95,
        stop_loss_atr_mult=1.5,
        take_profit_atr_mult=2.5,
        trailing_stop_activation=1.5,
        trailing_stop_distance=0.7,
        partial_profit_pct=0.5,
        partial_profit_target=0.5,
        max_holding_bars=10,
        kelly_fraction=0.25,
        regime_lookback=50,
        volatility_regime_threshold=0.5,
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
        
        self.rsi = bt.indicators.RelativeStrengthIndex(
            self.dataclose, period=self.params.rsi_period
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
        self.volatility_history = []
        self.price_history = []

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
        self.volatility_history.append(self.volatility[0])
        self.price_history.append(self.dataclose[0])
        
        if len(self.spread_history) > self.params.percentile_window:
            self.spread_history.pop(0)
            self.volume_ratio_history.pop(0)
            self.flow_imbalance_history.pop(0)
        
        if len(self.volatility_history) > self.params.regime_lookback:
            self.volatility_history.pop(0)
            self.price_history.pop(0)
        
        if current_position == 0:
            if len(self.spread_history) >= self.params.ewm_span:
                weights = np.exp(-np.arange(len(self.spread_history))[::-1] / self.params.ewm_span)
                weights = weights / weights.sum()
                
                spread_ewm = np.average(self.spread_history, weights=weights)
                volume_ewm = np.average(self.volume_ratio_history, weights=weights)
                flow_ewm = np.average(self.flow_imbalance_history, weights=weights)
                
                spread_std = np.std(self.spread_history)
                volume_std = np.std(self.volume_ratio_history)
                flow_std = np.std(self.flow_imbalance_history)
                
                spread_zscore = (spread_ratio - spread_ewm) / spread_std if spread_std > 0 else 0
                volume_zscore = (volume_ratio - volume_ewm) / volume_std if volume_std > 0 else 0
                flow_zscore = (flow_imbalance - flow_ewm) / flow_std if flow_std > 0 else 0
                
                rsi_divergence = 0
                if len(self) > self.params.rsi_period + 5:
                    price_change = (self.dataclose[0] - self.dataclose[-5]) / self.dataclose[-5]
                    rsi_change = self.rsi[0] - self.rsi[-5]
                    
                    if price_change > 0 and rsi_change < -5:
                        rsi_divergence = -1
                    elif price_change < 0 and rsi_change > 5:
                        rsi_divergence = 1
                    elif self.rsi[0] < self.params.rsi_oversold:
                        rsi_divergence = 1
                    elif self.rsi[0] > self.params.rsi_overbought:
                        rsi_divergence = -1
                
                spread_signal = max(0, min(1, (spread_zscore + 1) / 2))
                volume_signal = max(0, min(1, (volume_zscore + 1) / 2))
                flow_signal = max(0, min(1, (flow_zscore + 1) / 2))
                rsi_signal = max(0, min(1, abs(rsi_divergence)))
                
                composite_score = (
                    spread_signal * self.params.spread_weight +
                    volume_signal * self.params.volume_weight +
                    flow_signal * self.params.flow_weight +
                    rsi_signal * self.params.rsi_weight
                )
                
                volatility_regime = 'normal'
                if len(self.volatility_history) >= self.params.regime_lookback:
                    recent_vol = np.mean(self.volatility_history[-10:])
                    historical_vol = np.mean(self.volatility_history[:-10])
                    vol_ratio = recent_vol / historical_vol if historical_vol > 0 else 1
                    
                    if vol_ratio > 1 + self.params.volatility_regime_threshold:
                        volatility_regime = 'high'
                    elif vol_ratio < 1 - self.params.volatility_regime_threshold:
                        volatility_regime = 'low'
                
                adaptive_min_score = self.params.min_signal_score
                if volatility_regime == 'high':
                    adaptive_min_score *= 1.2
                elif volatility_regime == 'low':
                    adaptive_min_score *= 0.8
                
                if composite_score >= adaptive_min_score:
                    self.signal_strength = composite_score
                    
                    volatility_adjustment = 1.0
                    if volatility_regime == 'high':
                        volatility_adjustment = 0.7
                    elif volatility_regime == 'low':
                        volatility_adjustment = 1.3
                    
                    position_size = self.params.base_position_size + (
                        (self.params.max_position_size - self.params.base_position_size) * 
                        min(1.0, self.signal_strength) * volatility_adjustment * self.params.kelly_fraction
                    )
                    
                    direction = 0
                    if up_volume > down_volume and rsi_divergence >= 0:
                        direction = 1
                    elif down_volume > up_volume and rsi_divergence <= 0:
                        direction = -1
                    elif rsi_divergence > 0:
                        direction = 1
                    elif rsi_divergence < 0:
                        direction = -1
                    
                    if direction == 1:
                        size = (self.broker.getcash() * position_size) / self.dataclose[0]
                        self.order = self.buy(size=size)
                        self.entry_price = self.dataclose[0]
                        self.stop_price = self.entry_price - (self.atr[0] * self.params.stop_loss_atr_mult)
                        self.target_price = self.entry_price + (self.atr[0] * self.params.take_profit_atr_mult)
                    elif direction == -1:
                        size = (self.broker.getcash() * position_size) / self.dataclose[0]
                        self.order = self.sell(size=size)
                        self.entry_price = self.dataclose[0]
                        self.stop_price = self.entry_price + (self.atr[0] * self.params.stop_loss_atr_mult)
                        self.target_price = self.entry_price - (self.atr[0] * self.params.take_profit_atr_mult)
                    
                    if direction != 0:
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