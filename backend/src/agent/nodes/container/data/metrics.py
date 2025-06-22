import backtrader as bt
import pandas as pd
import argparse
import importlib.util
import os
import sys
import json


class ActionTrackingStrategy(bt.Strategy):
    def __init__(self):
        self.actions = []  # to store buy/sell logs

    def log_action(self, action_type, price, dt=None):
        dt = dt or self.datas[0].datetime.datetime(0)
        self.actions.append(
            {
                "datetime": dt.isoformat(),
                "action": action_type,
                "price": price,
            }
        )

    def notify_order(self, order):
        if order.status in [order.Completed]:
            action = "buy" if order.isbuy() else "sell"
            price = order.executed.price
            self.log_action(action, price)


def get_metrics(data_df, strategy_cls, strategy_params=None):
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(100000)
    cerebro.broker.setcommission(commission=0.001)

    data = bt.feeds.PandasData(dataname=data_df)
    cerebro.adddata(data)

    strategy_params = strategy_params or {}

    # Wrap strategy into a subclass that records actions
    class CombinedStrategy(ActionTrackingStrategy, strategy_cls):
        def __init__(self, *args, **kwargs):
            ActionTrackingStrategy.__init__(self)
            strategy_cls.__init__(self, *args, **kwargs)

    cerebro.addstrategy(CombinedStrategy, **strategy_params)

    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio, _name="sharpe", timeframe=bt.TimeFrame.Days
    )
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(bt.analyzers.SQN, _name="sqn")

    results = cerebro.run()
    strat = results[0]

    metrics = {
        "final_value": cerebro.broker.getvalue(),
        "sharpe": strat.analyzers.sharpe.get_analysis(),
        "drawdown": strat.analyzers.drawdown.get_analysis(),
        "returns": strat.analyzers.returns.get_analysis(),
        "trades": strat.analyzers.trades.get_analysis(),
        "sqn": strat.analyzers.sqn.get_analysis(),
        "actions": strat.actions,  # buy/sell logs
    }

    return metrics


def load_strategy_from_file(filepath):
    filepath = os.path.abspath(filepath)
    module_name = os.path.splitext(os.path.basename(filepath))[0]

    spec = importlib.util.spec_from_file_location(module_name, filepath)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module.MyStrategy


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strategy-path", required=True, help="Path to the strategy file"
    )
    parser.add_argument(
        "--result-path", required=True, help="Path to save results JSON"
    )

    args = parser.parse_args()

    # Load and clean data
    df = pd.read_csv("data.csv", parse_dates=["Datetime"])
    df.set_index("Datetime", inplace=True)
    df = df[df["StockName"] == "QQQ"]
    df = df[["Open", "High", "Low", "Close", "Volume"]]
    df.columns = [col.lower() for col in df.columns]

    # Load strategy
    strategy_cls = load_strategy_from_file(args.strategy_path)

    # Run backtest and get metrics + actions
    metrics = get_metrics(df, strategy_cls=strategy_cls)

    # Print key summary metrics
    print("\n===== BACKTEST SUMMARY =====")
    print(f"Final Portfolio Value: ${metrics['final_value']:.2f} (from $100000)")

    # Format Sharpe Ratio
    sharpe_ratio = metrics["sharpe"].get("sharperatio", None)
    if sharpe_ratio is not None:
        print(f"Sharpe Ratio: {sharpe_ratio:.1f}")
    else:
        print("Sharpe Ratio: N/A")

    # Format Max Drawdown as percentage
    max_drawdown = metrics["drawdown"].get("max", {}).get("drawdown", None)
    if max_drawdown is not None:
        print(f"Max Drawdown: {max_drawdown * 100:.1f}%")
    else:
        print("Max Drawdown: N/A")

    # Format Total Return from analyzer (should match our calculated one)
    analyzer_return = metrics["returns"].get("rtot", None)
    if analyzer_return is not None:
        print(f"Analyzer Total Return: {analyzer_return * 100:.1f}%")
    else:
        print("Analyzer Total Return: N/A")

    # Format SQN
    sqn_value = metrics["sqn"].get("sqn", None)
    if sqn_value is not None:
        print(f"SQN: {sqn_value:.1f}")
    else:
        print("SQN: N/A")

    # Save to JSON
    if not os.path.exists(os.path.dirname(args.result_path)):
        os.makedirs(os.path.dirname(args.result_path))
    with open(args.result_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    # print(f"Results saved to {args.result_path}")
