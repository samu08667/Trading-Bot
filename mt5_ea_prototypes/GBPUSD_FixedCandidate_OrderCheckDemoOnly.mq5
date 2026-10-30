#property strict
#property version   "1.000"
#property description "Demo-only OrderCheck prototype for gbpusd_short_h10_1_5_off_hours."
#property description "No broker execution, no position mutation, no retry."

input bool InpEnableOrderCheck = false;
input bool InpRequireDemoAccount = true;
input bool InpAllowLiveAccount = false;
input string InpSymbol = "GBPUSD";
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M15;
input int InpMaxSpreadPoints = 15;
input double InpVolumeLots = 0.01;
input long InpMagicNumber = 1510152345;
input bool InpLogCommonFiles = true;
input string InpLogPrefix = "gbpusd_short_h10_1_5_off_hours";
input string InpRunId = "";
input bool InpOverwriteLogsOnInit = true;
input string InpFridayLastEntryTime = "23:15";
input string InpFridayForcedFlatTime = "23:45";

const string CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours";
const string REQUIRED_SYMBOL = "GBPUSD";
const ENUM_TIMEFRAMES REQUIRED_TIMEFRAME = PERIOD_M15;
const int ATR_PERIOD = 20;
const int MA_FAST_PERIOD = 20;
const int TICK_VOLUME_PERCENTILE_WINDOW = 100;
const int HISTORY_BARS = 140;
const int MAX_HOLDING_BARS = 10;
const int M15_SECONDS = 15 * 60;
const int FRIDAY_DAY_OF_WEEK = 5;
const double CLOSE_TO_MA_LOW_MID = -0.4303672057741361;
const double CLOSE_TO_MA_MID_HIGH = 0.5954421525644814;
const double TICK_VOLUME_LOW_MID = 0.14;
const double TICK_VOLUME_MID_HIGH = 0.37;
const double SL_ATR_MULTIPLIER = 1.0;
const double TP_ATR_MULTIPLIER = 1.5;
const int ORDER_CHECK_DEVIATION_POINTS = 10;
const string ORDER_CHECK_COMMENT = "GBPH10OCHECK";
const string RUN_CONFIG_LOG = "run_config_log.csv";
const string SIGNAL_LOG = "signal_log.csv";
const string DECISION_LOG = "decision_log.csv";
const string ORDER_CHECK_LOG = "order_check_log.csv";
const string POSITION_LIFECYCLE_LOG = "position_lifecycle_log.csv";
const string TRADE_TRANSACTIONS_LOG = "trade_transactions_log.csv";
const string RECONCILIATION_LOG = "reconciliation_log.csv";

string g_run_id = "";
datetime g_last_evaluated_bar_time = 0;
datetime g_last_duplicate_logged_bar_time = 0;
datetime g_last_order_check_bar_time = 0;

struct SignalSnapshot
{
   datetime bar_time;
   double open;
   double high;
   double low;
   double close;
   long tick_volume;
   int spread;
   double atr_20;
   double ma_fast;
   double close_to_ma_fast_atr_20;
   double tick_volume_percentile_100;
   string hour_session;
   string close_bucket;
   string volume_bucket;
   bool signal_bool;
   double entry_reference_price;
   double sl_price_preview;
   double tp_price_preview;
   string max_exit_time_server;
};

struct PositionObservation
{
   bool detected;
   ulong ticket;
   datetime entry_time;
   double entry_price;
   double current_price;
   double sl;
   double tp;
};

string BoolText(const bool value) { return value ? "true" : "false"; }
string FormatNumber(const double value) { return DoubleToString(value, 12); }
string SafeLongToString(const long value) { return IntegerToString(value); }
string FormatOptionalNumber(const double value, const bool enabled) { return enabled ? FormatNumber(value) : ""; }
string TimeframeText() { return EnumToString(InpTimeframe); }
int CommonFileFlag() { return InpLogCommonFiles ? FILE_COMMON : 0; }
string LogFolder() { return "TradingBot\\" + InpLogPrefix + "\\" + g_run_id; }
string LogPath(const string file_name) { return LogFolder() + "\\" + file_name; }
string BuildGeneratedRunId()
{
   string compact = TimeToString(TimeLocal(), TIME_DATE | TIME_SECONDS);
   StringReplace(compact, ".", "");
   StringReplace(compact, ":", "");
   StringReplace(compact, " ", "_");
   return "ordercheck_demo_" + compact;
}

string ResolveRunId()
{
   string configured = InpRunId;
   StringTrimLeft(configured);
   StringTrimRight(configured);
   if(StringLen(configured) > 0) return configured;

   const string generated = BuildGeneratedRunId();
   if(StringLen(generated) > 0) return generated;
   return "ordercheck_demo_unset";
}

string FormatTimeServer(const datetime value)
{
   if(value <= 0) return "";
   string text = TimeToString(value, TIME_DATE | TIME_SECONDS);
   StringReplace(text, ".", "-");
   return text;
}

bool EnsureLogFolder()
{
   const int common_flag = CommonFileFlag();
   FolderCreate("TradingBot", common_flag);
   FolderCreate("TradingBot\\" + InpLogPrefix, common_flag);
   FolderCreate(LogFolder(), common_flag);
   return true;
}

int OpenLogForAppend(const string file_name, bool &write_header)
{
   const string path = LogPath(file_name);
   const int common_flag = CommonFileFlag();
   const bool exists = FileIsExist(path, common_flag);
   const int handle = FileOpen(path, FILE_READ | FILE_WRITE | FILE_CSV | FILE_ANSI | common_flag, ',');
   if(handle == INVALID_HANDLE)
   {
      Print("Unable to open log file: ", path, " error=", GetLastError());
      write_header = false;
      return INVALID_HANDLE;
   }
   write_header = (!exists || FileSize(handle) == 0);
   FileSeek(handle, 0, SEEK_END);
   return handle;
}

void ReverseRates(MqlRates &rates[])
{
   const int count = ArraySize(rates);
   for(int left = 0, right = count - 1; left < right; left++, right--)
   {
      MqlRates temp = rates[left];
      rates[left] = rates[right];
      rates[right] = temp;
   }
}

bool LoadClosedRatesOldestToNewest(MqlRates &rates[])
{
   const int copied = CopyRates(InpSymbol, InpTimeframe, 1, HISTORY_BARS, rates);
   if(copied <= TICK_VOLUME_PERCENTILE_WINDOW) return false;
   ArraySetAsSeries(rates, false);
   if(ArraySize(rates) >= 2 && rates[0].time > rates[ArraySize(rates) - 1].time)
      ReverseRates(rates);
   return ArraySize(rates) > TICK_VOLUME_PERCENTILE_WINDOW;
}

bool TrueRangeAtIndex(MqlRates &rates[], const int index, double &true_range)
{
   if(index <= 0 || index >= ArraySize(rates)) return false;
   const double previous_close = rates[index - 1].close;
   const double high_low = rates[index].high - rates[index].low;
   const double high_previous_close = MathAbs(rates[index].high - previous_close);
   const double low_previous_close = MathAbs(rates[index].low - previous_close);
   true_range = MathMax(high_low, MathMax(high_previous_close, low_previous_close));
   return true;
}

bool Atr20AtIndex(MqlRates &rates[], const int index, double &atr_value)
{
   if(index < ATR_PERIOD) return false;
   double sum = 0.0;
   for(int offset = 0; offset < ATR_PERIOD; offset++)
   {
      double true_range = 0.0;
      if(!TrueRangeAtIndex(rates, index - offset, true_range)) return false;
      sum += true_range;
   }
   atr_value = sum / ATR_PERIOD;
   return true;
}

bool MaFastAtIndex(MqlRates &rates[], const int index, double &ma_value)
{
   if(index < MA_FAST_PERIOD - 1) return false;
   double sum = 0.0;
   for(int offset = 0; offset < MA_FAST_PERIOD; offset++) sum += rates[index - offset].close;
   ma_value = sum / MA_FAST_PERIOD;
   return true;
}

bool TickVolumePercentile100AtIndex(MqlRates &rates[], const int index, double &percentile)
{
   if(index < TICK_VOLUME_PERCENTILE_WINDOW - 1) return false;
   const long current_tick_volume = rates[index].tick_volume;
   int inclusive_count = 0;
   for(int offset = 0; offset < TICK_VOLUME_PERCENTILE_WINDOW; offset++)
   {
      if(rates[index - offset].tick_volume <= current_tick_volume) inclusive_count++;
   }
   percentile = (double)inclusive_count / (double)TICK_VOLUME_PERCENTILE_WINDOW;
   return true;
}

string HourSession(const datetime server_time)
{
   MqlDateTime parts;
   TimeToStruct(server_time, parts);
   if(parts.hour >= 0 && parts.hour <= 7) return "Asia";
   if(parts.hour >= 8 && parts.hour <= 13) return "London";
   if(parts.hour >= 14 && parts.hour <= 21) return "New_York";
   return "Off_hours";
}

string BucketForValue(const double value, const double low_mid_cutoff, const double mid_high_cutoff)
{
   if(value <= low_mid_cutoff) return "low_tercile";
   if(value <= mid_high_cutoff) return "mid_tercile";
   return "high_tercile";
}
bool ParseHhMm(const string value, int &hour, int &minute)
{
   const int separator = StringFind(value, ":");
   if(separator <= 0) return false;
   hour = (int)StringToInteger(StringSubstr(value, 0, separator));
   minute = (int)StringToInteger(StringSubstr(value, separator + 1));
   return hour >= 0 && hour <= 23 && minute >= 0 && minute <= 59;
}

datetime SameDayTime(const datetime timestamp, const string hhmm)
{
   int hour = 0;
   int minute = 0;
   if(!ParseHhMm(hhmm, hour, minute)) return 0;
   MqlDateTime parts;
   TimeToStruct(timestamp, parts);
   parts.hour = hour;
   parts.min = minute;
   parts.sec = 0;
   return StructToTime(parts);
}

bool IsFriday(const datetime timestamp)
{
   MqlDateTime parts;
   TimeToStruct(timestamp, parts);
   return parts.day_of_week == FRIDAY_DAY_OF_WEEK;
}

bool FridayEntryCutoffOk(const datetime bar_time)
{
   if(!IsFriday(bar_time)) return true;
   const datetime last_entry_time = SameDayTime(bar_time, InpFridayLastEntryTime);
   if(last_entry_time <= 0) return false;
   return bar_time <= last_entry_time;
}

datetime FridayForcedFlatTimeIfApplicable(const datetime timestamp)
{
   if(!IsFriday(timestamp)) return 0;
   const datetime forced_flat_time = SameDayTime(timestamp, InpFridayForcedFlatTime);
   if(forced_flat_time <= 0) return 0;
   if(timestamp <= forced_flat_time) return forced_flat_time;
   return 0;
}

string MaxExitTimeServerPreview(const datetime bar_time)
{
   datetime selected_exit_time = (datetime)((long)bar_time + MAX_HOLDING_BARS * M15_SECONDS);
   const datetime forced_flat_time = FridayForcedFlatTimeIfApplicable(bar_time);
   if(forced_flat_time > 0 && forced_flat_time < selected_exit_time) selected_exit_time = forced_flat_time;
   return FormatTimeServer(selected_exit_time);
}

bool BuildSignalSnapshot(MqlRates &rates[], const int index, SignalSnapshot &snapshot)
{
   if(index < 0 || index >= ArraySize(rates)) return false;
   double atr_20 = 0.0;
   double ma_fast = 0.0;
   double tick_volume_percentile_100 = 0.0;
   if(!Atr20AtIndex(rates, index, atr_20)) return false;
   if(!MaFastAtIndex(rates, index, ma_fast)) return false;
   if(!TickVolumePercentile100AtIndex(rates, index, tick_volume_percentile_100)) return false;
   if(atr_20 <= 0.0 || rates[index].close <= 0.0) return false;

   const double close_to_ma_fast_atr_20 = (rates[index].close - ma_fast) / atr_20;
   const string hour_session = HourSession(rates[index].time);
   const string close_bucket = BucketForValue(close_to_ma_fast_atr_20, CLOSE_TO_MA_LOW_MID, CLOSE_TO_MA_MID_HIGH);
   const string volume_bucket = BucketForValue(tick_volume_percentile_100, TICK_VOLUME_LOW_MID, TICK_VOLUME_MID_HIGH);
   const bool signal_bool = (
      hour_session == "Off_hours" &&
      close_bucket == "high_tercile" &&
      volume_bucket == "mid_tercile" &&
      rates[index].spread <= InpMaxSpreadPoints &&
      rates[index].close > 0.0 &&
      atr_20 > 0.0
   );

   snapshot.bar_time = rates[index].time;
   snapshot.open = rates[index].open;
   snapshot.high = rates[index].high;
   snapshot.low = rates[index].low;
   snapshot.close = rates[index].close;
   snapshot.tick_volume = rates[index].tick_volume;
   snapshot.spread = rates[index].spread;
   snapshot.atr_20 = atr_20;
   snapshot.ma_fast = ma_fast;
   snapshot.close_to_ma_fast_atr_20 = close_to_ma_fast_atr_20;
   snapshot.tick_volume_percentile_100 = tick_volume_percentile_100;
   snapshot.hour_session = hour_session;
   snapshot.close_bucket = close_bucket;
   snapshot.volume_bucket = volume_bucket;
   snapshot.signal_bool = signal_bool;
   snapshot.entry_reference_price = signal_bool ? rates[index].close : 0.0;
   snapshot.sl_price_preview = signal_bool ? rates[index].close + SL_ATR_MULTIPLIER * atr_20 : 0.0;
   snapshot.tp_price_preview = signal_bool ? rates[index].close - TP_ATR_MULTIPLIER * atr_20 : 0.0;
   snapshot.max_exit_time_server = MaxExitTimeServerPreview(rates[index].time);
   return true;
}

void WriteSignalHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","timeframe","bar_time","open","high","low","close","tick_volume","spread","atr_20","ma_fast","close_to_ma_fast_atr_20","tick_volume_percentile_100","hour_session","close_to_ma_fast_atr_20_bucket","tick_volume_percentile_100_bucket","signal_bool","entry_reference_price","sl_price_preview","tp_price_preview","max_holding_bars","max_exit_time_server");
}

void WriteSignalLog(const SignalSnapshot &snapshot)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(SIGNAL_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteSignalHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),CANDIDATE_ID,InpSymbol,TimeframeText(),FormatTimeServer(snapshot.bar_time),FormatNumber(snapshot.open),FormatNumber(snapshot.high),FormatNumber(snapshot.low),FormatNumber(snapshot.close),SafeLongToString(snapshot.tick_volume),IntegerToString(snapshot.spread),FormatNumber(snapshot.atr_20),FormatNumber(snapshot.ma_fast),FormatNumber(snapshot.close_to_ma_fast_atr_20),FormatNumber(snapshot.tick_volume_percentile_100),snapshot.hour_session,snapshot.close_bucket,snapshot.volume_bucket,BoolText(snapshot.signal_bool),FormatOptionalNumber(snapshot.entry_reference_price,snapshot.signal_bool),FormatOptionalNumber(snapshot.sl_price_preview,snapshot.signal_bool),FormatOptionalNumber(snapshot.tp_price_preview,snapshot.signal_bool),IntegerToString(MAX_HOLDING_BARS),snapshot.max_exit_time_server);
   FileClose(handle);
}

void WriteDecisionHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","bar_time","signal_bool","demo_account_ok","symbol_ok","timeframe_ok","spread_ok","one_position_only_ok","pending_order_ok","friday_entry_cutoff_ok","trade_allowed_ok","expert_trade_allowed_ok","volume_ok","sl_tp_ok","order_check_enabled","decision","block_reason");
}

void WriteDecisionLog(const datetime bar_time,const bool signal_bool,const bool demo_account_ok,const bool symbol_ok,const bool timeframe_ok,const bool spread_ok,const bool one_position_only_ok,const bool pending_order_ok,const bool friday_entry_cutoff_ok,const bool trade_allowed_ok,const bool expert_trade_allowed_ok,const bool volume_ok,const bool sl_tp_ok,const string decision,const string block_reason)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(DECISION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteDecisionHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),CANDIDATE_ID,FormatTimeServer(bar_time),BoolText(signal_bool),BoolText(demo_account_ok),BoolText(symbol_ok),BoolText(timeframe_ok),BoolText(spread_ok),BoolText(one_position_only_ok),BoolText(pending_order_ok),BoolText(friday_entry_cutoff_ok),BoolText(trade_allowed_ok),BoolText(expert_trade_allowed_ok),BoolText(volume_ok),BoolText(sl_tp_ok),BoolText(InpEnableOrderCheck),decision,block_reason);
   FileClose(handle);
}

void WriteOrderCheckHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","attempt_id","candidate_id","bar_time","magic_number","comment","symbol","side","volume","price","sl","tp","order_check_called","order_check_retcode","order_check_comment","order_check_balance","order_check_equity","order_check_margin","order_check_margin_free","order_check_margin_level","order_send_called","execution_performed","block_reason");
}

void WriteOrderCheckLog(const datetime bar_time,const string attempt_id,const string comment,const double volume,const double price,const double sl,const double tp,const bool called,const MqlTradeCheckResult &check_result,const string block_reason)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(ORDER_CHECK_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteOrderCheckHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),attempt_id,CANDIDATE_ID,FormatTimeServer(bar_time),SafeLongToString(InpMagicNumber),comment,InpSymbol,"sell",FormatNumber(volume),FormatNumber(price),FormatNumber(sl),FormatNumber(tp),BoolText(called),called ? IntegerToString((int)check_result.retcode) : "",called ? check_result.comment : "",called ? FormatNumber(check_result.balance) : "",called ? FormatNumber(check_result.equity) : "",called ? FormatNumber(check_result.margin) : "",called ? FormatNumber(check_result.margin_free) : "",called ? FormatNumber(check_result.margin_level) : "","false","false",block_reason);
   FileClose(handle);
}
void WritePositionLifecycleHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","position_detected","position_ticket","entry_time","entry_price","current_price","sl","tp","bars_elapsed","max_holding_bars","max_exit_time_server","future_exit_reason_preview","action_taken");
}

bool FirstPositionObservation(PositionObservation &observation)
{
   observation.detected = false;
   observation.ticket = 0;
   observation.entry_time = 0;
   observation.entry_price = 0.0;
   observation.current_price = 0.0;
   observation.sl = 0.0;
   observation.tp = 0.0;
   for(int index = 0; index < PositionsTotal(); index++)
   {
      const ulong ticket = PositionGetTicket(index);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != REQUIRED_SYMBOL) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      observation.detected = true;
      observation.ticket = ticket;
      observation.entry_time = (datetime)PositionGetInteger(POSITION_TIME);
      observation.entry_price = PositionGetDouble(POSITION_PRICE_OPEN);
      observation.current_price = PositionGetDouble(POSITION_PRICE_CURRENT);
      observation.sl = PositionGetDouble(POSITION_SL);
      observation.tp = PositionGetDouble(POSITION_TP);
      return true;
   }
   return false;
}

int BarsElapsedSince(const datetime entry_time, const datetime reference_bar_time)
{
   if(entry_time <= 0 || reference_bar_time <= entry_time) return 0;
   return (int)MathFloor((double)(reference_bar_time - entry_time) / (double)M15_SECONDS);
}

string FutureExitReasonPreview(const datetime entry_time)
{
   if(entry_time <= 0) return "none";
   const datetime tenth_bar = (datetime)((long)entry_time + MAX_HOLDING_BARS * M15_SECONDS);
   const datetime forced_flat = FridayForcedFlatTimeIfApplicable(entry_time);
   if(forced_flat > 0 && forced_flat < tenth_bar) return "friday_forced_flat_preview";
   return "max_holding_preview";
}

void WritePositionLifecycleLog(const datetime reference_bar_time)
{
   PositionObservation observation;
   FirstPositionObservation(observation);
   bool write_header = false;
   const int handle = OpenLogForAppend(POSITION_LIFECYCLE_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WritePositionLifecycleHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),BoolText(observation.detected),observation.detected ? SafeLongToString((long)observation.ticket) : "",observation.detected ? FormatTimeServer(observation.entry_time) : "",observation.detected ? FormatNumber(observation.entry_price) : "",observation.detected ? FormatNumber(observation.current_price) : "",observation.detected ? FormatNumber(observation.sl) : "",observation.detected ? FormatNumber(observation.tp) : "",observation.detected ? IntegerToString(BarsElapsedSince(observation.entry_time, reference_bar_time)) : "0",IntegerToString(MAX_HOLDING_BARS),observation.detected ? MaxExitTimeServerPreview(observation.entry_time) : "",observation.detected ? FutureExitReasonPreview(observation.entry_time) : "none","none_observation_only");
   FileClose(handle);
}

void WriteTradeTransactionsHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","transaction_type","order","deal","position","symbol","price","volume","reason","note");
}

void WriteTradeTransactionLog(const MqlTradeTransaction &trans)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(TRADE_TRANSACTIONS_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteTradeTransactionsHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),IntegerToString((int)trans.type),SafeLongToString((long)trans.order),SafeLongToString((long)trans.deal),SafeLongToString((long)trans.position),trans.symbol,FormatNumber(trans.price),FormatNumber(trans.volume),"observed_external_or_manual_event","passive_log_only");
   FileClose(handle);
}

void WriteReconciliationHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","magic_number","position_count","pending_order_count","broker_state","reconciliation_status");
}

int CountPositionsForCandidate()
{
   int count = 0;
   for(int index = 0; index < PositionsTotal(); index++)
   {
      const ulong ticket = PositionGetTicket(index);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != REQUIRED_SYMBOL) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      count++;
   }
   return count;
}

int CountPendingOrdersForCandidate()
{
   int count = 0;
   for(int index = 0; index < OrdersTotal(); index++)
   {
      const ulong ticket = OrderGetTicket(index);
      if(ticket == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != REQUIRED_SYMBOL) continue;
      if((long)OrderGetInteger(ORDER_MAGIC) != InpMagicNumber) continue;
      count++;
   }
   return count;
}

void WriteReconciliationLog(const int position_count, const int pending_order_count)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(RECONCILIATION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteReconciliationHeader(handle);
   const string broker_state = (position_count == 0 && pending_order_count == 0) ? "flat_no_pending" : "position_or_pending_detected";
   const string reconciliation_status = (position_count == 0 && pending_order_count == 0) ? "ok_flat" : "blocked_existing_broker_state";
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),CANDIDATE_ID,InpSymbol,SafeLongToString(InpMagicNumber),IntegerToString(position_count),IntegerToString(pending_order_count),broker_state,reconciliation_status);
   FileClose(handle);
}

bool IsDemoAccount() { return AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO; }
bool SymbolAndInputOk() { return _Symbol == REQUIRED_SYMBOL && InpSymbol == REQUIRED_SYMBOL; }
bool TimeframeAndInputOk() { return _Period == REQUIRED_TIMEFRAME && InpTimeframe == REQUIRED_TIMEFRAME; }
bool TerminalTradeAllowed() { return (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED); }
bool ExpertTradeAllowed() { return (bool)MQLInfoInteger(MQL_TRADE_ALLOWED); }

bool SymbolTradeModeAllowsShort()
{
   const long trade_mode = SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_MODE);
   return trade_mode == SYMBOL_TRADE_MODE_FULL || trade_mode == SYMBOL_TRADE_MODE_SHORTONLY;
}

int CurrentSpreadPoints()
{
   return (int)SymbolInfoInteger(InpSymbol, SYMBOL_SPREAD);
}

int VolumeDigitsForStep(const double step)
{
   int digits = 0;
   double scaled = step;
   while(digits < 8 && MathAbs(scaled - MathRound(scaled)) > 0.000000001)
   {
      scaled *= 10.0;
      digits++;
   }
   return digits;
}

bool NormalizeVolumeToStep(const double requested_volume, double &normalized_volume)
{
   const double min_volume = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN);
   const double max_volume = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   const double volume_step = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   if(min_volume <= 0.0 || max_volume <= 0.0 || volume_step <= 0.0) return false;
   if(requested_volume < min_volume || requested_volume > max_volume) return false;
   const double steps = MathFloor((requested_volume - min_volume) / volume_step + 0.000000001);
   normalized_volume = min_volume + steps * volume_step;
   normalized_volume = NormalizeDouble(normalized_volume, VolumeDigitsForStep(volume_step));
   return normalized_volume >= min_volume && normalized_volume <= max_volume;
}

double NormalizeSymbolPrice(const double price)
{
   const int digits = (int)SymbolInfoInteger(InpSymbol, SYMBOL_DIGITS);
   return NormalizeDouble(price, digits);
}

bool SlTpValidForSell(const double price, const double sl, const double tp)
{
   if(price <= 0.0 || sl <= 0.0 || tp <= 0.0) return false;
   if(sl <= price || tp >= price) return false;
   const double point = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   const long stops_level_points = SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_STOPS_LEVEL);
   const double min_distance = (double)stops_level_points * point;
   if(min_distance > 0.0)
   {
      if(sl - price < min_distance) return false;
      if(price - tp < min_distance) return false;
   }
   return true;
}

ENUM_ORDER_TYPE_FILLING PreferredFillingMode()
{
   const long filling_mode = SymbolInfoInteger(InpSymbol, SYMBOL_FILLING_MODE);
   if((filling_mode & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC) return ORDER_FILLING_IOC;
   if((filling_mode & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK) return ORDER_FILLING_FOK;
   return ORDER_FILLING_RETURN;
}

bool BuildBrokerSafeCheckRequest(const SignalSnapshot &snapshot,const double normalized_volume,MqlTradeRequest &request,double &price,double &sl,double &tp,string &block_reason)
{
   MqlTick tick;
   if(!SymbolInfoTick(InpSymbol, tick) || tick.bid <= 0.0)
   {
      block_reason = "tick_unavailable";
      return false;
   }
   price = NormalizeSymbolPrice(tick.bid);
   sl = NormalizeSymbolPrice(snapshot.sl_price_preview);
   tp = NormalizeSymbolPrice(snapshot.tp_price_preview);
   if(!SlTpValidForSell(price, sl, tp))
   {
      block_reason = "sl_tp_invalid";
      return false;
   }
   ZeroMemory(request);
   request.action = TRADE_ACTION_DEAL;
   request.symbol = InpSymbol;
   request.volume = normalized_volume;
   request.type = ORDER_TYPE_SELL;
   request.price = price;
   request.sl = sl;
   request.tp = tp;
   request.deviation = ORDER_CHECK_DEVIATION_POINTS;
   request.magic = (ulong)InpMagicNumber;
   request.comment = ORDER_CHECK_COMMENT;
   request.type_time = ORDER_TIME_GTC;
   request.type_filling = PreferredFillingMode();
   return true;
}

string AttemptId(const datetime bar_time)
{
   string compact = TimeToString(bar_time, TIME_DATE | TIME_MINUTES);
   StringReplace(compact, ".", "");
   StringReplace(compact, ":", "");
   StringReplace(compact, " ", "");
   return "OC" + compact;
}

void DeleteRunLogFile(const string file_name)
{
   const string path = LogPath(file_name);
   const int common_flag = CommonFileFlag();
   if(FileIsExist(path, common_flag))
      FileDelete(path, common_flag);
}

void DeleteCurrentRunLogs()
{
   DeleteRunLogFile(RUN_CONFIG_LOG);
   DeleteRunLogFile(SIGNAL_LOG);
   DeleteRunLogFile(DECISION_LOG);
   DeleteRunLogFile(ORDER_CHECK_LOG);
   DeleteRunLogFile(POSITION_LIFECYCLE_LOG);
   DeleteRunLogFile(TRADE_TRANSACTIONS_LOG);
   DeleteRunLogFile(RECONCILIATION_LOG);
}

void WriteRunConfigHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","timeframe","InpEnableOrderCheck","InpRequireDemoAccount","InpAllowLiveAccount","InpLogCommonFiles","InpVolumeLots","InpMagicNumber","InpMaxSpreadPoints","InpFridayLastEntryTime","InpFridayForcedFlatTime","account_trade_mode","is_demo_account","terminal_trade_allowed","expert_trade_allowed");
}

void WriteRunConfigLog()
{
   bool write_header = false;
   const int handle = OpenLogForAppend(RUN_CONFIG_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteRunConfigHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),CANDIDATE_ID,InpSymbol,TimeframeText(),BoolText(InpEnableOrderCheck),BoolText(InpRequireDemoAccount),BoolText(InpAllowLiveAccount),BoolText(InpLogCommonFiles),FormatNumber(InpVolumeLots),SafeLongToString(InpMagicNumber),IntegerToString(InpMaxSpreadPoints),InpFridayLastEntryTime,InpFridayForcedFlatTime,IntegerToString((int)AccountInfoInteger(ACCOUNT_TRADE_MODE)),BoolText(IsDemoAccount()),BoolText(TerminalTradeAllowed()),BoolText(ExpertTradeAllowed()));
   FileClose(handle);
}

void EnsureLogHeaders()
{
   bool write_header = false;
   int handle = OpenLogForAppend(RUN_CONFIG_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteRunConfigHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(SIGNAL_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteSignalHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(DECISION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteDecisionHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(ORDER_CHECK_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteOrderCheckHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(POSITION_LIFECYCLE_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WritePositionLifecycleHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(TRADE_TRANSACTIONS_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteTradeTransactionsHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(RECONCILIATION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteReconciliationHeader(handle); FileClose(handle); }
}

void LogDuplicateBarSkipped(const datetime bar_time)
{
   WriteDecisionLog(bar_time,false,IsDemoAccount(),SymbolAndInputOk(),TimeframeAndInputOk(),CurrentSpreadPoints() <= InpMaxSpreadPoints,CountPositionsForCandidate() == 0,CountPendingOrdersForCandidate() == 0,FridayEntryCutoffOk(bar_time),TerminalTradeAllowed() && SymbolTradeModeAllowsShort(),ExpertTradeAllowed(),true,true,"blocked","duplicate_bar_skipped");
}

void WriteFeatureUnavailableDecision(const datetime bar_time)
{
   WriteDecisionLog(bar_time,false,IsDemoAccount(),SymbolAndInputOk(),TimeframeAndInputOk(),CurrentSpreadPoints() <= InpMaxSpreadPoints,CountPositionsForCandidate() == 0,CountPendingOrdersForCandidate() == 0,FridayEntryCutoffOk(bar_time),TerminalTradeAllowed() && SymbolTradeModeAllowsShort(),ExpertTradeAllowed(),false,false,"blocked","features_unavailable");
}

void ProcessClosedBar(const datetime closed_bar_time)
{
   MqlRates rates[];
   if(!LoadClosedRatesOldestToNewest(rates))
   {
      WriteFeatureUnavailableDecision(closed_bar_time);
      return;
   }

   const int index = ArraySize(rates) - 1;
   SignalSnapshot snapshot;
   if(!BuildSignalSnapshot(rates, index, snapshot))
   {
      WriteFeatureUnavailableDecision(closed_bar_time);
      return;
   }

   WriteSignalLog(snapshot);
   const int position_count = CountPositionsForCandidate();
   const int pending_order_count = CountPendingOrdersForCandidate();
   WriteReconciliationLog(position_count, pending_order_count);
   WritePositionLifecycleLog(snapshot.bar_time);

   if(!snapshot.signal_bool)
   {
      WriteDecisionLog(snapshot.bar_time,false,IsDemoAccount(),SymbolAndInputOk(),TimeframeAndInputOk(),CurrentSpreadPoints() <= InpMaxSpreadPoints,position_count == 0,pending_order_count == 0,FridayEntryCutoffOk(snapshot.bar_time),TerminalTradeAllowed() && SymbolTradeModeAllowsShort(),ExpertTradeAllowed(),true,true,"no_signal","");
      return;
   }

   const bool demo_account_ok = InpRequireDemoAccount && IsDemoAccount();
   const bool live_input_ok = !InpAllowLiveAccount;
   const bool symbol_ok = SymbolAndInputOk();
   const bool timeframe_ok = TimeframeAndInputOk();
   const bool spread_ok = CurrentSpreadPoints() <= InpMaxSpreadPoints;
   const bool one_position_only_ok = position_count == 0;
   const bool pending_order_ok = pending_order_count == 0;
   const bool friday_entry_cutoff_ok = FridayEntryCutoffOk(snapshot.bar_time);
   const bool terminal_trade_ok = TerminalTradeAllowed();
   const bool symbol_trade_mode_ok = SymbolTradeModeAllowsShort();
   const bool trade_allowed_ok = terminal_trade_ok && symbol_trade_mode_ok;
   const bool expert_trade_allowed_ok = ExpertTradeAllowed();

   double normalized_volume = 0.0;
   const bool volume_ok = NormalizeVolumeToStep(InpVolumeLots, normalized_volume);
   MqlTradeRequest request;
   double price = 0.0;
   double sl = 0.0;
   double tp = 0.0;
   string request_block_reason = "";
   bool sl_tp_ok = false;
   if(volume_ok)
      sl_tp_ok = BuildBrokerSafeCheckRequest(snapshot, normalized_volume, request, price, sl, tp, request_block_reason);

   string block_reason = "";
   if(!InpRequireDemoAccount) block_reason = "demo_requirement_disabled";
   else if(!live_input_ok) block_reason = "live_account_input_enabled";
   else if(!demo_account_ok) block_reason = "demo_account_required";
   else if(!symbol_ok) block_reason = "symbol_not_locked";
   else if(!timeframe_ok) block_reason = "timeframe_not_locked";
   else if(!terminal_trade_ok) block_reason = "terminal_trade_disabled";
   else if(!expert_trade_allowed_ok) block_reason = "expert_trade_disabled";
   else if(!symbol_trade_mode_ok) block_reason = "symbol_trade_mode_block";
   else if(!spread_ok) block_reason = "current_spread_exceeded";
   else if(!one_position_only_ok) block_reason = "one_position_only_block";
   else if(!pending_order_ok) block_reason = "pending_order_block";
   else if(!friday_entry_cutoff_ok) block_reason = "friday_entry_cutoff_block";
   else if(!volume_ok) block_reason = "volume_invalid";
   else if(!sl_tp_ok) block_reason = request_block_reason == "" ? "sl_tp_invalid" : request_block_reason;
   else if(g_last_order_check_bar_time == snapshot.bar_time) block_reason = "duplicate_order_check_block";
   else if(!InpEnableOrderCheck) block_reason = "order_check_disabled";

   if(block_reason != "")
   {
      const string decision = block_reason == "order_check_disabled" ? "order_check_skipped_disabled" : "blocked";
      WriteDecisionLog(snapshot.bar_time,true,demo_account_ok,symbol_ok,timeframe_ok,spread_ok,one_position_only_ok,pending_order_ok,friday_entry_cutoff_ok,trade_allowed_ok,expert_trade_allowed_ok,volume_ok,sl_tp_ok,decision,block_reason);
      MqlTradeCheckResult blank_result;
      ZeroMemory(blank_result);
      WriteOrderCheckLog(snapshot.bar_time,AttemptId(snapshot.bar_time),ORDER_CHECK_COMMENT,normalized_volume,price,sl,tp,false,blank_result,block_reason);
      return;
   }

   g_last_order_check_bar_time = snapshot.bar_time;
   MqlTradeCheckResult check_result;
   ZeroMemory(check_result);
   const bool check_called = OrderCheck(request, check_result);
   WriteDecisionLog(snapshot.bar_time,true,demo_account_ok,symbol_ok,timeframe_ok,spread_ok,one_position_only_ok,pending_order_ok,friday_entry_cutoff_ok,trade_allowed_ok,expert_trade_allowed_ok,volume_ok,sl_tp_ok,"order_check_attempted",check_called ? "" : "order_check_call_failed");
   WriteOrderCheckLog(snapshot.bar_time,AttemptId(snapshot.bar_time),request.comment,request.volume,request.price,request.sl,request.tp,true,check_result,check_called ? "" : "order_check_call_failed");
}

bool ValidateChartAndInputs()
{
   if(InpAllowLiveAccount)
   {
      Print("OrderCheck demo-only prototype blocked: live account input must remain false.");
      return false;
   }
   if(InpSymbol != REQUIRED_SYMBOL || _Symbol != REQUIRED_SYMBOL)
   {
      Print("OrderCheck demo-only prototype blocked: symbol must be ", REQUIRED_SYMBOL);
      return false;
   }
   if(InpTimeframe != REQUIRED_TIMEFRAME || _Period != REQUIRED_TIMEFRAME)
   {
      Print("OrderCheck demo-only prototype blocked: timeframe must be M15.");
      return false;
   }
   return true;
}

int OnInit()
{
   g_run_id = ResolveRunId();
   EnsureLogFolder();
   if(InpOverwriteLogsOnInit)
      DeleteCurrentRunLogs();
   EnsureLogHeaders();
   WriteRunConfigLog();
   if(!ValidateChartAndInputs()) return INIT_PARAMETERS_INCORRECT;
   Print("OrderCheck demo-only prototype initialized: candidate=",CANDIDATE_ID," enable_order_check=",BoolText(InpEnableOrderCheck)," require_demo=",BoolText(InpRequireDemoAccount)," allow_live=",BoolText(InpAllowLiveAccount)," run_id=",g_run_id," log_folder=",LogFolder());
   return INIT_SUCCEEDED;
}

void OnTick()
{
   const datetime closed_bar_time = iTime(InpSymbol, InpTimeframe, 1);
   if(closed_bar_time <= 0) return;
   if(closed_bar_time == g_last_evaluated_bar_time)
   {
      if(g_last_duplicate_logged_bar_time != closed_bar_time)
      {
         LogDuplicateBarSkipped(closed_bar_time);
         g_last_duplicate_logged_bar_time = closed_bar_time;
      }
      return;
   }
   g_last_evaluated_bar_time = closed_bar_time;
   g_last_duplicate_logged_bar_time = 0;
   ProcessClosedBar(closed_bar_time);
}

void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result)
{
   WriteTradeTransactionLog(trans);
}