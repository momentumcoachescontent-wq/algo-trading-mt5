import importlib.util
from pathlib import Path
import sys,unittest
import numpy as np
import pandas as pd
path=Path(__file__).resolve().parents[1]/'python/research/v5_multiasset.py'
spec=importlib.util.spec_from_file_location('v5',path);m=importlib.util.module_from_spec(spec);sys.modules['v5']=m;spec.loader.exec_module(m)

class V5Tests(unittest.TestCase):
    def data(self):
        c=np.r_[np.arange(10,30),np.arange(30,10,-1)].astype(float)
        return pd.DataFrame({'open':c,'high':c+.5,'low':c-.5,'close':c},index=pd.date_range('2020-01-01',periods=len(c)))
    def test_no_current_bar_entry_information(self):
        d=self.data();cfg=m.Hypothesis(3,2,5);a=m.execution_targets(d,cfg)
        changed=d.copy();changed.iloc[15:]*=10
        self.assertEqual(a.iloc[15],m.execution_targets(changed,cfg).iloc[15])
    def test_prefix_invariance(self):
        d=self.data();cfg=m.Hypothesis(3,2,5)
        pd.testing.assert_series_equal(m.decisions(d,cfg).iloc[:25],m.decisions(d.iloc[:25],cfg))
    def test_channel_excludes_signal_candle(self):
        d=self.data();self.assertEqual(m.decisions(d,m.Hypothesis(3,2,5)).iloc[8],1)
    def test_duplicate_time_rejected(self):
        d=self.data();d.index=[d.index[0]]*len(d)
        with self.assertRaises(ValueError):m.decisions(d,m.Hypothesis())
    def test_invalid_ohlc_rejected(self):
        d=self.data();d.iloc[3,d.columns.get_loc('high')]=0
        with self.assertRaises(ValueError):m.decisions(d,m.Hypothesis())
    def test_next_open_gap_changes_fill(self):
        d=self.data();p=d.open.iloc[:4];t=pd.Series([0,1,1,0],index=p.index)
        a=m.replay(p,t,0,0);changed=p.copy();changed.iloc[1]+=3
        b=m.replay(changed,t,0,0);self.assertAlmostEqual(a[0]['pnl']-b[0]['pnl'],3)
    def test_short_fees_and_slippage(self):
        p=pd.Series([100.,90.,80.],index=pd.date_range('2020',periods=3));t=pd.Series([-1,-1,0],index=p.index)
        trade=m.replay(p,t,.001,.001)[0]
        self.assertAlmostEqual(trade['pnl'],99.9-80.08-.0999-.08008)
    def test_reversal_closes_then_opens(self):
        p=pd.Series([100.,110.,90.],index=pd.date_range('2020',periods=3));t=pd.Series([1,-1,0],index=p.index)
        self.assertEqual([x['pnl'] for x in m.replay(p,t,0,0)],[10.,20.])
    def test_cost_stress_reduces_pnl(self):
        d=self.data();t=m.execution_targets(d,m.Hypothesis(3,2,5))
        self.assertLess(m.summarize(m.replay(d.open,t,.002,.002))['net_price_units'],m.summarize(m.replay(d.open,t,.001,.001))['net_price_units'])
    def test_no_trades_does_not_pass(self):
        self.assertFalse(m.summarize([])['positive']);self.assertIsNone(m.summarize([])['pf'])
    def test_vectorbt_independent_ledger(self):
        p=pd.Series([100.,110.,90.,95.,80.],index=pd.date_range('2020',periods=5));t=pd.Series([1,-1,0,1,0],index=p.index)
        self.assertEqual(len(m.vectorbt_check(p,t,.001,.001)),3)

if __name__=='__main__':unittest.main()
