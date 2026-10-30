#property strict
#property version   "1.000"
#property description "Demo-only lifecycle watch/preflight prototype for gbpusd_short_h10_1_5_off_hours."
#property description "Observes matching positions and logs close preflight with no broker mutation."

input bool InpEnableLifecycleWatch = false;
input bool InpEnableLifecycleClosePreflight = false;
input bool InpEnableLifecycleClose = false;
input string InpFinalLifecycleAcknowledgment = "";
input int InpMaxLifecycleCloseAttempts = 1;
input bool InpRequireDemoAccount = true;
input bool InpAllowLiveAccount = false;
input string InpRunId = "";
input bool InpOverwriteLogsOnInit = true;
input bool InpLogCommonFiles = true;
input long InpMagicNumber = 1510152345;
input int InpMaxHoldingBars = 10;
input string InpFridayForcedFlatTime = "23:45";
input string InpFridayLastEntryTime = "23:15";
input string InpSymbol = "GBPUSD";
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M15;
input string InpLogPrefix = "gbpusd_short_h10_1_5_off_hours";

const string CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours";
const string REQUIRED_SYMBOL = "GBPUSD";
const ENUM_TIMEFRAMES REQUIRED_TIMEFRAME = PERIOD_M15;
const string SIDE_SELL = "sell";
const int REQUIRED_MAX_HOLDING_BARS = 10;
const int M15_SECONDS = 15 * 60;
const int FRIDAY_DAY_OF_WEEK = 5;
const string FINAL_LIFECYCLE_ACK_TEXT = "confirm_single_demo_lifecycle_close_only";
const string RUN_CONFIG_LOG = "run_config_log.csv";
const string LIFECYCLE_WATCH_LOG = "lifecycle_watch_log.csv";
const string LIFECYCLE_EXIT_DECISION_LOG = "lifecycle_exit_decision_log.csv";
const string POSITION_CLOSE_LOG = "position_close_log.csv";
const string LIFECYCLE_RECONCILIATION_LOG = "lifecycle_reconciliation_log.csv";
const string LIFECYCLE_STATE_TRANSITION_LOG = "lifecycle_state_transition_log.csv";
const string STATIC_GUARD_CLOSE_CALLED_FALSE = "close_called,false";
const string STATIC_GUARD_RETRY_PERFORMED_FALSE = "retry_performed,false";
const string STATIC_GUARD_AUTOMATIC_RETRY_ALLOWED_FALSE = "automatic_retry_allowed,false";

string g_run_id = "";
datetime g_last_evaluated_closed_bar_time = 0;
string g_current_lifecycle_state = "initialized";
string g_last_lifecycle_attempt_id = "";

struct LifecycleSnapshot
{
   datetime timestamp_server;
   datetime current_closed_bar_time;
   bool position_observed_open;
   int matching_position_count;
   int pending_order_count;
   ulong position_ticket;
   datetime entry_time;
   datetime entry_bar_time;
   int bars_elapsed;
   double position_volume;
   double position_price_open;
   double position_sl;
   double position_tp;
   double close_price_preview;
   long position_type;
   string position_comment;
   string exit_reason_preview;
   string lifecycle_status;
   string bar_count_status;
};

string BoolText(const bool value) { return value ? "true" : "false"; }
string FormatNumber(const double value) { return DoubleToString(value, 12); }
string SafeLongToString(const long value) { return IntegerToString(value); }
string TimeframeText() { return EnumToString(InpTimeframe); }
int CommonFileFlag() { return InpLogCommonFiles ? FILE_COMMON : 0; }
string LogFolder() { return "TradingBot\\" + InpLogPrefix + "\\" + g_run_id; }
string LogPath(const string file_name) { return LogFolder() + "\\" + file_name; }

string FormatTimeServer(const datetime value)
{
   if(value <= 0) return "";
   string text = TimeToString(value, TIME_DATE | TIME_SECONDS);
   StringReplace(text, ".", "-");
   return text;
}

string BuildGeneratedRunId()
{
   string compact = TimeToString(TimeLocal(), TIME_DATE | TIME_SECONDS);
   StringReplace(compact, ".", "");
   StringReplace(compact, ":", "");
   StringReplace(compact, " ", "_");
   return "lifecycle_watch_demo_" + compact;
}

string ResolveRunId()
{
   string configured = InpRunId;
   StringTrimLeft(configured);
   StringTrimRight(configured);
   if(StringLen(configured) > 0) return configured;
   return BuildGeneratedRunId();
}

string Hash32Text(const string text)
{
   uint hash = 2166136261;
   for(int index = 0; index < StringLen(text); index++)
   {
      hash ^= (uint)StringGetCharacter(text, index);
      hash *= 16777619;
   }
   return IntegerToString((long)hash);
}

string LifecycleDigest(const string canonical_value)
{
   return "lifecycle_attempt_digest_non_crypto_" + Hash32Text(canonical_value);
}

string LifecycleAttemptId(const ulong position_ticket,const string exit_reason)
{
   const string canonical = "candidate_id=" + CANDIDATE_ID +
      "|symbol=" + REQUIRED_SYMBOL +
      "|position_ticket=" + SafeLongToString((long)position_ticket) +
      "|exit_reason=" + exit_reason +
      "|run_id=" + g_run_id;
   return "lifecycle_attempt_" + Hash32Text(canonical);
}

string CloseRequestDigest(const LifecycleSnapshot &snapshot,const string exit_reason)
{
   const string canonical = "candidate_id=" + CANDIDATE_ID +
      "|symbol=" + REQUIRED_SYMBOL +
      "|position_ticket=" + SafeLongToString((long)snapshot.position_ticket) +
      "|entry_time=" + FormatTimeServer(snapshot.entry_time) +
      "|exit_reason=" + exit_reason +
      "|volume=" + FormatNumber(snapshot.position_volume) +
      "|close_price=" + FormatNumber(snapshot.close_price_preview) +
      "|magic=" + SafeLongToString(InpMagicNumber) +
      "|max_holding_bars=" + IntegerToString(InpMaxHoldingBars);
   return LifecycleDigest(canonical);
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
      Print("Unable to open lifecycle log file: ", path, " error=", GetLastError());
      write_header = false;
      return INVALID_HANDLE;
   }
   write_header = (!exists || FileSize(handle) == 0);
   FileSeek(handle, 0, SEEK_END);
   return handle;
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
   DeleteRunLogFile(LIFECYCLE_WATCH_LOG);
   DeleteRunLogFile(LIFECYCLE_EXIT_DECISION_LOG);
   DeleteRunLogFile(POSITION_CLOSE_LOG);
   DeleteRunLogFile(LIFECYCLE_RECONCILIATION_LOG);
   DeleteRunLogFile(LIFECYCLE_STATE_TRANSITION_LOG);
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

bool FridayForcedFlatRequired(const datetime timestamp)
{
   if(!IsFriday(timestamp)) return false;
   const datetime forced_flat_time = SameDayTime(timestamp, InpFridayForcedFlatTime);
   if(forced_flat_time <= 0) return false;
   return timestamp >= forced_flat_time;
}

bool IsDemoAccount() { return AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO; }
bool IsLiveAccount() { return AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL; }
bool SymbolAndInputOk() { return _Symbol == REQUIRED_SYMBOL && InpSymbol == REQUIRED_SYMBOL; }
bool TimeframeAndInputOk() { return _Period == REQUIRED_TIMEFRAME && InpTimeframe == REQUIRED_TIMEFRAME; }
bool TerminalTradeAllowed() { return (bool)TerminalInfoInteger(TERMINAL_TRADE_ALLOWED); }
bool ExpertTradeAllowed() { return (bool)MQLInfoInteger(MQL_TRADE_ALLOWED); }

bool SymbolTradeModeAllowsMarketClose()
{
   const long trade_mode = SymbolInfoInteger(InpSymbol, SYMBOL_TRADE_MODE);
   return trade_mode == SYMBOL_TRADE_MODE_FULL || trade_mode == SYMBOL_TRADE_MODE_CLOSEONLY;
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

datetime EntryBarTimeFromPositionTime(const datetime entry_time)
{
   if(entry_time <= 0) return 0;
   const int shift = iBarShift(InpSymbol, InpTimeframe, entry_time, false);
   if(shift < 0) return 0;
   return iTime(InpSymbol, InpTimeframe, shift);
}

int ClosedBarsAfterEntry(const datetime entry_bar_time,const datetime current_closed_bar_time)
{
   if(entry_bar_time <= 0 || current_closed_bar_time <= 0) return -1;
   const int entry_shift = iBarShift(InpSymbol, InpTimeframe, entry_bar_time, false);
   const int current_shift = iBarShift(InpSymbol, InpTimeframe, current_closed_bar_time, false);
   if(entry_shift < 0 || current_shift < 0) return -1;
   const int elapsed = entry_shift - current_shift;
   return elapsed < 0 ? 0 : elapsed;
}

void InitializeSnapshot(LifecycleSnapshot &snapshot,const datetime current_closed_bar_time)
{
   snapshot.timestamp_server = TimeCurrent();
   snapshot.current_closed_bar_time = current_closed_bar_time;
   snapshot.position_observed_open = false;
   snapshot.matching_position_count = 0;
   snapshot.pending_order_count = 0;
   snapshot.position_ticket = 0;
   snapshot.entry_time = 0;
   snapshot.entry_bar_time = 0;
   snapshot.bars_elapsed = -1;
   snapshot.position_volume = 0.0;
   snapshot.position_price_open = 0.0;
   snapshot.position_sl = 0.0;
   snapshot.position_tp = 0.0;
   snapshot.close_price_preview = 0.0;
   snapshot.position_type = -1;
   snapshot.position_comment = "";
   snapshot.exit_reason_preview = "none";
   snapshot.lifecycle_status = "no_position_observed";
   snapshot.bar_count_status = "not_applicable";
}

void ReadLifecycleSnapshot(LifecycleSnapshot &snapshot,const datetime current_closed_bar_time)
{
   InitializeSnapshot(snapshot, current_closed_bar_time);
   snapshot.pending_order_count = CountPendingOrdersForCandidate();

   for(int index = 0; index < PositionsTotal(); index++)
   {
      const ulong ticket = PositionGetTicket(index);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != REQUIRED_SYMBOL) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

      snapshot.matching_position_count++;
      if(snapshot.matching_position_count == 1)
      {
         snapshot.position_ticket = ticket;
         snapshot.entry_time = (datetime)PositionGetInteger(POSITION_TIME);
         snapshot.position_volume = PositionGetDouble(POSITION_VOLUME);
         snapshot.position_price_open = PositionGetDouble(POSITION_PRICE_OPEN);
         snapshot.position_sl = PositionGetDouble(POSITION_SL);
         snapshot.position_tp = PositionGetDouble(POSITION_TP);
         snapshot.position_type = (long)PositionGetInteger(POSITION_TYPE);
         snapshot.position_comment = PositionGetString(POSITION_COMMENT);
      }
   }

   if(snapshot.matching_position_count == 0)
   {
      snapshot.lifecycle_status = "no_position_observed";
      return;
   }

   if(snapshot.matching_position_count > 1)
   {
      snapshot.lifecycle_status = "multiple_matching_positions_blocked";
      return;
   }

   snapshot.position_observed_open = true;
   if(snapshot.position_type != POSITION_TYPE_SELL)
   {
      snapshot.lifecycle_status = "position_side_mismatch_blocked";
      return;
   }

   snapshot.entry_bar_time = EntryBarTimeFromPositionTime(snapshot.entry_time);
   if(snapshot.entry_bar_time <= 0)
   {
      snapshot.lifecycle_status = "entry_bar_time_unresolved";
      snapshot.bar_count_status = "entry_bar_time_unresolved";
      return;
   }

   snapshot.bars_elapsed = ClosedBarsAfterEntry(snapshot.entry_bar_time, current_closed_bar_time);
   if(snapshot.bars_elapsed < 0)
   {
      snapshot.lifecycle_status = "bar_count_unavailable";
      snapshot.bar_count_status = "bar_count_unavailable";
      return;
   }
   snapshot.bar_count_status = "ok";

   MqlTick tick;
   if(SymbolInfoTick(InpSymbol, tick) && tick.ask > 0.0)
      snapshot.close_price_preview = tick.ask;

   if(FridayForcedFlatRequired(snapshot.timestamp_server))
   {
      snapshot.exit_reason_preview = "friday_forced_flat";
      snapshot.lifecycle_status = "position_close_required_friday_forced_flat";
      return;
   }

   if(snapshot.bars_elapsed >= InpMaxHoldingBars)
   {
      snapshot.exit_reason_preview = "time_exit_10_m15_bars";
      snapshot.lifecycle_status = "position_close_required_time_exit";
      return;
   }

   snapshot.lifecycle_status = "position_observed_open";
}

string LifecycleAttemptForSnapshot(const LifecycleSnapshot &snapshot)
{
   if(snapshot.position_ticket == 0) return "";
   if(snapshot.exit_reason_preview == "none") return "";
   return LifecycleAttemptId(snapshot.position_ticket, snapshot.exit_reason_preview);
}

string DigestForSnapshot(const LifecycleSnapshot &snapshot)
{
   if(snapshot.position_ticket == 0) return "";
   if(snapshot.exit_reason_preview == "none") return "";
   return CloseRequestDigest(snapshot, snapshot.exit_reason_preview);
}

string StateForSnapshot(const LifecycleSnapshot &snapshot)
{
   if(snapshot.lifecycle_status == "position_close_required_time_exit") return "position_close_required_time_exit";
   if(snapshot.lifecycle_status == "position_close_required_friday_forced_flat") return "position_close_required_friday_forced_flat";
   if(snapshot.lifecycle_status == "position_observed_open") return "position_observed_open";
   if(snapshot.lifecycle_status == "no_position_observed") return "no_position_observed";
   return "position_close_preflight_blocked";
}

void WriteRunConfigHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","snapshot_type","candidate_id","symbol","timeframe","InpEnableLifecycleWatch","InpEnableLifecycleClosePreflight","InpEnableLifecycleClose","InpFinalLifecycleAcknowledgment","final_lifecycle_ack_valid","InpMaxLifecycleCloseAttempts","max_close_attempts_ok","InpRequireDemoAccount","InpAllowLiveAccount","InpLogCommonFiles","InpMagicNumber","InpMaxHoldingBars","InpFridayForcedFlatTime","InpFridayLastEntryTime","account_trade_mode","is_demo_account","is_live_account","terminal_trade_allowed","expert_trade_allowed");
}

void WriteRunConfigLog()
{
   bool write_header = false;
   const int handle = OpenLogForAppend(RUN_CONFIG_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteRunConfigHeader(handle);
   const bool final_ack_valid = (!InpEnableLifecycleClose || InpFinalLifecycleAcknowledgment == FINAL_LIFECYCLE_ACK_TEXT);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),"initial_lifecycle_run_config_snapshot",CANDIDATE_ID,InpSymbol,TimeframeText(),BoolText(InpEnableLifecycleWatch),BoolText(InpEnableLifecycleClosePreflight),BoolText(InpEnableLifecycleClose),InpFinalLifecycleAcknowledgment,BoolText(final_ack_valid),IntegerToString(InpMaxLifecycleCloseAttempts),BoolText(InpMaxLifecycleCloseAttempts == 1),BoolText(InpRequireDemoAccount),BoolText(InpAllowLiveAccount),BoolText(InpLogCommonFiles),SafeLongToString(InpMagicNumber),IntegerToString(InpMaxHoldingBars),InpFridayForcedFlatTime,InpFridayLastEntryTime,IntegerToString((int)AccountInfoInteger(ACCOUNT_TRADE_MODE)),BoolText(IsDemoAccount()),BoolText(IsLiveAccount()),BoolText(TerminalTradeAllowed()),BoolText(ExpertTradeAllowed()));
   FileClose(handle);
}

void WriteLifecycleWatchHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","timeframe","magic_number","position_observed_open","matching_position_count","position_ticket","entry_time","entry_bar_time","current_closed_bar_time","bars_elapsed","max_holding_bars","friday_forced_flat_time","exit_reason_preview","lifecycle_status");
}

void WriteLifecycleWatchLog(const LifecycleSnapshot &snapshot)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(LIFECYCLE_WATCH_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteLifecycleWatchHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(snapshot.timestamp_server),CANDIDATE_ID,InpSymbol,TimeframeText(),SafeLongToString(InpMagicNumber),BoolText(snapshot.position_observed_open),IntegerToString(snapshot.matching_position_count),snapshot.position_ticket > 0 ? SafeLongToString((long)snapshot.position_ticket) : "",FormatTimeServer(snapshot.entry_time),FormatTimeServer(snapshot.entry_bar_time),FormatTimeServer(snapshot.current_closed_bar_time),snapshot.bars_elapsed >= 0 ? IntegerToString(snapshot.bars_elapsed) : "",IntegerToString(InpMaxHoldingBars),InpFridayForcedFlatTime,snapshot.exit_reason_preview,snapshot.lifecycle_status);
   FileClose(handle);
}

void WriteExitDecisionHeader(const int handle)
{
   FileWrite(handle,"run_id","lifecycle_attempt_id","candidate_id","symbol","position_ticket","entry_time","entry_bar_time","current_time_server","bars_elapsed","exit_reason_preview","watch_enabled","close_preflight_enabled","position_close_enabled","final_lifecycle_ack_valid","decision","block_reason");
}

void WriteExitDecisionLog(const LifecycleSnapshot &snapshot,const string lifecycle_attempt_id,const string decision,const string block_reason)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(LIFECYCLE_EXIT_DECISION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteExitDecisionHeader(handle);
   const bool final_ack_valid = (!InpEnableLifecycleClose || InpFinalLifecycleAcknowledgment == FINAL_LIFECYCLE_ACK_TEXT);
   FileWrite(handle,g_run_id,lifecycle_attempt_id,CANDIDATE_ID,InpSymbol,snapshot.position_ticket > 0 ? SafeLongToString((long)snapshot.position_ticket) : "",FormatTimeServer(snapshot.entry_time),FormatTimeServer(snapshot.entry_bar_time),FormatTimeServer(snapshot.timestamp_server),snapshot.bars_elapsed >= 0 ? IntegerToString(snapshot.bars_elapsed) : "",snapshot.exit_reason_preview,BoolText(InpEnableLifecycleWatch),BoolText(InpEnableLifecycleClosePreflight),BoolText(InpEnableLifecycleClose),BoolText(final_ack_valid),decision,block_reason);
   FileClose(handle);
}

void WriteLifecycleCloseHeader(const int handle)
{
   FileWrite(handle,"run_id","lifecycle_attempt_id","candidate_id","symbol","position_ticket","entry_time","current_time_server","bars_elapsed","exit_reason","volume","close_price_preview","close_request_digest","close_called","close_attempt_count","close_retcode","close_comment","close_deal_ticket","close_order_ticket","close_confirmed","final_position_count","retry_performed","automatic_retry_allowed","position_close_status","block_reason");
}

void WriteLifecycleCloseLog(const LifecycleSnapshot &snapshot,const string lifecycle_attempt_id,const string close_request_digest,const string position_close_status,const string block_reason)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(POSITION_CLOSE_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteLifecycleCloseHeader(handle);
   FileWrite(handle,g_run_id,lifecycle_attempt_id,CANDIDATE_ID,InpSymbol,snapshot.position_ticket > 0 ? SafeLongToString((long)snapshot.position_ticket) : "",FormatTimeServer(snapshot.entry_time),FormatTimeServer(snapshot.timestamp_server),snapshot.bars_elapsed >= 0 ? IntegerToString(snapshot.bars_elapsed) : "",snapshot.exit_reason_preview,FormatNumber(snapshot.position_volume),snapshot.close_price_preview > 0.0 ? FormatNumber(snapshot.close_price_preview) : "",close_request_digest,"false","0","","","","","false",IntegerToString(snapshot.matching_position_count),"false","false",position_close_status,block_reason);
   FileClose(handle);
}

void WriteLifecycleReconciliationHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","magic_number","matching_position_count","pending_order_count","position_ticket","position_volume","position_price_open","position_sl","position_tp","reconciliation_status");
}

void WriteLifecycleReconciliationLog(const LifecycleSnapshot &snapshot)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(LIFECYCLE_RECONCILIATION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteLifecycleReconciliationHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(snapshot.timestamp_server),CANDIDATE_ID,InpSymbol,SafeLongToString(InpMagicNumber),IntegerToString(snapshot.matching_position_count),IntegerToString(snapshot.pending_order_count),snapshot.position_ticket > 0 ? SafeLongToString((long)snapshot.position_ticket) : "",FormatNumber(snapshot.position_volume),FormatNumber(snapshot.position_price_open),FormatNumber(snapshot.position_sl),FormatNumber(snapshot.position_tp),snapshot.lifecycle_status);
   FileClose(handle);
}

void WriteLifecycleStateTransitionHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","lifecycle_attempt_id","candidate_id","symbol","position_ticket","previous_state","next_state","exit_reason","source_gate","close_called","close_confirmed");
}

void WriteLifecycleStateTransitionLog(const LifecycleSnapshot &snapshot,const string lifecycle_attempt_id,const string next_state,const string source_gate)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(LIFECYCLE_STATE_TRANSITION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteLifecycleStateTransitionHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(snapshot.timestamp_server),lifecycle_attempt_id,CANDIDATE_ID,InpSymbol,snapshot.position_ticket > 0 ? SafeLongToString((long)snapshot.position_ticket) : "",g_current_lifecycle_state,next_state,snapshot.exit_reason_preview,source_gate,"false","false");
   FileClose(handle);
   g_current_lifecycle_state = next_state;
}

void EnsureLogHeaders()
{
   bool write_header = false;
   int handle = OpenLogForAppend(RUN_CONFIG_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteRunConfigHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(LIFECYCLE_WATCH_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteLifecycleWatchHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(LIFECYCLE_EXIT_DECISION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteExitDecisionHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(POSITION_CLOSE_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteLifecycleCloseHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(LIFECYCLE_RECONCILIATION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteLifecycleReconciliationHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(LIFECYCLE_STATE_TRANSITION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteLifecycleStateTransitionHeader(handle); FileClose(handle); }
}

string FirstPreflightBlockReason(const LifecycleSnapshot &snapshot,const string lifecycle_attempt_id)
{
   const bool final_ack_valid = (!InpEnableLifecycleClose || InpFinalLifecycleAcknowledgment == FINAL_LIFECYCLE_ACK_TEXT);
   const bool trade_allowed_ok = TerminalTradeAllowed() && ExpertTradeAllowed() && SymbolTradeModeAllowsMarketClose();
   if(!InpEnableLifecycleWatch) return "lifecycle_watch_disabled";
   if(snapshot.exit_reason_preview == "none") return "";
   if(!InpEnableLifecycleClosePreflight) return "lifecycle_close_preflight_disabled";
   if(!InpRequireDemoAccount) return "demo_requirement_disabled";
   if(!IsDemoAccount()) return "demo_account_required";
   if(InpAllowLiveAccount || IsLiveAccount()) return "live_account_forbidden";
   if(!SymbolAndInputOk()) return "symbol_not_locked";
   if(!TimeframeAndInputOk()) return "timeframe_not_locked";
   if(!snapshot.position_observed_open) return snapshot.lifecycle_status;
   if(snapshot.matching_position_count != 1) return "matching_position_count_not_one";
   if(snapshot.position_type != POSITION_TYPE_SELL) return "position_side_mismatch_blocked";
   if(InpMaxLifecycleCloseAttempts != 1) return "max_close_attempts_must_equal_one";
   if(lifecycle_attempt_id != "" && g_last_lifecycle_attempt_id == lifecycle_attempt_id) return "duplicate_lifecycle_attempt_exists";
   if(!trade_allowed_ok) return "trade_or_expert_disabled";
   if(!final_ack_valid) return "final_lifecycle_ack_missing_or_invalid";
   if(snapshot.close_price_preview <= 0.0) return "close_price_unavailable";
   return "";
}

void EvaluateLifecycle(const datetime current_closed_bar_time)
{
   LifecycleSnapshot snapshot;
   ReadLifecycleSnapshot(snapshot, current_closed_bar_time);
   if(!InpEnableLifecycleWatch)
      snapshot.lifecycle_status = "lifecycle_watch_disabled";

   const string lifecycle_attempt_id = LifecycleAttemptForSnapshot(snapshot);
   const string close_request_digest = DigestForSnapshot(snapshot);

   WriteLifecycleReconciliationLog(snapshot);
   WriteLifecycleWatchLog(snapshot);

   string decision = "no_action";
   string block_reason = "";
   string close_status = "no_close_not_required";
   string next_state = StateForSnapshot(snapshot);

   if(!InpEnableLifecycleWatch)
   {
      decision = "blocked";
      block_reason = "lifecycle_watch_disabled";
      close_status = "no_close_watch_disabled";
      next_state = "position_close_preflight_blocked";
   }
   else if(snapshot.lifecycle_status == "no_position_observed")
   {
      decision = "no_action";
      close_status = "no_close_no_position";
      next_state = "no_position_observed";
   }
   else if(snapshot.lifecycle_status == "multiple_matching_positions_blocked" ||
           snapshot.lifecycle_status == "position_side_mismatch_blocked" ||
           snapshot.lifecycle_status == "entry_bar_time_unresolved" ||
           snapshot.lifecycle_status == "bar_count_unavailable")
   {
      decision = "blocked";
      block_reason = snapshot.lifecycle_status;
      close_status = "no_close_blocked";
      next_state = "position_close_preflight_blocked";
   }
   else if(snapshot.exit_reason_preview == "none")
   {
      decision = "no_action";
      close_status = "no_close_not_required";
      next_state = "position_observed_open";
   }
   else
   {
      next_state = StateForSnapshot(snapshot);
      WriteLifecycleStateTransitionLog(snapshot,lifecycle_attempt_id,next_state,"exit_decision");
      block_reason = FirstPreflightBlockReason(snapshot, lifecycle_attempt_id);
      if(block_reason == "")
      {
         decision = "position_close_preflight_passed_no_close";
         close_status = "position_close_preflight_passed_no_close";
         next_state = "position_close_preflight_passed_no_close";
         g_last_lifecycle_attempt_id = lifecycle_attempt_id;
      }
      else
      {
         decision = "blocked";
         close_status = "no_close_blocked";
         next_state = "position_close_preflight_blocked";
      }
   }

   WriteExitDecisionLog(snapshot,lifecycle_attempt_id,decision,block_reason);
   WriteLifecycleCloseLog(snapshot,lifecycle_attempt_id,close_request_digest,close_status,block_reason);
   WriteLifecycleStateTransitionLog(snapshot,lifecycle_attempt_id,next_state,decision);
}

bool ValidateChartAndInputs()
{
   if(InpAllowLiveAccount)
   {
      Print("Lifecycle watch demo-only blocked: live account input must remain false.");
      return false;
   }
   if(InpMaxLifecycleCloseAttempts != 1)
   {
      Print("Lifecycle watch demo-only blocked: max close attempts must equal 1.");
      return false;
   }
   if(InpMaxHoldingBars != REQUIRED_MAX_HOLDING_BARS)
   {
      Print("Lifecycle watch demo-only blocked: max holding bars must equal 10.");
      return false;
   }
   if(InpSymbol != REQUIRED_SYMBOL || _Symbol != REQUIRED_SYMBOL)
   {
      Print("Lifecycle watch demo-only blocked: symbol must be ", REQUIRED_SYMBOL);
      return false;
   }
   if(InpTimeframe != REQUIRED_TIMEFRAME || _Period != REQUIRED_TIMEFRAME)
   {
      Print("Lifecycle watch demo-only blocked: timeframe must be M15.");
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
   Print("Lifecycle watch demo-only initialized: candidate=",CANDIDATE_ID," watch=",BoolText(InpEnableLifecycleWatch)," preflight=",BoolText(InpEnableLifecycleClosePreflight)," lifecycle_close_input=",BoolText(InpEnableLifecycleClose)," require_demo=",BoolText(InpRequireDemoAccount)," allow_live=",BoolText(InpAllowLiveAccount)," run_id=",g_run_id," log_folder=",LogFolder());
   return INIT_SUCCEEDED;
}

void OnTick()
{
   const datetime current_closed_bar_time = iTime(InpSymbol, InpTimeframe, 1);
   if(current_closed_bar_time <= 0) return;
   if(current_closed_bar_time == g_last_evaluated_closed_bar_time) return;
   g_last_evaluated_closed_bar_time = current_closed_bar_time;
   EvaluateLifecycle(current_closed_bar_time);
}
