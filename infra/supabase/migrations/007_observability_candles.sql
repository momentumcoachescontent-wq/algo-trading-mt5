-- Read-only dashboard visualisation: passive OHLC imported independently of EAs.
-- This additive table does not change the trading webhook, risk management or EA logic.
create table if not exists public.observability_candles (
  symbol text not null check (symbol ~ '^[A-Z0-9._-]{2,24}$'),
  timeframe text not null check (timeframe in ('H4','D1')),
  bar_time timestamptz not null,
  open numeric(22,8) not null check (open > 0),
  high numeric(22,8) not null check (high > 0),
  low numeric(22,8) not null check (low > 0),
  close numeric(22,8) not null check (close > 0),
  tick_volume bigint check (tick_volume is null or tick_volume >= 0),
  source text not null default 'MT5_EXPORT',
  imported_at timestamptz not null default now(),
  primary key (symbol, timeframe, bar_time),
  constraint observability_candles_ohlc_valid check (
    high >= low and high >= greatest(open, close) and low <= least(open, close)
  )
);
comment on table public.observability_candles is
  'Passive MT5 OHLC exports for dashboard visualization only; no trade execution input.';
alter table public.observability_candles enable row level security;
revoke all on table public.observability_candles from public, anon, authenticated;
create index if not exists idx_observability_candles_recent
  on public.observability_candles (symbol, timeframe, bar_time desc);
