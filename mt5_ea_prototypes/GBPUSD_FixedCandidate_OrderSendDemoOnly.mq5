#property strict
#property version   "1.000"
#property description "Demo-only single-attempt-per-signal prototype for gbpusd_short_h10_1_5_off_hours."
#property description "One gated broker transmission attempt per attempt_id, no close, no retry."

input bool InpEnableOrderCheck = false;
input bool InpEnableSendPreflight = false;
input bool InpEnableOrderSend = false;
input bool InpEnableIntegratedLifecycleWatch = false;
input bool InpEnableIntegratedLifecycleClosePreflight = false;
input bool InpEnableIntegratedLifecycleClose = false;
input string InpFinalSendAcknowledgment = "";
input string InpFinalLifecycleAcknowledgment = "";
input int InpMaxOrderSendAttempts = 1;
input int InpMaxLifecycleCloseAttempts = 1;
input bool InpRequireDemoAccount = true;
input bool InpAllowLiveAccount = false;
input string InpSymbol = "GBPUSD";
input ENUM_TIMEFRAMES InpTimeframe = PERIOD_M15;
input string InpRunId = "";
input bool InpOverwriteLogsOnInit = true;
input bool InpLogCommonFiles = true;
input double InpVolumeLots = 0.01;
input bool InpUseRiskBasedSizing = false;
input double InpRiskPercentPerTrade = 0.5;
input double InpMaxRiskPercentPerTrade = 0.5;
input long InpMagicNumber = 1510152345;
input int InpMaxSpreadPoints = 15;
input int InpMaxHoldingBars = 10;
input string InpFridayLastEntryTime = "23:15";
input string InpFridayForcedFlatTime = "23:45";
input string InpLogPrefix = "gbpusd_short_h10_1_5_off_hours";

const string CANDIDATE_ID = "gbpusd_short_h10_1_5_off_hours";
const string REQUIRED_SYMBOL = "GBPUSD";
const ENUM_TIMEFRAMES REQUIRED_TIMEFRAME = PERIOD_M15;
const string SIDE_SELL = "sell";
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
const string PREFLIGHT_COMMENT = "GBPH10SPF";
const string LIFECYCLE_CLOSE_COMMENT = "GBPH10CLS";
const string FINAL_SEND_ACK_TEXT = "confirm_single_demo_send_only";
const string FINAL_LIFECYCLE_ACK_TEXT = "confirm_single_demo_lifecycle_close_only";
const string RUN_CONFIG_LOG = "run_config_log.csv";
const string ENTRY_SIGNAL_FRESHNESS_LOG = "entry_signal_freshness_log.csv";
const string SIGNAL_LOG = "signal_log.csv";
const string DECISION_LOG = "decision_log.csv";
const string ORDER_CHECK_LOG = "order_check_log.csv";
const string SEND_PREFLIGHT_LOG = "send_preflight_log.csv";
const string ORDER_SEND_LOG = "order_send_log.csv";
const string POSITION_SIZING_LOG = "position_sizing_log.csv";
const string STATE_TRANSITION_LOG = "state_transition_log.csv";
const string POST_SEND_RECONCILIATION_LOG = "post_send_reconciliation_log.csv";
const string RUN_FINAL_SUMMARY_LOG = "run_final_summary_log.csv";
const string TRADE_TRANSACTIONS_LOG = "trade_transactions_log.csv";
const string RECONCILIATION_LOG = "reconciliation_log.csv";
const string POSITION_LIFECYCLE_LOG = "position_lifecycle_log.csv";
const string INTEGRATED_LIFECYCLE_WATCH_LOG = "integrated_lifecycle_watch_log.csv";
const string INTEGRATED_LIFECYCLE_EXIT_DECISION_LOG = "integrated_lifecycle_exit_decision_log.csv";
const string INTEGRATED_LIFECYCLE_RECONCILIATION_LOG = "integrated_lifecycle_reconciliation_log.csv";
const string INTEGRATED_LIFECYCLE_STATE_TRANSITION_LOG = "integrated_lifecycle_state_transition_log.csv";
const string INTEGRATED_POSITION_CLOSE_LOG = "integrated_position_close_log.csv";
const string STATIC_GUARD_ORDER_SEND_ATTEMPT_COUNT_FIELD = "order_send_attempt_count";
const string STATIC_GUARD_RETRY_PERFORMED_FALSE = "retry_performed,false";
const string STATIC_GUARD_AUTOMATIC_RETRY_ALLOWED_FALSE = "automatic_retry_allowed,false";
const string STATIC_GUARD_INTEGRATED_CLOSE_CALLED_FALSE = "close_called=false";
const string STATIC_GUARD_INTEGRATED_CLOSE_ATTEMPT_COUNT_ZERO = "close_attempt_count=0";
const string STATIC_GUARD_INTEGRATED_RETRY_PERFORMED_FALSE = "retry_performed=false";
const string STATIC_GUARD_INTEGRATED_AUTOMATIC_RETRY_ALLOWED_FALSE = "automatic_retry_allowed=false";
const string STATIC_GUARD_SIZING_FIXED_VOLUME_USED = "sizing_fixed_volume_used";
const string STATIC_GUARD_SIZING_RISK_BASED_PASSED = "sizing_risk_based_passed";
const string STATIC_GUARD_SIZING_RISK_PERCENT_INVALID = "sizing_risk_percent_invalid";
const string STATIC_GUARD_SIZING_SL_DISTANCE_INVALID = "sizing_sl_distance_invalid";
const string STATIC_GUARD_SIZING_TICK_VALUE_UNAVAILABLE = "sizing_tick_value_unavailable";
const string STATIC_GUARD_SIZING_VOLUME_BELOW_MIN_LOT = "sizing_volume_below_min_lot";
const string STATIC_GUARD_SIZING_VOLUME_ABOVE_MAX_LOT = "sizing_volume_above_max_lot";
const string STATIC_GUARD_SIZING_EFFECTIVE_RISK_EXCEEDS_POLICY = "sizing_effective_risk_exceeds_policy";
const string STATIC_GUARD_SIZING_MARGIN_CHECK_FAILED = "sizing_margin_check_failed";

string g_run_id = "";
string g_session_instance_id = "";
datetime g_last_evaluated_bar_time = 0;
datetime g_last_duplicate_logged_bar_time = 0;
datetime g_entry_signal_baseline_closed_bar_time = 0;
bool g_entry_signal_baseline_established = false;
bool g_entry_signal_first_valid_tick_observed = false;
bool g_entry_signal_history_unavailable_logged = false;
datetime g_last_order_check_bar_time = 0;
datetime g_last_integrated_lifecycle_evaluated_bar_time = 0;
datetime g_last_integrated_lifecycle_forced_flat_time = 0;
string g_current_state = "initialized";
string g_current_integrated_lifecycle_state = "initialized";
string g_last_signal_id = "";
string g_last_attempt_id = "";
string g_last_order_send_attempt_id = "";
ulong g_confirmed_position_ticket = 0;
string g_confirmed_entry_signal_id = "";
string g_confirmed_entry_attempt_id = "";
datetime g_confirmed_entry_time = 0;
datetime g_confirmed_entry_bar_time = 0;
ulong g_confirmed_order_ticket = 0;
ulong g_confirmed_deal_ticket = 0;
bool g_any_order_send_called = false;
int g_total_order_send_attempt_count = 0;
int g_execution_confirmed_count = 0;
int g_rejected_count = 0;
int g_uncertain_count = 0;
bool g_retry_performed = false;
bool g_automatic_retry_allowed = false;
int g_lifecycle_close_called_count = 0;
int g_lifecycle_close_confirmed_count = 0;
int g_lifecycle_close_rejected_count = 0;
int g_lifecycle_close_uncertain_count = 0;
int g_lifecycle_close_skipped_already_closed_count = 0;
int g_lifecycle_close_duplicate_blocked_count = 0;
int g_lifecycle_close_time_exit_count = 0;
int g_lifecycle_close_friday_forced_flat_count = 0;
int g_lifecycle_close_unresolved_identity_blocked_count = 0;
int g_manual_intervention_required_count = 0;
int g_sizing_mode_fixed_count = 0;
int g_sizing_mode_risk_based_count = 0;
int g_sizing_risk_based_passed_count = 0;
int g_sizing_fixed_volume_used_count = 0;
int g_sizing_blocked_count = 0;
int g_sizing_risk_percent_invalid_count = 0;
int g_sizing_volume_below_min_lot_count = 0;
int g_sizing_volume_above_max_lot_count = 0;
int g_sizing_effective_risk_exceeds_policy_count = 0;
int g_sizing_tick_value_unavailable_count = 0;
bool g_sizing_effective_risk_seen = false;
double g_sizing_min_effective_risk_percent = 0.0;
double g_sizing_max_effective_risk_percent = 0.0;
bool g_sizing_volume_seen = false;
double g_sizing_min_volume_lots = 0.0;
double g_sizing_max_volume_lots = 0.0;
int g_deal_add_observed_count = 0;
int g_deal_history_lookup_success_count = 0;
int g_deal_history_lookup_unavailable_count = 0;
int g_stop_loss_exit_observed_count = 0;
int g_take_profit_exit_observed_count = 0;
int g_other_exit_observed_count = 0;
string g_lifecycle_close_preflight_keys[];
string g_lifecycle_close_sent_attempt_ids[];
bool g_integrated_lifecycle_uncertain_hold = false;

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

struct BrokerSnapshot
{
   int position_count;
   int pending_order_count;
   string broker_state;
   ulong first_position_ticket;
   ulong first_pending_order_ticket;
};

struct IntegratedLifecycleSnapshot
{
   datetime timestamp_server;
   datetime current_closed_bar_time;
   bool watch_enabled;
   bool position_observed_open;
   int matching_position_count;
   int pending_order_count;
   ulong position_ticket;
   long position_type;
   double position_volume;
   double position_price_open;
   double position_sl;
   double position_tp;
   datetime entry_time;
   datetime entry_bar_time;
   int bars_elapsed;
   string bar_count_status;
   string exit_reason_preview;
   string signal_id;
   string attempt_id;
   string position_identity_status;
   string integrated_lifecycle_status;
};

struct IntegratedLifecycleCloseAudit
{
   string lifecycle_close_attempt_id;
   string close_request_digest;
   string close_request_digest_preflight;
   string close_request_digest_before_send;
   bool close_request_unchanged_after_preflight;
   double close_price_preview;
   double close_request_price;
   double close_result_bid;
   double close_result_ask;
   double close_result_volume;
   string close_preflight_status;
   string block_reason;
   int final_position_count;
   bool close_called;
   int close_attempt_count;
   uint close_retcode;
   string close_comment;
   ulong close_deal_ticket;
   ulong close_order_ticket;
   bool close_confirmed;
   string post_close_reconciliation_status;
   string close_result_category;
   string close_identity_status;
   bool lifecycle_close_sent;
   string lifecycle_close_result_status;
   bool manual_intervention_required;
   string unresolved_policy_action;
   bool retry_performed;
   bool automatic_retry_allowed;
};
struct PositionSizingAudit
{
   datetime bar_time;
   string attempt_id;
   string signal_id;
   string sizing_phase;
   string sizing_mode;
   double fixed_volume_lots;
   double risk_percent_per_trade;
   double max_risk_percent_per_trade;
   string risk_account_basis;
   double account_equity;
   double account_balance;
   double risk_amount_account_currency;
   double entry_price;
   double sl_price;
   double tp_price;
   double sl_distance_price;
   double loss_per_1_lot_at_sl;
   double raw_risk_volume_lots;
   double normalized_risk_volume_lots;
   double volume_min;
   double volume_max;
   double volume_step;
   double effective_risk_amount;
   double effective_risk_percent;
   double expected_tp_amount;
   double risk_reward_ratio;
   string sizing_status;
   string sizing_block_reason;
   bool sizing_passed;
   string sizing_digest;
};

struct RequestAudit
{
   double volume;
   double price;
   double sl;
   double tp;
   string comment;
   string canonical_request;
   string request_digest;
   PositionSizingAudit sizing;
};

struct SendPreflightAudit
{
   datetime bar_time;
   string attempt_id;
   string signal_id;
   double volume;
   double price;
   double sl;
   double tp;
   string comment;
   string request_digest;
   string order_check_digest;
   bool order_check_called;
   bool order_check_passed;
   bool send_preflight_enabled;
   bool order_send_enabled;
   bool final_ack_valid;
   int max_order_send_attempts;
   bool max_order_send_attempts_ok;
   bool demo_account_ok;
   bool live_account_forbidden_ok;
   bool spread_ok;
   bool one_position_only_ok;
   bool pending_order_ok;
   bool friday_entry_cutoff_ok;
   bool digest_unchanged;
   bool previous_send_attempt_exists;
   bool order_send_called;
   int order_send_attempt_count;
   bool execution_performed;
   string send_preflight_status;
   string block_reason;
   PositionSizingAudit sizing;
};

struct OrderSendAudit
{
   datetime bar_time;
   string attempt_id;
   string signal_id;
   double volume;
   double price;
   double sl;
   double tp;
   string comment;
   string request_digest;
   string order_check_digest;
   bool order_send_called;
   int order_send_attempt_count;
   uint order_send_retcode;
   string order_send_retcode_name;
   string order_send_comment;
   uint order_send_request_id;
   ulong order_ticket;
   ulong deal_ticket;
   ulong position_ticket;
   bool execution_confirmed;
   bool broker_ticket_expected;
   string order_send_result_category;
   bool retry_performed;
   bool automatic_retry_allowed;
   string post_send_reconciliation_status;
   string final_state_status;
   PositionSizingAudit sizing;
};

struct DealHistoryObservation
{
   bool is_deal_add;
   bool history_lookup_succeeded;
   ulong transaction_position_ticket;
   ulong deal_ticket;
   ulong order_ticket;
   long deal_position_id;
   string symbol;
   long magic;
   long deal_time;
   long deal_time_msc;
   long deal_type_raw;
   string deal_type_name;
   long deal_entry_raw;
   string deal_entry_name;
   long deal_reason_raw;
   string deal_reason_name;
   double deal_price;
   double deal_volume;
   double deal_profit;
   double deal_commission;
   double deal_swap;
   double deal_fee;
   string deal_comment;
   string deal_external_id;
   string deal_core_fields_source;
   string history_lookup_status;
   long history_lookup_error_code;
   string history_lookup_error_text;
   string history_getter_status;
   long history_getter_error_code;
   string history_getter_error_text;
   string missing_history_fields;
   bool deal_ticket_valid;
   bool order_ticket_valid;
   bool deal_position_id_valid;
   bool symbol_valid;
   bool magic_valid;
   bool deal_time_valid;
   bool deal_time_msc_valid;
   bool deal_type_valid;
   bool deal_entry_valid;
   bool deal_reason_valid;
   bool deal_price_valid;
   bool deal_volume_valid;
   bool deal_profit_valid;
   bool deal_commission_valid;
   bool deal_swap_valid;
   bool deal_fee_valid;
   bool deal_comment_valid;
   bool deal_external_id_valid;
   bool classification_core_getters_valid;
   bool core_getters_success;
   bool economic_getters_complete;
   bool text_getters_complete;
   bool deal_type_recognized;
   string deal_event_classification;
};

string BoolText(const bool value) { return value ? "true" : "false"; }
string FormatNumber(const double value) { return DoubleToString(value, 12); }
string SafeLongToString(const long value) { return IntegerToString(value); }
string FormatOptionalNumber(const double value, const bool enabled) { return enabled ? FormatNumber(value) : ""; }
string TimeframeText() { return EnumToString(InpTimeframe); }
int CommonFileFlag() { return InpLogCommonFiles ? FILE_COMMON : 0; }
string LogFolder() { return "TradingBot\\" + InpLogPrefix + "\\" + g_run_id; }
string LogPath(const string file_name) { return LogFolder() + "\\" + file_name; }

string CsvEscape(string value)
{
   const string quote = CharToString(34);
   const string carriage_return = CharToString(13);
   const string line_feed = CharToString(10);
   const bool must_quote = StringFind(value, ",") >= 0 || StringFind(value, quote) >= 0 || StringFind(value, carriage_return) >= 0 || StringFind(value, line_feed) >= 0;
   StringReplace(value, carriage_return, " ");
   StringReplace(value, line_feed, " ");
   StringReplace(value, quote, quote + quote);
   return must_quote ? quote + value + quote : value;
}

string BuildGeneratedRunId()
{
   string compact = TimeToString(TimeLocal(), TIME_DATE | TIME_SECONDS);
   StringReplace(compact, ".", "");
   StringReplace(compact, ":", "");
   StringReplace(compact, " ", "_");
   return "send_preflight_demo_" + compact;
}

string ResolveRunId()
{
   string configured = InpRunId;
   StringTrimLeft(configured);
   StringTrimRight(configured);
   if(StringLen(configured) > 0) return configured;

   const string generated = BuildGeneratedRunId();
   if(StringLen(generated) > 0) return generated;
   return "send_preflight_demo_unset";
}

string BuildSessionInstanceId()
{
   string compact = TimeToString(TimeLocal(), TIME_DATE | TIME_SECONDS);
   StringReplace(compact, ".", "");
   StringReplace(compact, ":", "");
   StringReplace(compact, " ", "_");
   return "session_" + compact +
      "_chart_" + SafeLongToString(ChartID()) +
      "_uptime_ms_" + SafeLongToString((long)GetTickCount64()) +
      "_instance_us_" + SafeLongToString((long)GetMicrosecondCount());
}

string FormatTimeServer(const datetime value)
{
   if(value <= 0) return "";
   string text = TimeToString(value, TIME_DATE | TIME_SECONDS);
   StringReplace(text, ".", "-");
   return text;
}

string CompactTimeForId(const datetime value)
{
   string text = TimeToString(value, TIME_DATE | TIME_MINUTES);
   StringReplace(text, ".", "");
   StringReplace(text, ":", "");
   StringReplace(text, " ", "");
   return text;
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

string NonCryptoDigest(const string canonical_request)
{
   return "request_digest_non_crypto_" + Hash32Text(canonical_request);
}

string StableId(const string prefix, const string canonical_value)
{
   return prefix + "_" + Hash32Text(canonical_value);
}

string SignalId(const datetime bar_time)
{
   const string canonical = "candidate_id=" + CANDIDATE_ID +
      "|symbol=" + REQUIRED_SYMBOL +
      "|timeframe=M15" +
      "|bar_time=" + FormatTimeServer(bar_time) +
      "|side=" + SIDE_SELL;
   return "signal_" + CompactTimeForId(bar_time) + "_" + Hash32Text(canonical);
}

string AttemptId(const string signal_id)
{
   const string canonical = "signal_id=" + signal_id +
      "|run_id=" + g_run_id +
      "|phase=send_preflight";
   return StableId("attempt", canonical);
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

bool FridayEntryCutoffOk(const datetime server_time)
{
   if(!IsFriday(server_time)) return true;
   const datetime last_entry_time = SameDayTime(server_time, InpFridayLastEntryTime);
   if(last_entry_time <= 0) return false;
   return server_time <= last_entry_time;
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

void WriteEntrySignalFreshnessHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","timeframe","event","baseline_source","baseline_closed_bar_time","observed_closed_bar_time","last_observed_closed_bar_time","entry_signal_freshness_status","entry_processing_allowed","reason");
}

void WriteEntrySignalFreshnessLog(const string event_name,const string baseline_source,const datetime observed_closed_bar_time,const string freshness_status,const bool entry_processing_allowed,const string reason)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(ENTRY_SIGNAL_FRESHNESS_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteEntrySignalFreshnessHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),CANDIDATE_ID,InpSymbol,TimeframeText(),event_name,baseline_source,FormatTimeServer(g_entry_signal_baseline_closed_bar_time),FormatTimeServer(observed_closed_bar_time),FormatTimeServer(g_last_evaluated_bar_time),freshness_status,BoolText(entry_processing_allowed),reason);
   FileClose(handle);
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
   FileWrite(handle,"run_id","timestamp_server","attempt_id","signal_id","candidate_id","bar_time","signal_bool","demo_account_ok","live_account_forbidden_ok","symbol_ok","timeframe_ok","spread_ok","one_position_only_ok","pending_order_ok","friday_entry_cutoff_ok","trade_allowed_ok","expert_trade_allowed_ok","volume_ok","sl_tp_ok","sizing_mode","sizing_status","sizing_block_reason","final_volume_lots","effective_risk_percent","order_check_enabled","send_preflight_enabled","order_send_enabled","final_ack_valid","max_order_send_attempts_ok","decision","block_reason","order_send_called","order_send_attempt_count","execution_performed");
}

void WriteDecisionLog(const datetime bar_time,const string attempt_id,const string signal_id,const bool signal_bool,const bool demo_account_ok,const bool live_account_forbidden_ok,const bool symbol_ok,const bool timeframe_ok,const bool spread_ok,const bool one_position_only_ok,const bool pending_order_ok,const bool friday_entry_cutoff_ok,const bool trade_allowed_ok,const bool expert_trade_allowed_ok,const bool volume_ok,const bool sl_tp_ok,const string decision,const string block_reason,const string sizing_mode="",const string sizing_status="",const string sizing_block_reason="",const double final_volume_lots=0.0,const double effective_risk_percent=0.0)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(DECISION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteDecisionHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),attempt_id,signal_id,CANDIDATE_ID,FormatTimeServer(bar_time),BoolText(signal_bool),BoolText(demo_account_ok),BoolText(live_account_forbidden_ok),BoolText(symbol_ok),BoolText(timeframe_ok),BoolText(spread_ok),BoolText(one_position_only_ok),BoolText(pending_order_ok),BoolText(friday_entry_cutoff_ok),BoolText(trade_allowed_ok),BoolText(expert_trade_allowed_ok),BoolText(volume_ok),BoolText(sl_tp_ok),sizing_mode,sizing_status,sizing_block_reason,final_volume_lots > 0.0 ? FormatNumber(final_volume_lots) : "",effective_risk_percent > 0.0 ? FormatNumber(effective_risk_percent) : "",BoolText(InpEnableOrderCheck),BoolText(InpEnableSendPreflight),BoolText(InpEnableOrderSend),BoolText(InpFinalSendAcknowledgment == FINAL_SEND_ACK_TEXT),BoolText(InpMaxOrderSendAttempts == 1),decision,block_reason,"false","0","false");
   FileClose(handle);
}

void WriteOrderCheckHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","attempt_id","signal_id","candidate_id","bar_time","magic_number","comment","symbol","side","volume","price","sl","tp","request_digest","order_check_digest","sizing_mode","risk_percent_per_trade","risk_account_basis","account_equity","risk_amount_account_currency","loss_per_1_lot_at_sl","raw_risk_volume_lots","normalized_risk_volume_lots","effective_risk_amount","effective_risk_percent","expected_tp_amount","risk_reward_ratio","sizing_status","sizing_block_reason","order_check_called","order_check_passed","order_check_retcode","order_check_comment","order_check_balance","order_check_equity","order_check_margin","order_check_margin_free","order_check_margin_level","order_send_called","order_send_attempt_count","execution_performed","block_reason");
}

void WriteOrderCheckLog(const datetime bar_time,const string attempt_id,const string signal_id,const RequestAudit &audit,const bool called,const bool passed,const MqlTradeCheckResult &check_result,const string block_reason)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(ORDER_CHECK_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteOrderCheckHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),attempt_id,signal_id,CANDIDATE_ID,FormatTimeServer(bar_time),SafeLongToString(InpMagicNumber),audit.comment,InpSymbol,SIDE_SELL,FormatNumber(audit.volume),FormatNumber(audit.price),FormatNumber(audit.sl),FormatNumber(audit.tp),audit.request_digest,audit.request_digest,audit.sizing.sizing_mode,FormatNumber(audit.sizing.risk_percent_per_trade),audit.sizing.risk_account_basis,FormatNumber(audit.sizing.account_equity),FormatNumber(audit.sizing.risk_amount_account_currency),FormatNumber(audit.sizing.loss_per_1_lot_at_sl),FormatNumber(audit.sizing.raw_risk_volume_lots),FormatNumber(audit.sizing.normalized_risk_volume_lots),FormatNumber(audit.sizing.effective_risk_amount),FormatNumber(audit.sizing.effective_risk_percent),FormatNumber(audit.sizing.expected_tp_amount),FormatNumber(audit.sizing.risk_reward_ratio),audit.sizing.sizing_status,audit.sizing.sizing_block_reason,BoolText(called),BoolText(passed),called ? IntegerToString((int)check_result.retcode) : "",called ? check_result.comment : "",called ? FormatNumber(check_result.balance) : "",called ? FormatNumber(check_result.equity) : "",called ? FormatNumber(check_result.margin) : "",called ? FormatNumber(check_result.margin_free) : "",called ? FormatNumber(check_result.margin_level) : "","false","0","false",block_reason);
   FileClose(handle);
}

void WriteSendPreflightHeader(const int handle)
{
   FileWrite(handle,"run_id","attempt_id","signal_id","candidate_id","bar_time","timestamp_server","symbol","side","volume","price","sl","tp","magic_number","comment","request_digest","order_check_digest","sizing_mode","risk_percent_per_trade","risk_account_basis","account_equity","risk_amount_account_currency","normalized_risk_volume_lots","effective_risk_percent","sizing_status","sizing_block_reason","order_check_called","order_check_passed","send_preflight_enabled","order_send_enabled","final_ack_valid","max_order_send_attempts","max_order_send_attempts_ok","demo_account_ok","live_account_forbidden_ok","spread_ok","one_position_only_ok","pending_order_ok","friday_entry_cutoff_ok","digest_unchanged","previous_send_attempt_exists","send_preflight_status","block_reason","order_send_called","order_send_attempt_count","execution_performed");
}

void WriteSendPreflightLog(const SendPreflightAudit &audit)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(SEND_PREFLIGHT_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteSendPreflightHeader(handle);
   FileWrite(handle,g_run_id,audit.attempt_id,audit.signal_id,CANDIDATE_ID,FormatTimeServer(audit.bar_time),FormatTimeServer(TimeCurrent()),InpSymbol,SIDE_SELL,FormatNumber(audit.volume),FormatNumber(audit.price),FormatNumber(audit.sl),FormatNumber(audit.tp),SafeLongToString(InpMagicNumber),audit.comment,audit.request_digest,audit.order_check_digest,audit.sizing.sizing_mode,FormatNumber(audit.sizing.risk_percent_per_trade),audit.sizing.risk_account_basis,FormatNumber(audit.sizing.account_equity),FormatNumber(audit.sizing.risk_amount_account_currency),FormatNumber(audit.sizing.normalized_risk_volume_lots),FormatNumber(audit.sizing.effective_risk_percent),audit.sizing.sizing_status,audit.sizing.sizing_block_reason,BoolText(audit.order_check_called),BoolText(audit.order_check_passed),BoolText(audit.send_preflight_enabled),BoolText(audit.order_send_enabled),BoolText(audit.final_ack_valid),IntegerToString(audit.max_order_send_attempts),BoolText(audit.max_order_send_attempts_ok),BoolText(audit.demo_account_ok),BoolText(audit.live_account_forbidden_ok),BoolText(audit.spread_ok),BoolText(audit.one_position_only_ok),BoolText(audit.pending_order_ok),BoolText(audit.friday_entry_cutoff_ok),BoolText(audit.digest_unchanged),BoolText(audit.previous_send_attempt_exists),audit.send_preflight_status,audit.block_reason,BoolText(audit.order_send_called),IntegerToString(audit.order_send_attempt_count),BoolText(audit.execution_performed));
   FileClose(handle);
}

void WriteOrderSendHeader(const int handle)
{
   FileWrite(handle,"run_id","attempt_id","signal_id","candidate_id","bar_time","timestamp_server","symbol","side","volume","price","sl","tp","magic_number","comment","request_digest","order_check_digest","sizing_mode","risk_percent_per_trade","risk_account_basis","account_equity","risk_amount_account_currency","normalized_risk_volume_lots","effective_risk_amount","effective_risk_percent","expected_tp_amount","sizing_status","sizing_block_reason","order_send_called","order_send_attempt_count","order_send_retcode","order_send_retcode_name","order_send_comment","order_send_request_id","order_ticket","deal_ticket","position_ticket","execution_confirmed","broker_ticket_expected","order_send_result_category","retry_performed","automatic_retry_allowed","post_send_reconciliation_status","final_state_status");
}

void WriteOrderSendLog(const OrderSendAudit &audit)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(ORDER_SEND_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteOrderSendHeader(handle);
   FileWrite(handle,g_run_id,audit.attempt_id,audit.signal_id,CANDIDATE_ID,FormatTimeServer(audit.bar_time),FormatTimeServer(TimeCurrent()),InpSymbol,SIDE_SELL,FormatNumber(audit.volume),FormatNumber(audit.price),FormatNumber(audit.sl),FormatNumber(audit.tp),SafeLongToString(InpMagicNumber),audit.comment,audit.request_digest,audit.order_check_digest,audit.sizing.sizing_mode,FormatNumber(audit.sizing.risk_percent_per_trade),audit.sizing.risk_account_basis,FormatNumber(audit.sizing.account_equity),FormatNumber(audit.sizing.risk_amount_account_currency),FormatNumber(audit.sizing.normalized_risk_volume_lots),FormatNumber(audit.sizing.effective_risk_amount),FormatNumber(audit.sizing.effective_risk_percent),FormatNumber(audit.sizing.expected_tp_amount),audit.sizing.sizing_status,audit.sizing.sizing_block_reason,BoolText(audit.order_send_called),IntegerToString(audit.order_send_attempt_count),audit.order_send_called ? IntegerToString((int)audit.order_send_retcode) : "",audit.order_send_retcode_name,audit.order_send_comment,audit.order_send_called ? IntegerToString((int)audit.order_send_request_id) : "",audit.order_send_called ? SafeLongToString((long)audit.order_ticket) : "",audit.order_send_called ? SafeLongToString((long)audit.deal_ticket) : "",audit.position_ticket > 0 ? SafeLongToString((long)audit.position_ticket) : "",BoolText(audit.execution_confirmed),BoolText(audit.broker_ticket_expected),audit.order_send_result_category,BoolText(audit.retry_performed),BoolText(audit.automatic_retry_allowed),audit.post_send_reconciliation_status,audit.final_state_status);
   FileClose(handle);
}
void WritePositionSizingHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","attempt_id","signal_id","candidate_id","bar_time","sizing_phase","sizing_mode","fixed_volume_lots","risk_percent_per_trade","max_risk_percent_per_trade","risk_account_basis","account_equity","account_balance","risk_amount_account_currency","entry_price","sl_price","tp_price","sl_distance_price","loss_per_1_lot_at_sl","raw_risk_volume_lots","normalized_risk_volume_lots","volume_min","volume_max","volume_step","effective_risk_amount","effective_risk_percent","expected_tp_amount","risk_reward_ratio","sizing_status","sizing_block_reason","sizing_digest");
}

void WritePositionSizingLog(const PositionSizingAudit &audit)
{
   UpdateSizingFinalSummaryCounters(audit);
   bool write_header = false;
   const int handle = OpenLogForAppend(POSITION_SIZING_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WritePositionSizingHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),audit.attempt_id,audit.signal_id,CANDIDATE_ID,FormatTimeServer(audit.bar_time),audit.sizing_phase,audit.sizing_mode,FormatNumber(audit.fixed_volume_lots),FormatNumber(audit.risk_percent_per_trade),FormatNumber(audit.max_risk_percent_per_trade),audit.risk_account_basis,FormatNumber(audit.account_equity),FormatNumber(audit.account_balance),FormatNumber(audit.risk_amount_account_currency),FormatNumber(audit.entry_price),FormatNumber(audit.sl_price),FormatNumber(audit.tp_price),FormatNumber(audit.sl_distance_price),FormatNumber(audit.loss_per_1_lot_at_sl),FormatNumber(audit.raw_risk_volume_lots),FormatNumber(audit.normalized_risk_volume_lots),FormatNumber(audit.volume_min),FormatNumber(audit.volume_max),FormatNumber(audit.volume_step),FormatNumber(audit.effective_risk_amount),FormatNumber(audit.effective_risk_percent),FormatNumber(audit.expected_tp_amount),FormatNumber(audit.risk_reward_ratio),audit.sizing_status,audit.sizing_block_reason,audit.sizing_digest);
   FileClose(handle);
}

void WriteStateTransitionHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","attempt_id","signal_id","candidate_id","bar_time","previous_state","next_state","reason","source_gate","order_send_called","execution_performed");
}

void WriteStateTransitionLogWithFlags(const string attempt_id,const string signal_id,const datetime bar_time,const string next_state,const string reason,const string source_gate,const bool order_send_called,const bool execution_performed)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(STATE_TRANSITION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteStateTransitionHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),attempt_id,signal_id,CANDIDATE_ID,FormatTimeServer(bar_time),g_current_state,next_state,reason,source_gate,BoolText(order_send_called),BoolText(execution_performed));
   FileClose(handle);
   g_current_state = next_state;
}

void WriteStateTransitionLog(const string attempt_id,const string signal_id,const datetime bar_time,const string next_state,const string reason,const string source_gate)
{
   WriteStateTransitionLogWithFlags(attempt_id,signal_id,bar_time,next_state,reason,source_gate,false,false);
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

string EnumNameOrUnknown(const string enum_name,const long raw_value)
{
   if(enum_name == "" || StringFind(enum_name, "::") >= 0)
      return "unknown_" + SafeLongToString(raw_value);
   return enum_name;
}

string TradeTransactionTypeName(const long raw_value)
{
   return EnumNameOrUnknown(EnumToString((ENUM_TRADE_TRANSACTION_TYPE)raw_value),raw_value);
}

string DealTypeName(const long raw_value)
{
   return EnumNameOrUnknown(EnumToString((ENUM_DEAL_TYPE)raw_value),raw_value);
}

string DealEntryName(const long raw_value)
{
   return EnumNameOrUnknown(EnumToString((ENUM_DEAL_ENTRY)raw_value),raw_value);
}

string DealReasonName(const long raw_value)
{
   return EnumNameOrUnknown(EnumToString((ENUM_DEAL_REASON)raw_value),raw_value);
}

bool TradeTransactionHasDealType(const ENUM_TRADE_TRANSACTION_TYPE transaction_type)
{
   return transaction_type == TRADE_TRANSACTION_DEAL_ADD ||
      transaction_type == TRADE_TRANSACTION_DEAL_UPDATE ||
      transaction_type == TRADE_TRANSACTION_DEAL_DELETE ||
      transaction_type == TRADE_TRANSACTION_POSITION;
}

string TradeTransactionFieldsStatus(const ENUM_TRADE_TRANSACTION_TYPE transaction_type)
{
   if(transaction_type == TRADE_TRANSACTION_DEAL_ADD ||
      transaction_type == TRADE_TRANSACTION_DEAL_UPDATE ||
      transaction_type == TRADE_TRANSACTION_DEAL_DELETE)
      return "deal_fields_present_in_mql_trade_transaction";
   if(transaction_type == TRADE_TRANSACTION_ORDER_ADD ||
      transaction_type == TRADE_TRANSACTION_ORDER_UPDATE ||
      transaction_type == TRADE_TRANSACTION_ORDER_DELETE ||
      transaction_type == TRADE_TRANSACTION_HISTORY_ADD ||
      transaction_type == TRADE_TRANSACTION_HISTORY_UPDATE ||
      transaction_type == TRADE_TRANSACTION_HISTORY_DELETE)
      return "order_fields_present_in_mql_trade_transaction";
   if(transaction_type == TRADE_TRANSACTION_POSITION)
      return "position_fields_present_in_mql_trade_transaction";
   if(transaction_type == TRADE_TRANSACTION_REQUEST)
      return "request_type_only_in_mql_trade_transaction";
   return "unrecognized_transaction_type_fields_conservative";
}

string TradeTransactionDataSource(const bool request_context_valid,const bool deal_history_available)
{
   string source = "MqlTradeTransaction";
   if(request_context_valid)
      source += "+MqlTradeRequest+MqlTradeResult";
   if(deal_history_available)
      source += "+DealHistory";
   return source;
}

bool IsPositionDealType(const long deal_type_raw)
{
   return deal_type_raw == (long)DEAL_TYPE_BUY || deal_type_raw == (long)DEAL_TYPE_SELL;
}

bool IsExitDealEntry(const long deal_entry_raw)
{
   return deal_entry_raw == (long)DEAL_ENTRY_OUT ||
      deal_entry_raw == (long)DEAL_ENTRY_OUT_BY;
}

void RecordHistoryGetterFailure(DealHistoryObservation &observation,const string field_name,const long error_code)
{
   if(observation.missing_history_fields != "")
      observation.missing_history_fields += "|";
   observation.missing_history_fields += field_name;
   if(observation.history_getter_error_code == 0)
      observation.history_getter_error_code = error_code;
   if(observation.history_getter_error_text == "")
      observation.history_getter_error_text = field_name + "_getter_failed";
}

bool ReadHistoryDealInteger(const ulong deal_ticket,const ENUM_DEAL_PROPERTY_INTEGER property_id,const string field_name,long &value,DealHistoryObservation &observation)
{
   ResetLastError();
   if(HistoryDealGetInteger(deal_ticket,property_id,value))
      return true;
   RecordHistoryGetterFailure(observation,field_name,GetLastError());
   return false;
}

bool ReadHistoryDealDouble(const ulong deal_ticket,const ENUM_DEAL_PROPERTY_DOUBLE property_id,const string field_name,double &value,DealHistoryObservation &observation)
{
   ResetLastError();
   if(HistoryDealGetDouble(deal_ticket,property_id,value))
      return true;
   RecordHistoryGetterFailure(observation,field_name,GetLastError());
   return false;
}

bool ReadHistoryDealString(const ulong deal_ticket,const ENUM_DEAL_PROPERTY_STRING property_id,const string field_name,string &value,DealHistoryObservation &observation)
{
   ResetLastError();
   if(HistoryDealGetString(deal_ticket,property_id,value))
      return true;
   RecordHistoryGetterFailure(observation,field_name,GetLastError());
   return false;
}

string ClassifyDealHistoryObservation(const DealHistoryObservation &observation)
{
   if(!observation.history_lookup_succeeded)
      return "history_lookup_unavailable";
   if(!observation.classification_core_getters_valid)
      return "history_data_incomplete";
   if(!observation.deal_type_recognized)
      return "unknown_deal_type";
   if(!IsPositionDealType(observation.deal_type_raw))
      return "non_position_deal";
   if(observation.deal_entry_raw == (long)DEAL_ENTRY_IN)
      return "entry_deal";
   if(observation.deal_entry_raw == (long)DEAL_ENTRY_INOUT)
      return "reversal_deal";
   if(IsExitDealEntry(observation.deal_entry_raw))
   {
      if(observation.deal_reason_raw == (long)DEAL_REASON_SL)
         return "broker_stop_loss_exit";
      if(observation.deal_reason_raw == (long)DEAL_REASON_TP)
         return "broker_take_profit_exit";
      if(observation.deal_reason_raw == (long)DEAL_REASON_EXPERT ||
         observation.deal_reason_raw == (long)DEAL_REASON_CLIENT ||
         observation.deal_reason_raw == (long)DEAL_REASON_MOBILE ||
         observation.deal_reason_raw == (long)DEAL_REASON_WEB)
         return "ea_or_manual_exit";
      return "external_or_unknown_exit";
   }
   return "external_or_unknown_exit";
}

void InitializeDealHistoryObservation(const MqlTradeTransaction &trans,DealHistoryObservation &observation)
{
   observation.is_deal_add = trans.type == TRADE_TRANSACTION_DEAL_ADD;
   observation.history_lookup_succeeded = false;
   observation.transaction_position_ticket = trans.position;
   observation.deal_ticket = 0;
   observation.order_ticket = 0;
   observation.deal_position_id = 0;
   observation.symbol = "";
   observation.magic = 0;
   observation.deal_time = 0;
   observation.deal_time_msc = 0;
   observation.deal_type_raw = -1;
   observation.deal_type_name = "";
   observation.deal_entry_raw = -1;
   observation.deal_entry_name = "";
   observation.deal_reason_raw = -1;
   observation.deal_reason_name = "";
   observation.deal_price = 0.0;
   observation.deal_volume = 0.0;
   observation.deal_profit = 0.0;
   observation.deal_commission = 0.0;
   observation.deal_swap = 0.0;
   observation.deal_fee = 0.0;
   observation.deal_comment = "";
   observation.deal_external_id = "";
   observation.deal_core_fields_source = observation.is_deal_add ? "deal_history_unavailable" : "";
   observation.history_lookup_status = observation.is_deal_add ? "unavailable_at_callback" : "not_applicable_transaction_type";
   observation.history_lookup_error_code = 0;
   observation.history_lookup_error_text = "";
   observation.history_getter_status = observation.is_deal_add ? "not_attempted" : "not_applicable_transaction_type";
   observation.history_getter_error_code = 0;
   observation.history_getter_error_text = "";
   observation.missing_history_fields = "";
   observation.deal_ticket_valid = false;
   observation.order_ticket_valid = false;
   observation.deal_position_id_valid = false;
   observation.symbol_valid = false;
   observation.magic_valid = false;
   observation.deal_time_valid = false;
   observation.deal_time_msc_valid = false;
   observation.deal_type_valid = false;
   observation.deal_entry_valid = false;
   observation.deal_reason_valid = false;
   observation.deal_price_valid = false;
   observation.deal_volume_valid = false;
   observation.deal_profit_valid = false;
   observation.deal_commission_valid = false;
   observation.deal_swap_valid = false;
   observation.deal_fee_valid = false;
   observation.deal_comment_valid = false;
   observation.deal_external_id_valid = false;
   observation.classification_core_getters_valid = false;
   observation.core_getters_success = false;
   observation.economic_getters_complete = false;
   observation.text_getters_complete = false;
   observation.deal_type_recognized = false;
   observation.deal_event_classification = observation.is_deal_add ? "history_lookup_unavailable" : "not_applicable_non_deal_transaction";
}

void BuildDealHistoryObservation(const MqlTradeTransaction &trans,DealHistoryObservation &observation)
{
   InitializeDealHistoryObservation(trans,observation);
   if(!observation.is_deal_add)
      return;

   g_deal_add_observed_count++;
   if(trans.deal == 0)
   {
      observation.history_lookup_error_text = "trans_deal_ticket_missing";
      g_deal_history_lookup_unavailable_count++;
      return;
   }

   ResetLastError();
   if(!HistoryDealSelect(trans.deal))
   {
      observation.history_lookup_error_code = GetLastError();
      observation.history_lookup_error_text = "HistoryDealSelect_failed_at_callback";
      g_deal_history_lookup_unavailable_count++;
      return;
   }

   observation.history_lookup_succeeded = true;
   observation.history_lookup_status = "history_select_success";
   observation.history_lookup_error_code = 0;
   observation.history_lookup_error_text = "";
   long history_deal_ticket = 0;
   long history_order_ticket = 0;
   observation.deal_ticket_valid = ReadHistoryDealInteger(trans.deal,DEAL_TICKET,"DEAL_TICKET",history_deal_ticket,observation);
   if(observation.deal_ticket_valid)
      observation.deal_ticket = (ulong)history_deal_ticket;
   observation.order_ticket_valid = ReadHistoryDealInteger(trans.deal,DEAL_ORDER,"DEAL_ORDER",history_order_ticket,observation);
   if(observation.order_ticket_valid)
      observation.order_ticket = (ulong)history_order_ticket;
   observation.deal_position_id_valid = ReadHistoryDealInteger(trans.deal,DEAL_POSITION_ID,"DEAL_POSITION_ID",observation.deal_position_id,observation);
   observation.symbol_valid = ReadHistoryDealString(trans.deal,DEAL_SYMBOL,"DEAL_SYMBOL",observation.symbol,observation);
   observation.magic_valid = ReadHistoryDealInteger(trans.deal,DEAL_MAGIC,"DEAL_MAGIC",observation.magic,observation);
   observation.deal_time_valid = ReadHistoryDealInteger(trans.deal,DEAL_TIME,"DEAL_TIME",observation.deal_time,observation);
   observation.deal_time_msc_valid = ReadHistoryDealInteger(trans.deal,DEAL_TIME_MSC,"DEAL_TIME_MSC",observation.deal_time_msc,observation);
   observation.deal_type_valid = ReadHistoryDealInteger(trans.deal,DEAL_TYPE,"DEAL_TYPE",observation.deal_type_raw,observation);
   if(observation.deal_type_valid)
   {
      observation.deal_type_name = DealTypeName(observation.deal_type_raw);
      observation.deal_type_recognized = StringFind(observation.deal_type_name,"unknown_") != 0;
   }
   observation.deal_entry_valid = ReadHistoryDealInteger(trans.deal,DEAL_ENTRY,"DEAL_ENTRY",observation.deal_entry_raw,observation);
   if(observation.deal_entry_valid)
      observation.deal_entry_name = DealEntryName(observation.deal_entry_raw);
   observation.deal_reason_valid = ReadHistoryDealInteger(trans.deal,DEAL_REASON,"DEAL_REASON",observation.deal_reason_raw,observation);
   if(observation.deal_reason_valid)
      observation.deal_reason_name = DealReasonName(observation.deal_reason_raw);
   observation.deal_price_valid = ReadHistoryDealDouble(trans.deal,DEAL_PRICE,"DEAL_PRICE",observation.deal_price,observation);
   observation.deal_volume_valid = ReadHistoryDealDouble(trans.deal,DEAL_VOLUME,"DEAL_VOLUME",observation.deal_volume,observation);
   observation.deal_profit_valid = ReadHistoryDealDouble(trans.deal,DEAL_PROFIT,"DEAL_PROFIT",observation.deal_profit,observation);
   observation.deal_commission_valid = ReadHistoryDealDouble(trans.deal,DEAL_COMMISSION,"DEAL_COMMISSION",observation.deal_commission,observation);
   observation.deal_swap_valid = ReadHistoryDealDouble(trans.deal,DEAL_SWAP,"DEAL_SWAP",observation.deal_swap,observation);
   observation.deal_fee_valid = ReadHistoryDealDouble(trans.deal,DEAL_FEE,"DEAL_FEE",observation.deal_fee,observation);
   observation.deal_comment_valid = ReadHistoryDealString(trans.deal,DEAL_COMMENT,"DEAL_COMMENT",observation.deal_comment,observation);
   observation.deal_external_id_valid = ReadHistoryDealString(trans.deal,DEAL_EXTERNAL_ID,"DEAL_EXTERNAL_ID",observation.deal_external_id,observation);

   observation.classification_core_getters_valid = observation.deal_type_valid &&
      observation.deal_entry_valid && observation.deal_reason_valid;
   observation.core_getters_success = observation.classification_core_getters_valid &&
      observation.deal_ticket_valid && observation.order_ticket_valid &&
      observation.deal_position_id_valid && observation.symbol_valid &&
      observation.magic_valid && observation.deal_time_valid &&
      observation.deal_time_msc_valid;
   observation.economic_getters_complete = observation.deal_price_valid &&
      observation.deal_volume_valid && observation.deal_profit_valid &&
      observation.deal_commission_valid && observation.deal_swap_valid &&
      observation.deal_fee_valid;
   observation.text_getters_complete = observation.deal_comment_valid &&
      observation.deal_external_id_valid;
   observation.history_getter_status =
      (observation.core_getters_success ? "core_getters_success" : "core_getters_incomplete") + "|" +
      (observation.economic_getters_complete ? "economic_getters_complete" : "economic_getters_incomplete") + "|" +
      (observation.text_getters_complete ? "text_getters_complete" : "text_getters_incomplete");
   if(!observation.core_getters_success || !observation.economic_getters_complete || !observation.text_getters_complete)
      observation.history_getter_status += "|partial_getter_failure";
   observation.deal_core_fields_source =
      observation.core_getters_success ? "deal_history_complete" : "deal_history_partial";
   observation.deal_event_classification = ClassifyDealHistoryObservation(observation);
   g_deal_history_lookup_success_count++;

   if(observation.classification_core_getters_valid &&
      observation.deal_type_recognized &&
      IsPositionDealType(observation.deal_type_raw) &&
      IsExitDealEntry(observation.deal_entry_raw))
   {
      if(observation.deal_event_classification == "broker_stop_loss_exit")
         g_stop_loss_exit_observed_count++;
      else if(observation.deal_event_classification == "broker_take_profit_exit")
         g_take_profit_exit_observed_count++;
      else
         g_other_exit_observed_count++;
   }
}

string TradeTransactionObservationKey(const MqlTradeTransaction &trans,const DealHistoryObservation &observation)
{
   const string canonical = "session_instance_id=" + g_session_instance_id +
      "|transaction_type=" + IntegerToString((int)trans.type) +
      "|deal_ticket=" + SafeLongToString((long)trans.deal) +
      "|order_ticket=" + SafeLongToString((long)trans.order) +
      "|deal_time_msc=" + (observation.deal_time_msc_valid ? SafeLongToString(observation.deal_time_msc) : "unavailable");
   return StableId("trade_event",canonical);
}

void WriteTradeTransactionsHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","attempt_id","signal_id","transaction_type","order","deal","position","symbol","magic_number","price","volume","reason","note","request_action","result_retcode","transaction_identity_status","session_instance_id","transaction_type_name","transaction_data_source","transaction_fields_status","trans_deal_type_raw","trans_deal_type_name","trans_price_sl","trans_price_tp","trans_position_by","deal_ticket","order_ticket","transaction_position_ticket","deal_symbol","deal_magic","deal_time","deal_time_msc","deal_type_raw","deal_type_name","deal_entry_raw","deal_entry_name","deal_reason_raw","deal_reason_name","deal_price","deal_volume","deal_profit","deal_commission","deal_swap","deal_fee","deal_comment","deal_external_id","deal_core_fields_source","history_lookup_status","history_lookup_error_code","history_lookup_error_text","deal_event_classification","observational_event_key","deal_position_id","history_getter_status","history_getter_error_code","history_getter_error_text","missing_history_fields","request_context_status","request_symbol","request_magic","result_comment");
}

bool TicketMatchesConfirmedIdentity(const ulong observed_ticket,const ulong confirmed_ticket)
{
   return observed_ticket != 0 && confirmed_ticket != 0 && observed_ticket == confirmed_ticket;
}

void ResolveTradeTransactionIdentity(const MqlTradeTransaction &trans,string &signal_id,string &attempt_id,string &transaction_identity_status)
{
   signal_id = "signal_id_unresolved";
   attempt_id = "attempt_id_unresolved";
   transaction_identity_status = "unresolved_after_restart_or_external_event";

   const bool has_reference = trans.position != 0 || trans.order != 0 || trans.deal != 0;
   if(!has_reference)
   {
      transaction_identity_status = "no_position_reference";
      return;
   }

   const bool matched_position = TicketMatchesConfirmedIdentity(trans.position,g_confirmed_position_ticket);
   const bool matched_order = TicketMatchesConfirmedIdentity(trans.order,g_confirmed_order_ticket);
   const bool matched_deal = TicketMatchesConfirmedIdentity(trans.deal,g_confirmed_deal_ticket);
   if((matched_position || matched_order || matched_deal) && g_confirmed_entry_signal_id != "" && g_confirmed_entry_attempt_id != "")
   {
      signal_id = g_confirmed_entry_signal_id;
      attempt_id = g_confirmed_entry_attempt_id;
      transaction_identity_status = "matched_confirmed_entry";
   }
}

void WriteTradeTransactionLog(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result)
{
   DealHistoryObservation deal_observation;
   BuildDealHistoryObservation(trans,deal_observation);
   bool write_header = false;
   const int handle = OpenLogForAppend(TRADE_TRANSACTIONS_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteTradeTransactionsHeader(handle);
   const bool request_context_valid = trans.type == TRADE_TRANSACTION_REQUEST;
   const string request_context_status = request_context_valid ? "valid_trade_transaction_request" : "not_applicable";
   const string tx_symbol = trans.symbol;
   const string tx_magic = request_context_valid ? SafeLongToString((long)request.magic) : "";
   const string request_symbol = request_context_valid ? request.symbol : "";
   const string request_magic = request_context_valid ? SafeLongToString((long)request.magic) : "";
   const string request_action = request_context_valid ? IntegerToString((int)request.action) : "";
   const string result_retcode = request_context_valid ? IntegerToString((int)result.retcode) : "";
   const string result_comment = request_context_valid ? result.comment : "";
   const string transaction_data_source = TradeTransactionDataSource(
      request_context_valid,
      deal_observation.history_lookup_succeeded);
   string tx_signal_id = "";
   string tx_attempt_id = "";
   string transaction_identity_status = "";
   ResolveTradeTransactionIdentity(trans,tx_signal_id,tx_attempt_id,transaction_identity_status);
   const bool trans_deal_type_available = TradeTransactionHasDealType(trans.type);
   const string observational_event_key = TradeTransactionObservationKey(trans,deal_observation);
   FileWrite(handle,
      g_run_id,
      FormatTimeServer(TimeCurrent()),
      tx_attempt_id,
      tx_signal_id,
      IntegerToString((int)trans.type),
      SafeLongToString((long)trans.order),
      SafeLongToString((long)trans.deal),
      SafeLongToString((long)trans.position),
      CsvEscape(tx_symbol),
      tx_magic,
      FormatNumber(trans.price),
      FormatNumber(trans.volume),
      "observed_external_or_manual_event",
      "passive_log_only",
      request_action,
      result_retcode,
      transaction_identity_status,
      g_session_instance_id,
      TradeTransactionTypeName((long)trans.type),
      transaction_data_source,
      TradeTransactionFieldsStatus(trans.type),
      trans_deal_type_available ? SafeLongToString((long)trans.deal_type) : "",
      trans_deal_type_available ? DealTypeName((long)trans.deal_type) : "",
      FormatNumber(trans.price_sl),
      FormatNumber(trans.price_tp),
      SafeLongToString((long)trans.position_by),
      deal_observation.deal_ticket_valid ? SafeLongToString((long)deal_observation.deal_ticket) : "",
      deal_observation.order_ticket_valid ? SafeLongToString((long)deal_observation.order_ticket) : "",
      SafeLongToString((long)deal_observation.transaction_position_ticket),
      deal_observation.symbol_valid ? CsvEscape(deal_observation.symbol) : "",
      deal_observation.magic_valid ? SafeLongToString(deal_observation.magic) : "",
      deal_observation.deal_time_valid ? FormatTimeServer((datetime)deal_observation.deal_time) : "",
      deal_observation.deal_time_msc_valid ? SafeLongToString(deal_observation.deal_time_msc) : "",
      deal_observation.deal_type_valid ? SafeLongToString(deal_observation.deal_type_raw) : "",
      deal_observation.deal_type_valid ? deal_observation.deal_type_name : "",
      deal_observation.deal_entry_valid ? SafeLongToString(deal_observation.deal_entry_raw) : "",
      deal_observation.deal_entry_valid ? deal_observation.deal_entry_name : "",
      deal_observation.deal_reason_valid ? SafeLongToString(deal_observation.deal_reason_raw) : "",
      deal_observation.deal_reason_valid ? deal_observation.deal_reason_name : "",
      deal_observation.deal_price_valid ? FormatNumber(deal_observation.deal_price) : "",
      deal_observation.deal_volume_valid ? FormatNumber(deal_observation.deal_volume) : "",
      deal_observation.deal_profit_valid ? FormatNumber(deal_observation.deal_profit) : "",
      deal_observation.deal_commission_valid ? FormatNumber(deal_observation.deal_commission) : "",
      deal_observation.deal_swap_valid ? FormatNumber(deal_observation.deal_swap) : "",
      deal_observation.deal_fee_valid ? FormatNumber(deal_observation.deal_fee) : "",
      deal_observation.deal_comment_valid ? CsvEscape(deal_observation.deal_comment) : "",
      deal_observation.deal_external_id_valid ? CsvEscape(deal_observation.deal_external_id) : "",
      deal_observation.deal_core_fields_source,
      deal_observation.history_lookup_status,
      deal_observation.is_deal_add ? SafeLongToString(deal_observation.history_lookup_error_code) : "",
      CsvEscape(deal_observation.history_lookup_error_text),
      deal_observation.deal_event_classification,
      observational_event_key,
      deal_observation.deal_position_id_valid ? SafeLongToString(deal_observation.deal_position_id) : "",
      deal_observation.history_getter_status,
      deal_observation.history_lookup_succeeded ? SafeLongToString(deal_observation.history_getter_error_code) : "",
      CsvEscape(deal_observation.history_getter_error_text),
      CsvEscape(deal_observation.missing_history_fields),
      request_context_status,
      CsvEscape(request_symbol),
      request_magic,
      CsvEscape(result_comment));
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

BrokerSnapshot ReadBrokerSnapshot()
{
   BrokerSnapshot snapshot;
   snapshot.position_count = 0;
   snapshot.pending_order_count = 0;
   snapshot.first_position_ticket = 0;
   snapshot.first_pending_order_ticket = 0;
   for(int index = 0; index < PositionsTotal(); index++)
   {
      const ulong ticket = PositionGetTicket(index);
      if(ticket == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != REQUIRED_SYMBOL) continue;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;
      snapshot.position_count++;
      if(snapshot.first_position_ticket == 0) snapshot.first_position_ticket = ticket;
   }
   for(int index = 0; index < OrdersTotal(); index++)
   {
      const ulong ticket = OrderGetTicket(index);
      if(ticket == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != REQUIRED_SYMBOL) continue;
      if((long)OrderGetInteger(ORDER_MAGIC) != InpMagicNumber) continue;
      snapshot.pending_order_count++;
      if(snapshot.first_pending_order_ticket == 0) snapshot.first_pending_order_ticket = ticket;
   }
   snapshot.broker_state = (snapshot.position_count == 0 && snapshot.pending_order_count == 0) ? "flat_no_pending" : "position_or_pending_detected";
   return snapshot;
}
void WriteReconciliationLog(const BrokerSnapshot &snapshot)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(RECONCILIATION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteReconciliationHeader(handle);
   const string reconciliation_status = (snapshot.position_count == 0 && snapshot.pending_order_count == 0) ? "ok_flat" : "blocked_existing_broker_state";
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),CANDIDATE_ID,InpSymbol,SafeLongToString(InpMagicNumber),IntegerToString(snapshot.position_count),IntegerToString(snapshot.pending_order_count),snapshot.broker_state,reconciliation_status);
   FileClose(handle);
}

void WritePostSendReconciliationHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","attempt_id","signal_id","candidate_id","symbol","magic_number","position_count","pending_order_count","broker_state","observed_order_ticket","observed_deal_ticket","observed_position_ticket","order_send_called","execution_performed","order_send_result_category","post_send_reconciliation_status");
}

void WritePostSendReconciliationLog(const OrderSendAudit &audit,const BrokerSnapshot &snapshot)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(POST_SEND_RECONCILIATION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WritePostSendReconciliationHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),audit.attempt_id,audit.signal_id,CANDIDATE_ID,InpSymbol,SafeLongToString(InpMagicNumber),IntegerToString(snapshot.position_count),IntegerToString(snapshot.pending_order_count),snapshot.broker_state,audit.order_send_called ? SafeLongToString((long)audit.order_ticket) : "",audit.order_send_called ? SafeLongToString((long)audit.deal_ticket) : "",audit.position_ticket > 0 ? SafeLongToString((long)audit.position_ticket) : "",BoolText(audit.order_send_called),BoolText(audit.execution_confirmed),audit.order_send_result_category,audit.post_send_reconciliation_status);
   FileClose(handle);
}
bool IsDemoAccount() { return AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO; }
bool IsLiveAccount() { return AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_REAL; }
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
   for(double scaled = step; digits < 8 && MathAbs(scaled - MathRound(scaled)) > 0.000000001; scaled *= 10.0)
      digits++;
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

bool NormalizeVolumeFloorToStep(const double requested_volume,const double min_volume,const double max_volume,const double volume_step,double &normalized_volume)
{
   normalized_volume = 0.0;
   if(min_volume <= 0.0 || max_volume <= 0.0 || volume_step <= 0.0) return false;
   if(requested_volume < min_volume || requested_volume > max_volume) return false;
   const double steps = MathFloor((requested_volume - min_volume) / volume_step + 0.000000001);
   normalized_volume = min_volume + steps * volume_step;
   normalized_volume = NormalizeDouble(normalized_volume, VolumeDigitsForStep(volume_step));
   return normalized_volume >= min_volume && normalized_volume <= max_volume;
}

PositionSizingAudit EmptyPositionSizingAudit()
{
   PositionSizingAudit audit;
   audit.bar_time = 0;
   audit.attempt_id = "";
   audit.signal_id = "";
   audit.sizing_phase = "";
   audit.sizing_mode = InpUseRiskBasedSizing ? "risk_based" : "fixed";
   audit.fixed_volume_lots = InpVolumeLots;
   audit.risk_percent_per_trade = InpRiskPercentPerTrade;
   audit.max_risk_percent_per_trade = InpMaxRiskPercentPerTrade;
   audit.risk_account_basis = "ACCOUNT_EQUITY";
   audit.account_equity = 0.0;
   audit.account_balance = 0.0;
   audit.risk_amount_account_currency = 0.0;
   audit.entry_price = 0.0;
   audit.sl_price = 0.0;
   audit.tp_price = 0.0;
   audit.sl_distance_price = 0.0;
   audit.loss_per_1_lot_at_sl = 0.0;
   audit.raw_risk_volume_lots = 0.0;
   audit.normalized_risk_volume_lots = 0.0;
   audit.volume_min = 0.0;
   audit.volume_max = 0.0;
   audit.volume_step = 0.0;
   audit.effective_risk_amount = 0.0;
   audit.effective_risk_percent = 0.0;
   audit.expected_tp_amount = 0.0;
   audit.risk_reward_ratio = TP_ATR_MULTIPLIER / SL_ATR_MULTIPLIER;
   audit.sizing_status = "";
   audit.sizing_block_reason = "";
   audit.sizing_passed = false;
   audit.sizing_digest = "";
   return audit;
}

bool LoadVolumeSpec(PositionSizingAudit &audit)
{
   audit.volume_min = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN);
   audit.volume_max = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX);
   audit.volume_step = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   return audit.volume_min > 0.0 && audit.volume_max > 0.0 && audit.volume_step > 0.0;
}

bool LossPerOneLotAtSl(const string symbol,const double entry_price,const double sl_price,double &loss_per_1_lot)
{
   loss_per_1_lot = 0.0;
   double profit = 0.0;
   if(OrderCalcProfit(ORDER_TYPE_SELL, symbol, 1.0, entry_price, sl_price, profit) && MathAbs(profit) > 0.0)
   {
      loss_per_1_lot = MathAbs(profit);
      return true;
   }
   const double tick_size = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_value = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE_LOSS);
   if(tick_value <= 0.0) tick_value = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tick_size <= 0.0 || tick_value <= 0.0) return false;
   loss_per_1_lot = MathAbs(entry_price - sl_price) / tick_size * tick_value;
   return loss_per_1_lot > 0.0;
}

string PositionSizingCanonical(const PositionSizingAudit &audit)
{
   return "sizing_mode=" + audit.sizing_mode +
      "|fixed_volume_lots=" + FormatNumber(audit.fixed_volume_lots) +
      "|risk_percent_per_trade=" + FormatNumber(audit.risk_percent_per_trade) +
      "|max_risk_percent_per_trade=" + FormatNumber(audit.max_risk_percent_per_trade) +
      "|risk_account_basis=" + audit.risk_account_basis +
      "|account_equity=" + FormatNumber(audit.account_equity) +
      "|risk_amount_account_currency=" + FormatNumber(audit.risk_amount_account_currency) +
      "|entry_price=" + FormatNumber(audit.entry_price) +
      "|sl_price=" + FormatNumber(audit.sl_price) +
      "|tp_price=" + FormatNumber(audit.tp_price) +
      "|sl_distance_price=" + FormatNumber(audit.sl_distance_price) +
      "|loss_per_1_lot_at_sl=" + FormatNumber(audit.loss_per_1_lot_at_sl) +
      "|raw_risk_volume_lots=" + FormatNumber(audit.raw_risk_volume_lots) +
      "|normalized_risk_volume_lots=" + FormatNumber(audit.normalized_risk_volume_lots) +
      "|effective_risk_amount=" + FormatNumber(audit.effective_risk_amount) +
      "|effective_risk_percent=" + FormatNumber(audit.effective_risk_percent) +
      "|expected_tp_amount=" + FormatNumber(audit.expected_tp_amount) +
      "|risk_reward_ratio=" + FormatNumber(audit.risk_reward_ratio) +
      "|sizing_status=" + audit.sizing_status +
      "|sizing_block_reason=" + audit.sizing_block_reason;
}

void FinalizePositionSizingDigest(PositionSizingAudit &audit)
{
   audit.sizing_digest = NonCryptoDigest(PositionSizingCanonical(audit));
}

bool ComputePositionSizing(const SignalSnapshot &snapshot,const string attempt_id,const string signal_id,const string sizing_phase,PositionSizingAudit &audit)
{
   audit = EmptyPositionSizingAudit();
   audit.bar_time = snapshot.bar_time;
   audit.attempt_id = attempt_id;
   audit.signal_id = signal_id;
   audit.sizing_phase = sizing_phase;
   audit.account_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   audit.account_balance = AccountInfoDouble(ACCOUNT_BALANCE);
   audit.risk_amount_account_currency = audit.account_equity * InpRiskPercentPerTrade / 100.0;

   MqlTick tick;
   if(!SymbolInfoTick(InpSymbol, tick) || tick.bid <= 0.0)
   {
      audit.sizing_status = "sizing_sl_distance_invalid";
      audit.sizing_block_reason = "tick_unavailable";
      FinalizePositionSizingDigest(audit);
      return false;
   }
   audit.entry_price = NormalizeSymbolPrice(tick.bid);
   audit.sl_price = NormalizeSymbolPrice(snapshot.sl_price_preview);
   audit.tp_price = NormalizeSymbolPrice(snapshot.tp_price_preview);
   audit.sl_distance_price = MathAbs(audit.entry_price - audit.sl_price);

   if(!LoadVolumeSpec(audit))
   {
      audit.sizing_status = "sizing_volume_below_min_lot";
      audit.sizing_block_reason = "volume_spec_unavailable";
      FinalizePositionSizingDigest(audit);
      return false;
   }
   if(audit.entry_price <= 0.0 || audit.sl_price <= 0.0 || audit.tp_price <= 0.0 || audit.sl_distance_price <= 0.0)
   {
      audit.sizing_status = "sizing_sl_distance_invalid";
      audit.sizing_block_reason = "sizing_sl_distance_invalid";
      FinalizePositionSizingDigest(audit);
      return false;
   }
   if(!InpUseRiskBasedSizing)
   {
      audit.raw_risk_volume_lots = InpVolumeLots;
      if(InpVolumeLots < audit.volume_min)
      {
         audit.sizing_status = "sizing_volume_below_min_lot";
         audit.sizing_block_reason = "sizing_volume_below_min_lot";
         FinalizePositionSizingDigest(audit);
         return false;
      }
      if(InpVolumeLots > audit.volume_max)
      {
         audit.sizing_status = "sizing_volume_above_max_lot";
         audit.sizing_block_reason = "sizing_volume_above_max_lot";
         FinalizePositionSizingDigest(audit);
         return false;
      }
      if(!NormalizeVolumeFloorToStep(InpVolumeLots, audit.volume_min, audit.volume_max, audit.volume_step, audit.normalized_risk_volume_lots))
      {
         audit.sizing_status = "sizing_volume_below_min_lot";
         audit.sizing_block_reason = "volume_invalid";
         FinalizePositionSizingDigest(audit);
         return false;
      }
      if(LossPerOneLotAtSl(InpSymbol, audit.entry_price, audit.sl_price, audit.loss_per_1_lot_at_sl))
      {
         audit.effective_risk_amount = audit.loss_per_1_lot_at_sl * audit.normalized_risk_volume_lots;
         audit.effective_risk_percent = audit.account_equity > 0.0 ? audit.effective_risk_amount / audit.account_equity * 100.0 : 0.0;
         double tp_profit = 0.0;
         audit.expected_tp_amount = OrderCalcProfit(ORDER_TYPE_SELL, InpSymbol, audit.normalized_risk_volume_lots, audit.entry_price, audit.tp_price, tp_profit) ? MathAbs(tp_profit) : audit.effective_risk_amount * audit.risk_reward_ratio;
      }
      audit.sizing_status = "sizing_fixed_volume_used";
      audit.sizing_block_reason = "";
      audit.sizing_passed = true;
      FinalizePositionSizingDigest(audit);
      return true;
   }

   if(MathAbs(InpMaxRiskPercentPerTrade - 0.5) > 0.000000001 || InpRiskPercentPerTrade <= 0.0 || InpRiskPercentPerTrade > InpMaxRiskPercentPerTrade || InpMaxRiskPercentPerTrade <= 0.0)
   {
      audit.sizing_status = "sizing_risk_percent_invalid";
      audit.sizing_block_reason = "sizing_risk_percent_invalid";
      FinalizePositionSizingDigest(audit);
      return false;
   }

   if(!LossPerOneLotAtSl(InpSymbol, audit.entry_price, audit.sl_price, audit.loss_per_1_lot_at_sl))
   {
      audit.sizing_status = "sizing_tick_value_unavailable";
      audit.sizing_block_reason = "sizing_tick_value_unavailable";
      FinalizePositionSizingDigest(audit);
      return false;
   }

   if(audit.account_equity <= 0.0 || audit.risk_amount_account_currency <= 0.0)
   {
      audit.sizing_status = "sizing_margin_check_failed";
      audit.sizing_block_reason = "account_equity_unavailable";
      FinalizePositionSizingDigest(audit);
      return false;
   }

   audit.raw_risk_volume_lots = audit.risk_amount_account_currency / audit.loss_per_1_lot_at_sl;
   if(audit.raw_risk_volume_lots < audit.volume_min)
   {
      audit.sizing_status = "sizing_volume_below_min_lot";
      audit.sizing_block_reason = "sizing_volume_below_min_lot";
      FinalizePositionSizingDigest(audit);
      return false;
   }
   if(audit.raw_risk_volume_lots > audit.volume_max)
   {
      audit.sizing_status = "sizing_volume_above_max_lot";
      audit.sizing_block_reason = "sizing_volume_above_max_lot";
      FinalizePositionSizingDigest(audit);
      return false;
   }
   if(!NormalizeVolumeFloorToStep(audit.raw_risk_volume_lots, audit.volume_min, audit.volume_max, audit.volume_step, audit.normalized_risk_volume_lots))
   {
      audit.sizing_status = "sizing_volume_below_min_lot";
      audit.sizing_block_reason = "sizing_volume_below_min_lot";
      FinalizePositionSizingDigest(audit);
      return false;
   }

   audit.effective_risk_amount = audit.loss_per_1_lot_at_sl * audit.normalized_risk_volume_lots;
   audit.effective_risk_percent = audit.effective_risk_amount / audit.account_equity * 100.0;
   if(audit.effective_risk_percent > InpMaxRiskPercentPerTrade + 0.000000001)
   {
      audit.sizing_status = "sizing_effective_risk_exceeds_policy";
      audit.sizing_block_reason = "sizing_effective_risk_exceeds_policy";
      FinalizePositionSizingDigest(audit);
      return false;
   }

   double tp_profit = 0.0;
   audit.expected_tp_amount = OrderCalcProfit(ORDER_TYPE_SELL, InpSymbol, audit.normalized_risk_volume_lots, audit.entry_price, audit.tp_price, tp_profit) ? MathAbs(tp_profit) : audit.effective_risk_amount * audit.risk_reward_ratio;
   audit.sizing_status = "sizing_risk_based_passed";
   audit.sizing_block_reason = "";
   audit.sizing_passed = true;
   FinalizePositionSizingDigest(audit);
   return true;
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

string CanonicalRequestString(const MqlTradeRequest &request,const PositionSizingAudit &sizing_audit)
{
   return "candidate_id=" + CANDIDATE_ID +
      "|symbol=" + request.symbol +
      "|side=" + SIDE_SELL +
      "|volume=" + FormatNumber(request.volume) +
      "|price=" + FormatNumber(request.price) +
      "|sl=" + FormatNumber(request.sl) +
      "|tp=" + FormatNumber(request.tp) +
      "|deviation=" + IntegerToString((int)request.deviation) +
      "|magic=" + SafeLongToString((long)request.magic) +
      "|comment=" + request.comment +
      "|type_time=" + IntegerToString((int)request.type_time) +
      "|type_filling=" + IntegerToString((int)request.type_filling) +
      "|sizing_mode=" + sizing_audit.sizing_mode +
      "|risk_percent_per_trade=" + FormatNumber(sizing_audit.risk_percent_per_trade) +
      "|risk_account_basis=" + sizing_audit.risk_account_basis +
      "|account_equity=" + FormatNumber(sizing_audit.account_equity) +
      "|risk_amount=" + FormatNumber(sizing_audit.risk_amount_account_currency) +
      "|sl_distance=" + FormatNumber(sizing_audit.sl_distance_price) +
      "|loss_per_1_lot_at_sl=" + FormatNumber(sizing_audit.loss_per_1_lot_at_sl) +
      "|raw_risk_volume_lots=" + FormatNumber(sizing_audit.raw_risk_volume_lots) +
      "|normalized_risk_volume_lots=" + FormatNumber(sizing_audit.normalized_risk_volume_lots) +
      "|effective_risk_amount=" + FormatNumber(sizing_audit.effective_risk_amount) +
      "|effective_risk_percent=" + FormatNumber(sizing_audit.effective_risk_percent) +
      "|sizing_digest=" + sizing_audit.sizing_digest;
}

void FillRequestAudit(const MqlTradeRequest &request,const PositionSizingAudit &sizing_audit,RequestAudit &audit)
{
   audit.volume = request.volume;
   audit.price = request.price;
   audit.sl = request.sl;
   audit.tp = request.tp;
   audit.comment = request.comment;
   audit.sizing = sizing_audit;
   audit.canonical_request = CanonicalRequestString(request,sizing_audit);
   audit.request_digest = NonCryptoDigest(audit.canonical_request);
}

void AttachSizingAuditToRequestAudit(const PositionSizingAudit &sizing_audit,RequestAudit &audit)
{
   audit.sizing = sizing_audit;
}

bool BuildBrokerSafeCheckRequest(const SignalSnapshot &snapshot,const PositionSizingAudit &sizing_audit,MqlTradeRequest &request,RequestAudit &audit,string &block_reason)
{
   if(!sizing_audit.sizing_passed)
   {
      block_reason = sizing_audit.sizing_block_reason == "" ? "sizing_unavailable" : sizing_audit.sizing_block_reason;
      return false;
   }
   const double price = sizing_audit.entry_price;
   const double sl = sizing_audit.sl_price;
   const double tp = sizing_audit.tp_price;
   if(!SlTpValidForSell(price, sl, tp))
   {
      block_reason = "sl_tp_invalid";
      return false;
   }
   ZeroMemory(request);
   request.action = TRADE_ACTION_DEAL;
   request.symbol = InpSymbol;
   request.volume = sizing_audit.normalized_risk_volume_lots;
   request.type = ORDER_TYPE_SELL;
   request.price = price;
   request.sl = sl;
   request.tp = tp;
   request.deviation = ORDER_CHECK_DEVIATION_POINTS;
   request.magic = (ulong)InpMagicNumber;
   request.comment = PREFLIGHT_COMMENT;
   request.type_time = ORDER_TIME_GTC;
   request.type_filling = PreferredFillingMode();
   FillRequestAudit(request,sizing_audit,audit);
   return true;
}

RequestAudit EmptyRequestAudit()
{
   RequestAudit audit;
   audit.volume = 0.0;
   audit.price = 0.0;
   audit.sl = 0.0;
   audit.tp = 0.0;
   audit.comment = PREFLIGHT_COMMENT;
   audit.canonical_request = "";
   audit.request_digest = "";
   audit.sizing = EmptyPositionSizingAudit();
   return audit;
}

string RetcodeName(const uint retcode)
{
   switch(retcode)
   {
      case TRADE_RETCODE_REQUOTE: return "TRADE_RETCODE_REQUOTE";
      case TRADE_RETCODE_REJECT: return "TRADE_RETCODE_REJECT";
      case TRADE_RETCODE_CANCEL: return "TRADE_RETCODE_CANCEL";
      case TRADE_RETCODE_PLACED: return "TRADE_RETCODE_PLACED";
      case TRADE_RETCODE_DONE: return "TRADE_RETCODE_DONE";
      case TRADE_RETCODE_DONE_PARTIAL: return "TRADE_RETCODE_DONE_PARTIAL";
      case TRADE_RETCODE_ERROR: return "TRADE_RETCODE_ERROR";
      case TRADE_RETCODE_TIMEOUT: return "TRADE_RETCODE_TIMEOUT";
      case TRADE_RETCODE_INVALID: return "TRADE_RETCODE_INVALID";
      case TRADE_RETCODE_INVALID_VOLUME: return "TRADE_RETCODE_INVALID_VOLUME";
      case TRADE_RETCODE_INVALID_PRICE: return "TRADE_RETCODE_INVALID_PRICE";
      case TRADE_RETCODE_INVALID_STOPS: return "TRADE_RETCODE_INVALID_STOPS";
      case TRADE_RETCODE_TRADE_DISABLED: return "TRADE_RETCODE_TRADE_DISABLED";
      case TRADE_RETCODE_MARKET_CLOSED: return "TRADE_RETCODE_MARKET_CLOSED";
      case TRADE_RETCODE_NO_MONEY: return "TRADE_RETCODE_NO_MONEY";
      case TRADE_RETCODE_PRICE_CHANGED: return "TRADE_RETCODE_PRICE_CHANGED";
      case TRADE_RETCODE_PRICE_OFF: return "TRADE_RETCODE_PRICE_OFF";
      case TRADE_RETCODE_TOO_MANY_REQUESTS: return "TRADE_RETCODE_TOO_MANY_REQUESTS";
      case TRADE_RETCODE_SERVER_DISABLES_AT: return "TRADE_RETCODE_SERVER_DISABLES_AT";
      case TRADE_RETCODE_CLIENT_DISABLES_AT: return "TRADE_RETCODE_CLIENT_DISABLES_AT";
      case TRADE_RETCODE_LOCKED: return "TRADE_RETCODE_LOCKED";
      case TRADE_RETCODE_FROZEN: return "TRADE_RETCODE_FROZEN";
      case TRADE_RETCODE_CONNECTION: return "TRADE_RETCODE_CONNECTION";
      case TRADE_RETCODE_ONLY_REAL: return "TRADE_RETCODE_ONLY_REAL";
   }
   return "TRADE_RETCODE_UNKNOWN_" + IntegerToString((int)retcode);
}

string RetcodeResultCategory(const uint retcode)
{
   switch(retcode)
   {
      case TRADE_RETCODE_DONE:
      case TRADE_RETCODE_PLACED:
      case TRADE_RETCODE_DONE_PARTIAL:
         return "success_accepted";
      case TRADE_RETCODE_CLIENT_DISABLES_AT:
      case TRADE_RETCODE_SERVER_DISABLES_AT:
         return "client_autotrading_disabled";
      case TRADE_RETCODE_MARKET_CLOSED:
         return "market_closed";
      case TRADE_RETCODE_TRADE_DISABLED:
      case TRADE_RETCODE_ONLY_REAL:
         return "trade_disabled";
      case TRADE_RETCODE_INVALID_VOLUME:
         return "invalid_volume";
      case TRADE_RETCODE_INVALID_STOPS:
         return "invalid_stops";
      case TRADE_RETCODE_REQUOTE:
      case TRADE_RETCODE_PRICE_CHANGED:
      case TRADE_RETCODE_PRICE_OFF:
      case TRADE_RETCODE_INVALID_PRICE:
         return "price_changed_or_requote";
      case TRADE_RETCODE_NO_MONEY:
         return "no_money_or_margin";
      case TRADE_RETCODE_TIMEOUT:
      case TRADE_RETCODE_CONNECTION:
      case TRADE_RETCODE_TOO_MANY_REQUESTS:
      case TRADE_RETCODE_LOCKED:
      case TRADE_RETCODE_FROZEN:
         return "timeout_or_uncertain";
   }
   return "unknown_retcode";
}

bool BrokerTicketExpectedForCategory(const string category)
{
   return category == "success_accepted" || category == "timeout_or_uncertain" || category == "unknown_retcode";
}

bool RejectedCategory(const string category)
{
   return category == "client_autotrading_disabled" || category == "market_closed" || category == "trade_disabled" || category == "invalid_volume" || category == "invalid_stops" || category == "price_changed_or_requote" || category == "no_money_or_margin";
}

string ReconciliationStatusForSend(const string category,const bool execution_confirmed,const BrokerSnapshot &snapshot)
{
   if(execution_confirmed) return "position_open_confirmed_after_send";
   if(category == "success_accepted") return "success_retcode_without_position_hold";
   if(category == "timeout_or_uncertain" || category == "unknown_retcode") return snapshot.broker_state == "flat_no_pending" ? "uncertain_flat_snapshot_hold" : "uncertain_broker_state_hold";
   if(RejectedCategory(category) && snapshot.broker_state == "flat_no_pending") return "rejected_no_position_no_order";
   if(RejectedCategory(category)) return "rejected_but_broker_state_changed_hold";
   return "unknown_reconciliation_hold";
}

string FinalStateForSend(const string category,const bool execution_confirmed,const BrokerSnapshot &snapshot)
{
   if(execution_confirmed) return "send_accepted_position_open";
   if(RejectedCategory(category) && snapshot.broker_state == "flat_no_pending") return "send_rejected_no_position_no_order";
   return "send_uncertain_reconciliation_hold";
}

OrderSendAudit BuildOrderSendAudit(const datetime bar_time,const string attempt_id,const string signal_id,const RequestAudit &request_audit,const bool called,const int attempt_count,const MqlTradeResult &result,const BrokerSnapshot &post_snapshot)
{
   OrderSendAudit audit;
   audit.bar_time = bar_time;
   audit.attempt_id = attempt_id;
   audit.signal_id = signal_id;
   audit.volume = request_audit.volume;
   audit.price = request_audit.price;
   audit.sl = request_audit.sl;
   audit.tp = request_audit.tp;
   audit.comment = request_audit.comment;
   audit.request_digest = request_audit.request_digest;
   audit.order_check_digest = request_audit.request_digest;
   audit.order_send_called = called;
   audit.order_send_attempt_count = attempt_count;
   audit.order_send_retcode = called ? result.retcode : 0;
   audit.order_send_retcode_name = called ? RetcodeName(result.retcode) : "";
   audit.order_send_comment = called ? result.comment : "";
   audit.order_send_request_id = called ? result.request_id : 0;
   audit.order_ticket = called ? result.order : 0;
   audit.deal_ticket = called ? result.deal : 0;
   audit.position_ticket = post_snapshot.first_position_ticket;
   audit.order_send_result_category = called ? RetcodeResultCategory(result.retcode) : "not_called";
   audit.broker_ticket_expected = called && BrokerTicketExpectedForCategory(audit.order_send_result_category);
   audit.execution_confirmed = called && audit.order_send_result_category == "success_accepted" && post_snapshot.position_count > 0;
   audit.retry_performed = false;
   audit.automatic_retry_allowed = false;
   audit.post_send_reconciliation_status = called ? ReconciliationStatusForSend(audit.order_send_result_category,audit.execution_confirmed,post_snapshot) : "no_send_no_broker_mutation";
   audit.final_state_status = called ? FinalStateForSend(audit.order_send_result_category,audit.execution_confirmed,post_snapshot) : "send_preflight_blocked";
   audit.sizing = request_audit.sizing;
   return audit;
}

void UpdateRunFinalSummaryCounters(const OrderSendAudit &audit)
{
   if(!audit.order_send_called) return;
   g_any_order_send_called = true;
   g_total_order_send_attempt_count += audit.order_send_attempt_count;
   if(audit.execution_confirmed)
      g_execution_confirmed_count++;
   else if(audit.final_state_status == "send_rejected_no_position_no_order")
      g_rejected_count++;
   else if(audit.final_state_status == "send_uncertain_reconciliation_hold")
      g_uncertain_count++;
   g_retry_performed = g_retry_performed || audit.retry_performed;
   g_automatic_retry_allowed = g_automatic_retry_allowed || audit.automatic_retry_allowed;
}

void UpdateSizingFinalSummaryCounters(const PositionSizingAudit &audit)
{
   if(audit.sizing_mode == "fixed")
      g_sizing_mode_fixed_count++;
   else if(audit.sizing_mode == "risk_based")
      g_sizing_mode_risk_based_count++;

   if(audit.sizing_status == "sizing_risk_based_passed")
      g_sizing_risk_based_passed_count++;
   else if(audit.sizing_status == "sizing_fixed_volume_used")
      g_sizing_fixed_volume_used_count++;
   else if(audit.sizing_status == "sizing_risk_percent_invalid")
      g_sizing_risk_percent_invalid_count++;
   else if(audit.sizing_status == "sizing_volume_below_min_lot")
      g_sizing_volume_below_min_lot_count++;
   else if(audit.sizing_status == "sizing_volume_above_max_lot")
      g_sizing_volume_above_max_lot_count++;
   else if(audit.sizing_status == "sizing_effective_risk_exceeds_policy")
      g_sizing_effective_risk_exceeds_policy_count++;
   else if(audit.sizing_status == "sizing_tick_value_unavailable")
      g_sizing_tick_value_unavailable_count++;

   if(!audit.sizing_passed)
      g_sizing_blocked_count++;

   if(audit.effective_risk_percent > 0.0)
   {
      if(!g_sizing_effective_risk_seen || audit.effective_risk_percent < g_sizing_min_effective_risk_percent)
         g_sizing_min_effective_risk_percent = audit.effective_risk_percent;
      if(!g_sizing_effective_risk_seen || audit.effective_risk_percent > g_sizing_max_effective_risk_percent)
         g_sizing_max_effective_risk_percent = audit.effective_risk_percent;
      g_sizing_effective_risk_seen = true;
   }

   if(audit.normalized_risk_volume_lots > 0.0)
   {
      if(!g_sizing_volume_seen || audit.normalized_risk_volume_lots < g_sizing_min_volume_lots)
         g_sizing_min_volume_lots = audit.normalized_risk_volume_lots;
      if(!g_sizing_volume_seen || audit.normalized_risk_volume_lots > g_sizing_max_volume_lots)
         g_sizing_max_volume_lots = audit.normalized_risk_volume_lots;
      g_sizing_volume_seen = true;
   }
}

void UpdateLifecycleCloseFinalSummaryCounters(const IntegratedLifecycleSnapshot &snapshot,const IntegratedLifecycleCloseAudit &audit)
{
   if(audit.close_called)
   {
      g_lifecycle_close_called_count++;
      if(snapshot.exit_reason_preview == "time_exit_10_m15_bars")
         g_lifecycle_close_time_exit_count++;
      else if(snapshot.exit_reason_preview == "friday_forced_flat")
         g_lifecycle_close_friday_forced_flat_count++;
   }

   if(audit.lifecycle_close_result_status == "position_close_confirmed")
      g_lifecycle_close_confirmed_count++;
   else if(audit.lifecycle_close_result_status == "position_close_rejected_no_retry")
      g_lifecycle_close_rejected_count++;
   else if(audit.lifecycle_close_result_status == "position_close_uncertain_reconciliation_hold")
      g_lifecycle_close_uncertain_count++;
   else if(audit.lifecycle_close_result_status == "position_close_skipped_already_closed_by_broker")
      g_lifecycle_close_skipped_already_closed_count++;

   if(audit.lifecycle_close_result_status == "position_close_duplicate_send_blocked" || audit.close_preflight_status == "position_close_preflight_duplicate_blocked")
      g_lifecycle_close_duplicate_blocked_count++;

   if(audit.lifecycle_close_result_status == "position_identity_unresolved_manual_review_required")
      g_lifecycle_close_unresolved_identity_blocked_count++;

   if(audit.manual_intervention_required)
      g_manual_intervention_required_count++;

   g_retry_performed = g_retry_performed || audit.retry_performed;
   g_automatic_retry_allowed = g_automatic_retry_allowed || audit.automatic_retry_allowed;
}
datetime ConfirmedEntryBarTimeFromPositionTime(const datetime entry_time)
{
   if(entry_time <= 0) return 0;
   const int shift = iBarShift(InpSymbol, InpTimeframe, entry_time, false);
   if(shift < 0) return 0;
   return iTime(InpSymbol, InpTimeframe, shift);
}

bool ReadPositionEntryTimeByTicket(const ulong position_ticket, datetime &entry_time)
{
   entry_time = 0;
   if(position_ticket == 0) return false;
   for(int index = 0; index < PositionsTotal(); index++)
   {
      const ulong ticket = PositionGetTicket(index);
      if(ticket != position_ticket) continue;
      if(PositionGetString(POSITION_SYMBOL) != REQUIRED_SYMBOL) return false;
      if((long)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) return false;
      entry_time = (datetime)PositionGetInteger(POSITION_TIME);
      return entry_time > 0;
   }
   return false;
}

void StoreConfirmedPositionIdentity(const OrderSendAudit &audit)
{
   if(!audit.execution_confirmed || audit.position_ticket == 0) return;
   datetime entry_time = 0;
   if(!ReadPositionEntryTimeByTicket(audit.position_ticket, entry_time)) return;
   g_confirmed_position_ticket = audit.position_ticket;
   g_confirmed_entry_signal_id = audit.signal_id;
   g_confirmed_entry_attempt_id = audit.attempt_id;
   g_confirmed_entry_time = entry_time;
   g_confirmed_entry_bar_time = ConfirmedEntryBarTimeFromPositionTime(entry_time);
   g_confirmed_order_ticket = audit.order_ticket;
   g_confirmed_deal_ticket = audit.deal_ticket;
}
void EvaluateSendPreflight(const SignalSnapshot &snapshot,const string attempt_id,const string signal_id,const bool order_check_called,const bool order_check_passed,const RequestAudit &order_check_audit,const string upstream_block_reason)
{
   BrokerSnapshot fresh_snapshot = ReadBrokerSnapshot();
   PositionSizingAudit sizing_audit;
   const bool sizing_ok = ComputePositionSizing(snapshot, attempt_id, signal_id, "send_preflight", sizing_audit);
   WritePositionSizingLog(sizing_audit);

   MqlTradeRequest preflight_request;
   RequestAudit preflight_audit = EmptyRequestAudit();
   AttachSizingAuditToRequestAudit(sizing_audit, preflight_audit);
   string request_block_reason = "";
   const bool request_ok = sizing_ok && BuildBrokerSafeCheckRequest(snapshot, sizing_audit, preflight_request, preflight_audit, request_block_reason);

   SendPreflightAudit audit;
   audit.bar_time = snapshot.bar_time;
   audit.attempt_id = attempt_id;
   audit.signal_id = signal_id;
   audit.volume = request_ok ? preflight_audit.volume : (sizing_audit.normalized_risk_volume_lots > 0.0 ? sizing_audit.normalized_risk_volume_lots : order_check_audit.volume);
   audit.price = request_ok ? preflight_audit.price : (sizing_audit.entry_price > 0.0 ? sizing_audit.entry_price : order_check_audit.price);
   audit.sl = request_ok ? preflight_audit.sl : (sizing_audit.sl_price > 0.0 ? sizing_audit.sl_price : order_check_audit.sl);
   audit.tp = request_ok ? preflight_audit.tp : (sizing_audit.tp_price > 0.0 ? sizing_audit.tp_price : order_check_audit.tp);
   audit.comment = request_ok ? preflight_audit.comment : order_check_audit.comment;
   audit.request_digest = request_ok ? preflight_audit.request_digest : "";
   audit.order_check_digest = order_check_audit.request_digest;
   audit.sizing = sizing_audit;
   audit.order_check_called = order_check_called;
   audit.order_check_passed = order_check_passed;
   audit.send_preflight_enabled = InpEnableSendPreflight;
   audit.order_send_enabled = InpEnableOrderSend;
   audit.final_ack_valid = InpFinalSendAcknowledgment == FINAL_SEND_ACK_TEXT;
   audit.max_order_send_attempts = InpMaxOrderSendAttempts;
   audit.max_order_send_attempts_ok = InpMaxOrderSendAttempts == 1;
   audit.demo_account_ok = InpRequireDemoAccount && IsDemoAccount();
   audit.live_account_forbidden_ok = !InpAllowLiveAccount && !IsLiveAccount();
   audit.spread_ok = CurrentSpreadPoints() <= InpMaxSpreadPoints;
   audit.one_position_only_ok = fresh_snapshot.position_count == 0;
   audit.pending_order_ok = fresh_snapshot.pending_order_count == 0;
   audit.friday_entry_cutoff_ok = FridayEntryCutoffOk(TimeCurrent());
   audit.digest_unchanged = order_check_called && order_check_passed && request_ok && preflight_audit.request_digest == order_check_audit.request_digest;
   const bool signal_binding_ok = snapshot.bar_time == iTime(InpSymbol, InpTimeframe, 1);
   const bool terminal_trade_ok = TerminalTradeAllowed();
   const bool expert_trade_allowed_ok = ExpertTradeAllowed();
   const bool symbol_trade_mode_ok = SymbolTradeModeAllowsShort();
   audit.previous_send_attempt_exists = g_last_order_send_attempt_id == attempt_id;
   audit.order_send_called = false;
   audit.order_send_attempt_count = 0;
   audit.execution_performed = false;

   string block_reason = "";
   if(upstream_block_reason != "") block_reason = upstream_block_reason;
   else if(!order_check_called || !order_check_passed) block_reason = order_check_called ? "order_check_failed" : "order_check_required_before_send";
   else if(!InpEnableSendPreflight) block_reason = "send_preflight_disabled";
   else if(!InpEnableOrderSend) block_reason = "order_send_input_disabled";
   else if(!audit.final_ack_valid) block_reason = "final_ack_missing_or_invalid";
   else if(!audit.max_order_send_attempts_ok) block_reason = "max_order_send_attempts_must_equal_one";
   else if(!InpRequireDemoAccount) block_reason = "demo_requirement_disabled";
   else if(!audit.demo_account_ok) block_reason = "demo_account_required";
   else if(!audit.live_account_forbidden_ok) block_reason = "live_account_forbidden";
   else if(!SymbolAndInputOk()) block_reason = "symbol_not_locked";
   else if(!TimeframeAndInputOk()) block_reason = "timeframe_not_locked";
   else if(!signal_binding_ok) block_reason = "signal_binding_changed";
   else if(!terminal_trade_ok) block_reason = "terminal_trade_disabled";
   else if(!expert_trade_allowed_ok) block_reason = "expert_trade_disabled";
   else if(!symbol_trade_mode_ok) block_reason = "symbol_trade_mode_block";
   else if(!sizing_ok) block_reason = sizing_audit.sizing_block_reason == "" ? "sizing_unavailable" : sizing_audit.sizing_block_reason;
   else if(!request_ok) block_reason = request_block_reason == "" ? "request_unavailable" : request_block_reason;
   else if(!audit.spread_ok) block_reason = "current_spread_exceeded";
   else if(!audit.one_position_only_ok) block_reason = "one_position_only_block";
   else if(!audit.pending_order_ok) block_reason = "pending_order_block";
   else if(!audit.friday_entry_cutoff_ok) block_reason = "friday_entry_cutoff_block";
   else if(!audit.digest_unchanged) block_reason = "request_digest_changed_after_order_check";
   else if(audit.previous_send_attempt_exists) block_reason = "previous_send_attempt_exists";

   if(block_reason != "")
   {
      audit.block_reason = block_reason;
      audit.send_preflight_status = "send_preflight_blocked";
      WriteSendPreflightLog(audit);
      WriteStateTransitionLog(attempt_id,signal_id,snapshot.bar_time,"send_preflight_blocked",block_reason,"send_preflight");
      MqlTradeResult blank_result;
      ZeroMemory(blank_result);
      RequestAudit blocked_request_audit = order_check_audit;
      if(request_ok) blocked_request_audit = preflight_audit;
      else AttachSizingAuditToRequestAudit(sizing_audit, blocked_request_audit);
      OrderSendAudit blocked_send_audit = BuildOrderSendAudit(snapshot.bar_time,attempt_id,signal_id,blocked_request_audit,false,0,blank_result,fresh_snapshot);
      blocked_send_audit.order_send_result_category = "not_called_" + block_reason;
      WriteOrderSendLog(blocked_send_audit);
      WritePostSendReconciliationLog(blocked_send_audit, fresh_snapshot);
      return;
   }

   audit.block_reason = "";
   audit.send_preflight_status = "send_preflight_passed";
   WriteStateTransitionLogWithFlags(attempt_id,signal_id,snapshot.bar_time,"send_attempted","all_final_gates_passed","order_send",true,false);
   g_last_order_send_attempt_id = attempt_id;

   MqlTradeResult send_result;
   ZeroMemory(send_result);
   const bool order_send_function_returned = OrderSend(preflight_request, send_result);
   audit.order_send_called = true;
   audit.order_send_attempt_count = 1;

   BrokerSnapshot post_snapshot = ReadBrokerSnapshot();
   OrderSendAudit send_audit = BuildOrderSendAudit(snapshot.bar_time,attempt_id,signal_id,preflight_audit,true,1,send_result,post_snapshot);
   if(!order_send_function_returned && send_audit.order_send_result_category == "unknown_retcode")
      send_audit.post_send_reconciliation_status = "order_send_returned_false_unknown_retcode_hold";
   StoreConfirmedPositionIdentity(send_audit);
   audit.execution_performed = send_audit.execution_confirmed;
   WriteSendPreflightLog(audit);
   WriteOrderSendLog(send_audit);
   WritePostSendReconciliationLog(send_audit, post_snapshot);
   UpdateRunFinalSummaryCounters(send_audit);
   WriteStateTransitionLogWithFlags(attempt_id,signal_id,snapshot.bar_time,send_audit.final_state_status,send_audit.post_send_reconciliation_status,"post_send_reconciliation",true,send_audit.execution_confirmed);
}bool IntegratedLifecycleConfigOk()
{
   return InpMaxLifecycleCloseAttempts == 1 && InpMaxHoldingBars == MAX_HOLDING_BARS;
}

string IntegratedLifecycleConfigBlockReason()
{
   if(InpMaxLifecycleCloseAttempts != 1) return "max_lifecycle_close_attempts_must_equal_one";
   if(InpMaxHoldingBars != MAX_HOLDING_BARS) return "max_holding_bars_must_equal_ten";
   return "";
}

bool IntegratedFinalLifecycleAckValid()
{
   return InpFinalLifecycleAcknowledgment == FINAL_LIFECYCLE_ACK_TEXT;
}

datetime IntegratedFridayForcedFlatTime(const datetime timestamp)
{
   if(!IsFriday(timestamp)) return 0;
   return SameDayTime(timestamp, InpFridayForcedFlatTime);
}

bool IntegratedFridayForcedFlatRequired(const datetime timestamp)
{
   const datetime forced_flat_time = IntegratedFridayForcedFlatTime(timestamp);
   if(forced_flat_time <= 0) return false;
   return timestamp >= forced_flat_time;
}

bool IntegratedLifecycleEvaluationDue(const datetime current_closed_bar_time)
{
   if(current_closed_bar_time != g_last_integrated_lifecycle_evaluated_bar_time) return true;
   if(!InpEnableIntegratedLifecycleWatch) return false;
   const datetime now = TimeCurrent();
   const datetime forced_flat_time = IntegratedFridayForcedFlatTime(now);
   if(forced_flat_time <= 0) return false;
   return now >= forced_flat_time && g_last_integrated_lifecycle_forced_flat_time != forced_flat_time;
}

void MarkIntegratedLifecycleEvaluated(const datetime current_closed_bar_time)
{
   g_last_integrated_lifecycle_evaluated_bar_time = current_closed_bar_time;
   const datetime now = TimeCurrent();
   const datetime forced_flat_time = IntegratedFridayForcedFlatTime(now);
   if(forced_flat_time > 0 && now >= forced_flat_time)
      g_last_integrated_lifecycle_forced_flat_time = forced_flat_time;
}

datetime IntegratedEntryBarTimeFromPositionTime(const datetime entry_time)
{
   if(entry_time <= 0) return 0;
   const int shift = iBarShift(InpSymbol, InpTimeframe, entry_time, false);
   if(shift < 0) return 0;
   return iTime(InpSymbol, InpTimeframe, shift);
}

int IntegratedClosedBarsAfterEntry(const datetime entry_bar_time,const datetime current_closed_bar_time)
{
   if(entry_bar_time <= 0 || current_closed_bar_time <= 0) return -1;
   const int entry_shift = iBarShift(InpSymbol, InpTimeframe, entry_bar_time, false);
   const int current_shift = iBarShift(InpSymbol, InpTimeframe, current_closed_bar_time, false);
   if(entry_shift < 0 || current_shift < 0) return -1;
   // The entry bar is the first bar completed after execution once it closes.
   const int closed_bars_after_entry = entry_shift - current_shift + 1;
   return closed_bars_after_entry < 0 ? 0 : closed_bars_after_entry;
}

void InitializeIntegratedLifecycleSnapshot(IntegratedLifecycleSnapshot &snapshot,const datetime current_closed_bar_time)
{
   snapshot.timestamp_server = TimeCurrent();
   snapshot.current_closed_bar_time = current_closed_bar_time;
   snapshot.watch_enabled = InpEnableIntegratedLifecycleWatch;
   snapshot.position_observed_open = false;
   snapshot.matching_position_count = 0;
   snapshot.pending_order_count = 0;
   snapshot.position_ticket = 0;
   snapshot.position_type = -1;
   snapshot.position_volume = 0.0;
   snapshot.position_price_open = 0.0;
   snapshot.position_sl = 0.0;
   snapshot.position_tp = 0.0;
   snapshot.entry_time = 0;
   snapshot.entry_bar_time = 0;
   snapshot.bars_elapsed = -1;
   snapshot.bar_count_status = "not_applicable";
   snapshot.exit_reason_preview = "none";
   snapshot.signal_id = "signal_id_unresolved";
   snapshot.attempt_id = "attempt_id_unresolved";
   snapshot.position_identity_status = "no_position_observed";
   snapshot.integrated_lifecycle_status = "no_position_observed";
}

void ReadIntegratedLifecycleSnapshot(IntegratedLifecycleSnapshot &snapshot,const datetime current_closed_bar_time)
{
   InitializeIntegratedLifecycleSnapshot(snapshot, current_closed_bar_time);
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
         snapshot.position_type = (long)PositionGetInteger(POSITION_TYPE);
         snapshot.position_volume = PositionGetDouble(POSITION_VOLUME);
         snapshot.position_price_open = PositionGetDouble(POSITION_PRICE_OPEN);
         snapshot.position_sl = PositionGetDouble(POSITION_SL);
         snapshot.position_tp = PositionGetDouble(POSITION_TP);
         snapshot.entry_time = (datetime)PositionGetInteger(POSITION_TIME);
      }
   }

   if(snapshot.matching_position_count == 0)
   {
      snapshot.position_identity_status = "no_position_observed";
      snapshot.integrated_lifecycle_status = "no_position_observed";
      return;
   }

   if(snapshot.matching_position_count > 1)
   {
      snapshot.position_identity_status = "multiple_matching_positions_blocked";
      snapshot.integrated_lifecycle_status = "multiple_matching_positions_blocked";
      return;
   }

   snapshot.position_observed_open = true;
   snapshot.integrated_lifecycle_status = "position_observed_open";
   if(snapshot.position_ticket == g_confirmed_position_ticket && g_confirmed_position_ticket > 0 && g_confirmed_entry_signal_id != "" && g_confirmed_entry_attempt_id != "")
   {
      snapshot.signal_id = g_confirmed_entry_signal_id;
      snapshot.attempt_id = g_confirmed_entry_attempt_id;
      snapshot.position_identity_status = "matched_confirmed_entry";
      if(g_confirmed_entry_time > 0) snapshot.entry_time = g_confirmed_entry_time;
      snapshot.entry_bar_time = g_confirmed_entry_bar_time;
   }
   else
   {
      snapshot.signal_id = "signal_id_unresolved";
      snapshot.attempt_id = "attempt_id_unresolved";
      snapshot.position_identity_status = "unresolved_after_restart_or_external_position";
   }
   if(snapshot.entry_bar_time <= 0)
      snapshot.entry_bar_time = IntegratedEntryBarTimeFromPositionTime(snapshot.entry_time);
   if(snapshot.entry_bar_time <= 0)
   {
      snapshot.integrated_lifecycle_status = "entry_bar_time_unresolved";
      snapshot.bar_count_status = "entry_bar_time_unresolved";
      return;
   }

   snapshot.bars_elapsed = IntegratedClosedBarsAfterEntry(snapshot.entry_bar_time, current_closed_bar_time);
   if(snapshot.bars_elapsed < 0)
   {
      snapshot.integrated_lifecycle_status = "bar_count_unavailable";
      snapshot.bar_count_status = "bar_count_unavailable";
      return;
   }
   snapshot.bar_count_status = "ok";

   if(IntegratedFridayForcedFlatRequired(snapshot.timestamp_server))
   {
      snapshot.exit_reason_preview = "friday_forced_flat";
      return;
   }

   if(snapshot.bars_elapsed >= InpMaxHoldingBars)
      snapshot.exit_reason_preview = "time_exit_10_m15_bars";
}

string IntegratedLifecycleStateForSnapshot(const IntegratedLifecycleSnapshot &snapshot)
{
   if(snapshot.integrated_lifecycle_status == "integrated_lifecycle_watch_disabled") return "integrated_lifecycle_watch_disabled";
   if(snapshot.integrated_lifecycle_status == "multiple_matching_positions_blocked") return "multiple_matching_positions_blocked";
   if(snapshot.integrated_lifecycle_status == "entry_bar_time_unresolved") return "entry_bar_time_unresolved";
   if(snapshot.integrated_lifecycle_status == "bar_count_unavailable") return "bar_count_unavailable";
   if(snapshot.integrated_lifecycle_status == "no_position_observed") return "no_position_observed";
   if(snapshot.exit_reason_preview == "time_exit_10_m15_bars") return "position_close_required_time_exit_watch_only";
   if(snapshot.exit_reason_preview == "friday_forced_flat") return "position_close_required_friday_forced_flat_watch_only";
   return "position_observed_open";
}

void WriteIntegratedLifecycleWatchHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","timeframe","magic_number","watch_enabled","position_observed_open","matching_position_count","position_ticket","position_type","position_volume","position_price_open","position_sl","position_tp","entry_time","entry_bar_time","current_closed_bar_time","bars_elapsed","bar_count_status","max_holding_bars","friday_forced_flat_time","exit_reason_preview","signal_id","attempt_id","position_identity_status","integrated_lifecycle_status");
}

void WriteIntegratedLifecycleWatchLog(const IntegratedLifecycleSnapshot &snapshot)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(INTEGRATED_LIFECYCLE_WATCH_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteIntegratedLifecycleWatchHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(snapshot.timestamp_server),CANDIDATE_ID,InpSymbol,TimeframeText(),SafeLongToString(InpMagicNumber),BoolText(snapshot.watch_enabled),BoolText(snapshot.position_observed_open),IntegerToString(snapshot.matching_position_count),snapshot.position_ticket > 0 ? SafeLongToString((long)snapshot.position_ticket) : "",snapshot.position_type >= 0 ? IntegerToString((int)snapshot.position_type) : "",FormatNumber(snapshot.position_volume),FormatNumber(snapshot.position_price_open),FormatNumber(snapshot.position_sl),FormatNumber(snapshot.position_tp),FormatTimeServer(snapshot.entry_time),FormatTimeServer(snapshot.entry_bar_time),FormatTimeServer(snapshot.current_closed_bar_time),snapshot.bars_elapsed >= 0 ? IntegerToString(snapshot.bars_elapsed) : "",snapshot.bar_count_status,IntegerToString(InpMaxHoldingBars),InpFridayForcedFlatTime,snapshot.exit_reason_preview,snapshot.signal_id,snapshot.attempt_id,snapshot.position_identity_status,snapshot.integrated_lifecycle_status);
   FileClose(handle);
}

void WriteIntegratedLifecycleExitDecisionHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","position_ticket","position_identity_status","entry_time","entry_bar_time","current_time_server","bars_elapsed","exit_reason_preview","watch_enabled","close_preflight_enabled","close_enabled","final_lifecycle_ack_valid","decision","block_reason","close_called","close_attempt_count","retry_performed","automatic_retry_allowed","lifecycle_close_attempt_id","lifecycle_close_result_status");
}

void WriteIntegratedLifecycleExitDecisionLog(const IntegratedLifecycleSnapshot &snapshot,const string decision,const string block_reason,const IntegratedLifecycleCloseAudit &audit)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(INTEGRATED_LIFECYCLE_EXIT_DECISION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteIntegratedLifecycleExitDecisionHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),CANDIDATE_ID,InpSymbol,snapshot.position_ticket > 0 ? SafeLongToString((long)snapshot.position_ticket) : "",snapshot.position_identity_status,FormatTimeServer(snapshot.entry_time),FormatTimeServer(snapshot.entry_bar_time),FormatTimeServer(snapshot.timestamp_server),snapshot.bars_elapsed >= 0 ? IntegerToString(snapshot.bars_elapsed) : "",snapshot.exit_reason_preview,BoolText(InpEnableIntegratedLifecycleWatch),BoolText(InpEnableIntegratedLifecycleClosePreflight),BoolText(InpEnableIntegratedLifecycleClose),BoolText(IntegratedFinalLifecycleAckValid()),decision,block_reason,BoolText(audit.close_called),IntegerToString(audit.close_attempt_count),BoolText(audit.retry_performed),BoolText(audit.automatic_retry_allowed),audit.lifecycle_close_attempt_id,audit.lifecycle_close_result_status);
   FileClose(handle);
}
void WriteIntegratedLifecycleReconciliationHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","magic_number","matching_position_count","pending_order_count","position_ticket","position_identity_status","position_volume","position_price_open","position_sl","position_tp","reconciliation_status");
}

void WriteIntegratedLifecycleReconciliationLog(const IntegratedLifecycleSnapshot &snapshot)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(INTEGRATED_LIFECYCLE_RECONCILIATION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteIntegratedLifecycleReconciliationHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(snapshot.timestamp_server),CANDIDATE_ID,InpSymbol,SafeLongToString(InpMagicNumber),IntegerToString(snapshot.matching_position_count),IntegerToString(snapshot.pending_order_count),snapshot.position_ticket > 0 ? SafeLongToString((long)snapshot.position_ticket) : "",snapshot.position_identity_status,FormatNumber(snapshot.position_volume),FormatNumber(snapshot.position_price_open),FormatNumber(snapshot.position_sl),FormatNumber(snapshot.position_tp),snapshot.integrated_lifecycle_status);
   FileClose(handle);
}

void WriteIntegratedLifecycleStateTransitionHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","signal_id","attempt_id","lifecycle_close_attempt_id","position_ticket","position_identity_status","previous_state","next_state","exit_reason_preview","source_gate","close_called","close_attempt_count","close_confirmed","manual_intervention_required","unresolved_policy_action");
}

void WriteIntegratedLifecycleStateTransitionLog(const IntegratedLifecycleSnapshot &snapshot,const string next_state,const string source_gate,const IntegratedLifecycleCloseAudit &audit)
{
   bool write_header = false;
   const int handle = OpenLogForAppend(INTEGRATED_LIFECYCLE_STATE_TRANSITION_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteIntegratedLifecycleStateTransitionHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(snapshot.timestamp_server),CANDIDATE_ID,InpSymbol,snapshot.signal_id,snapshot.attempt_id,audit.lifecycle_close_attempt_id,snapshot.position_ticket > 0 ? SafeLongToString((long)snapshot.position_ticket) : "",snapshot.position_identity_status,g_current_integrated_lifecycle_state,next_state,snapshot.exit_reason_preview,source_gate,BoolText(audit.close_called),IntegerToString(audit.close_attempt_count),BoolText(audit.close_confirmed),BoolText(audit.manual_intervention_required),audit.unresolved_policy_action);
   FileClose(handle);
   g_current_integrated_lifecycle_state = next_state;
}

bool IntegratedLifecycleExitReasonValid(const string exit_reason)
{
   return exit_reason == "time_exit_10_m15_bars" || exit_reason == "friday_forced_flat";
}

bool IntegratedLifecyclePositionIdentityAllowed(const string position_identity_status)
{
   return position_identity_status == "matched_confirmed_entry";
}

string LifecycleCloseAttemptCanonical(const IntegratedLifecycleSnapshot &snapshot)
{
   return "candidate_id=" + CANDIDATE_ID +
      "|symbol=" + REQUIRED_SYMBOL +
      "|position_ticket=" + SafeLongToString((long)snapshot.position_ticket) +
      "|exit_reason=" + snapshot.exit_reason_preview +
      "|entry_attempt_id=" + snapshot.attempt_id +
      "|run_id=" + g_run_id;
}

string LifecycleCloseAttemptId(const IntegratedLifecycleSnapshot &snapshot)
{
   return StableId("lifecycle_close_attempt", LifecycleCloseAttemptCanonical(snapshot));
}

string LifecycleClosePreflightKey(const IntegratedLifecycleSnapshot &snapshot)
{
   return SafeLongToString((long)snapshot.position_ticket) + "|" + snapshot.exit_reason_preview + "|" + snapshot.attempt_id;
}

bool LifecycleClosePreflightDuplicateExists(const string preflight_key)
{
   for(int index = 0; index < ArraySize(g_lifecycle_close_preflight_keys); index++)
   {
      if(g_lifecycle_close_preflight_keys[index] == preflight_key) return true;
   }
   return false;
}

void RememberLifecycleClosePreflightKey(const string preflight_key)
{
   if(preflight_key == "") return;
   const int current_size = ArraySize(g_lifecycle_close_preflight_keys);
   ArrayResize(g_lifecycle_close_preflight_keys, current_size + 1);
   g_lifecycle_close_preflight_keys[current_size] = preflight_key;
}

bool LifecycleCloseSendDuplicateExists(const string lifecycle_close_attempt_id)
{
   for(int index = 0; index < ArraySize(g_lifecycle_close_sent_attempt_ids); index++)
   {
      if(g_lifecycle_close_sent_attempt_ids[index] == lifecycle_close_attempt_id) return true;
   }
   return false;
}

void RememberLifecycleCloseSentAttempt(const string lifecycle_close_attempt_id)
{
   if(lifecycle_close_attempt_id == "") return;
   const int current_size = ArraySize(g_lifecycle_close_sent_attempt_ids);
   ArrayResize(g_lifecycle_close_sent_attempt_ids, current_size + 1);
   g_lifecycle_close_sent_attempt_ids[current_size] = lifecycle_close_attempt_id;
}

bool ResolveLifecycleCloseFillingMode(ENUM_ORDER_TYPE_FILLING &filling_mode)
{
   const long symbol_filling_mode = SymbolInfoInteger(InpSymbol, SYMBOL_FILLING_MODE);
   if((symbol_filling_mode & SYMBOL_FILLING_IOC) == SYMBOL_FILLING_IOC)
   {
      filling_mode = ORDER_FILLING_IOC;
      return true;
   }
   if((symbol_filling_mode & SYMBOL_FILLING_FOK) == SYMBOL_FILLING_FOK)
   {
      filling_mode = ORDER_FILLING_FOK;
      return true;
   }
   filling_mode = ORDER_FILLING_RETURN;
   return true;
}

bool FullCloseVolumeValid(const double position_volume,double &close_volume)
{
   close_volume = 0.0;
   if(position_volume <= 0.0) return false;
   double normalized_volume = 0.0;
   if(!NormalizeVolumeToStep(position_volume, normalized_volume)) return false;
   const double volume_step = SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP);
   const double tolerance = volume_step > 0.0 ? volume_step / 10.0 : 0.00000001;
   if(MathAbs(normalized_volume - position_volume) > tolerance) return false;
   close_volume = normalized_volume;
   return close_volume > 0.0;
}

string CanonicalLifecycleCloseRequestString(const IntegratedLifecycleSnapshot &snapshot,const MqlTradeRequest &request)
{
   return LifecycleCloseAttemptCanonical(snapshot) +
      "|phase=integrated_lifecycle_single_close" +
      "|action=" + IntegerToString((int)request.action) +
      "|type=" + IntegerToString((int)request.type) +
      "|position=" + SafeLongToString((long)request.position) +
      "|volume=" + FormatNumber(request.volume) +
      "|price=" + FormatNumber(request.price) +
      "|deviation=" + IntegerToString((int)request.deviation) +
      "|magic=" + SafeLongToString((long)request.magic) +
      "|comment=" + request.comment +
      "|type_time=" + IntegerToString((int)request.type_time) +
      "|type_filling=" + IntegerToString((int)request.type_filling);
}

string LifecycleCloseRequestDigestFromRequest(const IntegratedLifecycleSnapshot &snapshot,const MqlTradeRequest &request)
{
   return "lifecycle_close_attempt_digest_non_crypto_" + Hash32Text(CanonicalLifecycleCloseRequestString(snapshot, request));
}

bool BuildLifecycleCloseRequest(const IntegratedLifecycleSnapshot &snapshot,MqlTradeRequest &close_request,string &close_request_digest,double &close_request_price,string &block_reason)
{
   close_request_digest = "";
   close_request_price = 0.0;
   block_reason = "";
   double close_volume = 0.0;
   if(!FullCloseVolumeValid(snapshot.position_volume, close_volume))
   {
      block_reason = "close_invalid_volume";
      return false;
   }
   const double ask_price = SymbolInfoDouble(InpSymbol, SYMBOL_ASK);
   if(ask_price <= 0.0)
   {
      block_reason = "close_price_unavailable";
      return false;
   }
   ENUM_ORDER_TYPE_FILLING filling_mode;
   if(!ResolveLifecycleCloseFillingMode(filling_mode))
   {
      block_reason = "close_filling_mode_unavailable";
      return false;
   }
   ZeroMemory(close_request);
   close_request.action = TRADE_ACTION_DEAL;
   close_request.symbol = InpSymbol;
   close_request.volume = close_volume;
   close_request.type = ORDER_TYPE_BUY;
   close_request.price = NormalizeSymbolPrice(ask_price);
   close_request.position = snapshot.position_ticket;
   close_request.deviation = ORDER_CHECK_DEVIATION_POINTS;
   close_request.magic = (ulong)InpMagicNumber;
   close_request.comment = LIFECYCLE_CLOSE_COMMENT;
   close_request.type_time = ORDER_TIME_GTC;
   close_request.type_filling = filling_mode;
   close_request_price = close_request.price;
   close_request_digest = LifecycleCloseRequestDigestFromRequest(snapshot, close_request);
   return true;
}

string CloseRetcodeResultCategory(const uint retcode)
{
   switch(retcode)
   {
      case TRADE_RETCODE_DONE:
      case TRADE_RETCODE_PLACED:
      case TRADE_RETCODE_DONE_PARTIAL:
         return "close_success_accepted";
      case TRADE_RETCODE_MARKET_CLOSED:
         return "close_market_closed";
      case TRADE_RETCODE_TRADE_DISABLED:
      case TRADE_RETCODE_ONLY_REAL:
      case TRADE_RETCODE_CLIENT_DISABLES_AT:
      case TRADE_RETCODE_SERVER_DISABLES_AT:
         return "close_trade_disabled";
      case TRADE_RETCODE_INVALID_VOLUME:
         return "close_invalid_volume";
      case TRADE_RETCODE_REQUOTE:
      case TRADE_RETCODE_PRICE_CHANGED:
      case TRADE_RETCODE_PRICE_OFF:
      case TRADE_RETCODE_INVALID_PRICE:
         return "close_price_changed_or_requote";
      case TRADE_RETCODE_NO_MONEY:
         return "close_no_money_or_margin";
      case TRADE_RETCODE_TIMEOUT:
      case TRADE_RETCODE_CONNECTION:
      case TRADE_RETCODE_TOO_MANY_REQUESTS:
      case TRADE_RETCODE_LOCKED:
      case TRADE_RETCODE_FROZEN:
         return "close_timeout_or_uncertain";
      case TRADE_RETCODE_REJECT:
      case TRADE_RETCODE_CANCEL:
      case TRADE_RETCODE_ERROR:
      case TRADE_RETCODE_INVALID:
         return "close_rejected_no_retry";
   }
   return "close_unknown_retcode";
}

bool CloseRejectedNoRetryCategory(const string category)
{
   return category == "close_rejected_no_retry" || category == "close_rejected_position_already_closed" || category == "close_market_closed" || category == "close_trade_disabled" || category == "close_invalid_volume" || category == "close_price_changed_or_requote" || category == "close_no_money_or_margin";
}

bool CloseUncertainCategory(const string category)
{
   return category == "close_timeout_or_uncertain" || category == "close_unknown_retcode";
}

string PostCloseReconciliationStatus(const string category,const bool close_confirmed,const BrokerSnapshot &post_snapshot)
{
   if(close_confirmed) return "position_flat_confirmed_after_close";
   if(category == "close_success_accepted") return post_snapshot.position_count == 0 ? "success_retcode_flat_pending_conflict_hold" : "success_retcode_position_still_open_hold";
   if(category == "close_rejected_position_already_closed") return "rejected_position_already_flat";
   if(CloseUncertainCategory(category)) return post_snapshot.position_count == 0 ? "uncertain_flat_snapshot_hold" : "uncertain_position_state_hold";
   if(CloseRejectedNoRetryCategory(category) && post_snapshot.position_count == 0) return "rejected_but_position_already_flat";
   if(CloseRejectedNoRetryCategory(category)) return "rejected_position_still_open";
   return "close_unknown_reconciliation_hold";
}

string FinalLifecycleCloseResultStatus(const string category,const bool close_confirmed,const BrokerSnapshot &post_snapshot)
{
   if(close_confirmed) return "position_close_confirmed";
   if(category == "close_success_accepted") return "position_close_uncertain_reconciliation_hold";
   if(CloseUncertainCategory(category)) return "position_close_uncertain_reconciliation_hold";
   if(category == "close_rejected_position_already_closed") return "position_close_skipped_already_closed_by_broker";
   if(CloseRejectedNoRetryCategory(category) && post_snapshot.position_count == 0) return "position_close_skipped_already_closed_by_broker";
   if(CloseRejectedNoRetryCategory(category)) return "position_close_rejected_no_retry";
   return "position_close_uncertain_reconciliation_hold";
}

void InitializeIntegratedLifecycleCloseAudit(IntegratedLifecycleCloseAudit &audit)
{
   audit.lifecycle_close_attempt_id = "";
   audit.close_request_digest = "";
   audit.close_request_digest_preflight = "";
   audit.close_request_digest_before_send = "";
   audit.close_request_unchanged_after_preflight = false;
   audit.close_price_preview = 0.0;
   audit.close_request_price = 0.0;
   audit.close_result_bid = 0.0;
   audit.close_result_ask = 0.0;
   audit.close_result_volume = 0.0;
   audit.close_preflight_status = "position_close_preflight_not_required";
   audit.block_reason = "";
   audit.final_position_count = CountPositionsForCandidate();
   audit.close_called = false;
   audit.close_attempt_count = 0;
   audit.close_retcode = 0;
   audit.close_comment = "no_close_preflight_only";
   audit.close_deal_ticket = 0;
   audit.close_order_ticket = 0;
   audit.close_confirmed = false;
   audit.post_close_reconciliation_status = "no_close_no_broker_mutation";
   audit.close_result_category = "not_called";
   audit.close_identity_status = "not_evaluated";
   audit.lifecycle_close_sent = false;
   audit.lifecycle_close_result_status = "position_close_preflight_not_required";
   audit.manual_intervention_required = false;
   audit.unresolved_policy_action = "";
   audit.retry_performed = false;
   audit.automatic_retry_allowed = false;
}

void WriteIntegratedLifecycleCloseHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","symbol","magic_number","position_ticket","position_type","entry_signal_id","entry_attempt_id","lifecycle_close_attempt_id","position_identity_status","entry_time","entry_bar_time","current_time_server","current_closed_bar_time","bars_elapsed","exit_reason","volume","close_price_preview","close_request_price","close_request_digest","close_request_digest_preflight","close_request_digest_before_send","close_request_unchanged_after_preflight","close_preflight_enabled","close_enabled","final_lifecycle_ack_valid","close_preflight_status","block_reason","close_called","close_attempt_count","close_retcode","close_comment","close_deal_ticket","close_order_ticket","close_confirmed","final_position_count","retry_performed","automatic_retry_allowed","close_result_category","post_close_reconciliation_status","close_identity_status","lifecycle_close_sent","lifecycle_close_result_status","close_result_bid","close_result_ask","close_result_volume","manual_intervention_required","unresolved_policy_action");
}

void WriteIntegratedLifecycleCloseLog(const IntegratedLifecycleSnapshot &snapshot,const IntegratedLifecycleCloseAudit &audit)
{
   UpdateLifecycleCloseFinalSummaryCounters(snapshot,audit);
   bool write_header = false;
   const int handle = OpenLogForAppend(INTEGRATED_POSITION_CLOSE_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteIntegratedLifecycleCloseHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),CANDIDATE_ID,InpSymbol,SafeLongToString(InpMagicNumber),snapshot.position_ticket > 0 ? SafeLongToString((long)snapshot.position_ticket) : "",snapshot.position_type >= 0 ? IntegerToString((int)snapshot.position_type) : "",snapshot.signal_id,snapshot.attempt_id,audit.lifecycle_close_attempt_id,snapshot.position_identity_status,FormatTimeServer(snapshot.entry_time),FormatTimeServer(snapshot.entry_bar_time),FormatTimeServer(snapshot.timestamp_server),FormatTimeServer(snapshot.current_closed_bar_time),snapshot.bars_elapsed >= 0 ? IntegerToString(snapshot.bars_elapsed) : "",snapshot.exit_reason_preview,FormatNumber(snapshot.position_volume),audit.close_price_preview > 0.0 ? FormatNumber(audit.close_price_preview) : "",audit.close_request_price > 0.0 ? FormatNumber(audit.close_request_price) : "",audit.close_request_digest,audit.close_request_digest_preflight,audit.close_request_digest_before_send,BoolText(audit.close_request_unchanged_after_preflight),BoolText(InpEnableIntegratedLifecycleClosePreflight),BoolText(InpEnableIntegratedLifecycleClose),BoolText(IntegratedFinalLifecycleAckValid()),audit.close_preflight_status,audit.block_reason,BoolText(audit.close_called),IntegerToString(audit.close_attempt_count),audit.close_called ? IntegerToString((int)audit.close_retcode) : "",audit.close_comment,audit.close_deal_ticket > 0 ? SafeLongToString((long)audit.close_deal_ticket) : "",audit.close_order_ticket > 0 ? SafeLongToString((long)audit.close_order_ticket) : "",BoolText(audit.close_confirmed),IntegerToString(audit.final_position_count),BoolText(audit.retry_performed),BoolText(audit.automatic_retry_allowed),audit.close_result_category,audit.post_close_reconciliation_status,audit.close_identity_status,BoolText(audit.lifecycle_close_sent),audit.lifecycle_close_result_status,audit.close_result_bid > 0.0 ? FormatNumber(audit.close_result_bid) : "",audit.close_result_ask > 0.0 ? FormatNumber(audit.close_result_ask) : "",audit.close_result_volume > 0.0 ? FormatNumber(audit.close_result_volume) : "",BoolText(audit.manual_intervention_required),audit.unresolved_policy_action);
   FileClose(handle);
}

IntegratedLifecycleCloseAudit EvaluateIntegratedLifecycleClosePreflight(const IntegratedLifecycleSnapshot &snapshot,const string config_block_reason)
{
   IntegratedLifecycleCloseAudit audit;
   InitializeIntegratedLifecycleCloseAudit(audit);
   audit.close_identity_status = snapshot.position_identity_status;

   if(!InpEnableIntegratedLifecycleWatch)
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.lifecycle_close_result_status = audit.close_preflight_status;
      audit.block_reason = "integrated_lifecycle_watch_disabled";
      WriteIntegratedLifecycleCloseLog(snapshot,audit);
      return audit;
   }

   if(config_block_reason != "")
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.lifecycle_close_result_status = audit.close_preflight_status;
      audit.block_reason = config_block_reason;
      WriteIntegratedLifecycleCloseLog(snapshot,audit);
      return audit;
   }

   if(!IntegratedLifecycleExitReasonValid(snapshot.exit_reason_preview))
   {
      audit.close_preflight_status = "position_close_preflight_not_required";
      audit.lifecycle_close_result_status = audit.close_preflight_status;
      WriteIntegratedLifecycleCloseLog(snapshot,audit);
      return audit;
   }

   if(snapshot.position_identity_status == "unresolved_after_restart_or_external_position")
   {
      audit.lifecycle_close_attempt_id = LifecycleCloseAttemptId(snapshot);
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.lifecycle_close_result_status = "position_identity_unresolved_manual_review_required";
      audit.close_result_category = "not_called_position_identity_unresolved";
      audit.block_reason = "position_identity_unresolved_manual_review_required";
      audit.close_comment = "manual_review_required_unresolved_identity";
      audit.manual_intervention_required = true;
      audit.unresolved_policy_action = "block_lifecycle_close";
      WriteIntegratedLifecycleCloseLog(snapshot,audit);
      return audit;
   }

   audit.lifecycle_close_attempt_id = LifecycleCloseAttemptId(snapshot);
   MqlTradeRequest close_request_preflight;
   string request_block_reason = "";
   const bool request_ok = BuildLifecycleCloseRequest(snapshot, close_request_preflight, audit.close_request_digest_preflight, audit.close_request_price, request_block_reason);
   audit.close_request_digest = audit.close_request_digest_preflight;
   audit.close_price_preview = audit.close_request_price;

   IntegratedLifecycleSnapshot fresh_snapshot;
   ReadIntegratedLifecycleSnapshot(fresh_snapshot, snapshot.current_closed_bar_time);
   audit.final_position_count = fresh_snapshot.matching_position_count;
   const bool fresh_reconciliation_clean_enough = fresh_snapshot.matching_position_count == 1 && fresh_snapshot.position_ticket == snapshot.position_ticket && fresh_snapshot.pending_order_count == 0;
   const string preflight_key = LifecycleClosePreflightKey(snapshot);

   if(!InpEnableIntegratedLifecycleClosePreflight)
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "integrated_lifecycle_close_preflight_disabled";
   }
   else if(!InpRequireDemoAccount)
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "demo_requirement_disabled";
   }
   else if(!(InpRequireDemoAccount && IsDemoAccount()))
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "demo_account_required";
   }
   else if(InpAllowLiveAccount)
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "live_account_input_enabled";
   }
   else if(IsLiveAccount())
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "live_account_forbidden";
   }
   else if(!SymbolAndInputOk())
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "symbol_not_locked";
   }
   else if(!TimeframeAndInputOk())
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "timeframe_not_locked";
   }
   else if(snapshot.matching_position_count != 1 || snapshot.position_ticket == 0)
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "exactly_one_matching_position_required";
   }
   else if(snapshot.position_type != POSITION_TYPE_SELL)
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "position_type_not_short";
   }
   else if(!IntegratedLifecyclePositionIdentityAllowed(snapshot.position_identity_status))
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "position_identity_not_allowed_for_close_preflight";
   }
   else if(InpMaxLifecycleCloseAttempts != 1)
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "max_lifecycle_close_attempts_must_equal_one";
   }
   else if(!TerminalTradeAllowed())
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "terminal_trade_not_allowed";
   }
   else if(!ExpertTradeAllowed())
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "expert_trade_not_allowed";
   }
   else if(fresh_snapshot.matching_position_count == 0)
   {
      audit.close_preflight_status = "position_close_skipped_already_closed_by_broker";
      audit.block_reason = "position_already_closed_by_broker_before_close";
   }
   else if(!fresh_reconciliation_clean_enough)
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "fresh_reconciliation_not_clean";
   }
   else if(!request_ok)
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = request_block_reason == "" ? "close_request_unavailable" : request_block_reason;
   }
   else if(!IntegratedFinalLifecycleAckValid())
   {
      audit.close_preflight_status = "position_close_preflight_blocked";
      audit.block_reason = "final_lifecycle_ack_missing_or_invalid";
   }
   else if(LifecycleClosePreflightDuplicateExists(preflight_key))
   {
      audit.close_preflight_status = "position_close_preflight_duplicate_blocked";
      audit.block_reason = "position_close_preflight_duplicate_blocked";
   }
   else
   {
      RememberLifecycleClosePreflightKey(preflight_key);
      if(!InpEnableIntegratedLifecycleClose)
      {
         audit.close_preflight_status = "position_close_preflight_passed_no_close";
      }
      else
      {
         audit.close_preflight_status = "position_close_preflight_passed";
      }
   }

   audit.lifecycle_close_result_status = audit.close_preflight_status;
   if(audit.close_preflight_status != "position_close_preflight_passed")
   {
      WriteIntegratedLifecycleCloseLog(snapshot,audit);
      return audit;
   }

   if(g_integrated_lifecycle_uncertain_hold)
   {
      audit.close_preflight_status = "position_close_blocked";
      audit.lifecycle_close_result_status = "position_close_blocked";
      audit.block_reason = "existing_lifecycle_uncertainty_hold";
      WriteIntegratedLifecycleCloseLog(snapshot,audit);
      return audit;
   }

   if(LifecycleCloseSendDuplicateExists(audit.lifecycle_close_attempt_id))
   {
      audit.close_preflight_status = "position_close_blocked";
      audit.lifecycle_close_result_status = "position_close_duplicate_send_blocked";
      audit.block_reason = "position_close_duplicate_send_blocked";
      WriteIntegratedLifecycleCloseLog(snapshot,audit);
      return audit;
   }

   MqlTradeRequest close_request_before_send;
   double before_send_price = 0.0;
   string before_send_digest = "";
   string before_send_block_reason = "";
   if(!BuildLifecycleCloseRequest(snapshot, close_request_before_send, before_send_digest, before_send_price, before_send_block_reason))
   {
      audit.close_preflight_status = "position_close_blocked";
      audit.lifecycle_close_result_status = "position_close_blocked";
      audit.block_reason = before_send_block_reason == "" ? "close_request_unavailable_before_send" : before_send_block_reason;
      WriteIntegratedLifecycleCloseLog(snapshot,audit);
      return audit;
   }

   audit.close_request_digest_before_send = before_send_digest;
   audit.close_request_unchanged_after_preflight = audit.close_request_digest_preflight != "" && audit.close_request_digest_preflight == audit.close_request_digest_before_send;
   if(!audit.close_request_unchanged_after_preflight)
   {
      audit.close_preflight_status = "position_close_blocked";
      audit.lifecycle_close_result_status = "position_close_blocked";
      audit.block_reason = "close_request_digest_changed_before_send";
      WriteIntegratedLifecycleCloseLog(snapshot,audit);
      return audit;
   }

   audit.close_called = true;
   audit.close_attempt_count = 1;
   audit.lifecycle_close_sent = true;
   audit.lifecycle_close_result_status = "position_close_attempted";
   RememberLifecycleCloseSentAttempt(audit.lifecycle_close_attempt_id);
   WriteIntegratedLifecycleStateTransitionLog(snapshot,"position_close_attempted","lifecycle_close_order_send",audit);

   MqlTradeResult close_result;
   ZeroMemory(close_result);
   const bool lifecycle_close_order_send_returned = OrderSend(close_request_before_send, close_result);
   audit.close_retcode = close_result.retcode;
   audit.close_comment = close_result.comment;
   audit.close_deal_ticket = close_result.deal;
   audit.close_order_ticket = close_result.order;
   audit.close_result_bid = close_result.bid;
   audit.close_result_ask = close_result.ask;
   audit.close_result_volume = close_result.volume;
   audit.close_result_category = CloseRetcodeResultCategory(close_result.retcode);

   BrokerSnapshot post_close_snapshot = ReadBrokerSnapshot();
   audit.final_position_count = post_close_snapshot.position_count;
   if(CloseRejectedNoRetryCategory(audit.close_result_category) && post_close_snapshot.position_count == 0)
      audit.close_result_category = "close_rejected_position_already_closed";
   audit.close_confirmed = audit.close_result_category == "close_success_accepted" && post_close_snapshot.position_count == 0 && post_close_snapshot.pending_order_count == 0;
   audit.post_close_reconciliation_status = PostCloseReconciliationStatus(audit.close_result_category,audit.close_confirmed,post_close_snapshot);
   if(!lifecycle_close_order_send_returned && audit.close_result_category == "close_unknown_retcode")
      audit.post_close_reconciliation_status = "close_order_send_returned_false_unknown_retcode_hold";
   audit.lifecycle_close_result_status = FinalLifecycleCloseResultStatus(audit.close_result_category,audit.close_confirmed,post_close_snapshot);
   if(audit.lifecycle_close_result_status == "position_close_uncertain_reconciliation_hold")
      g_integrated_lifecycle_uncertain_hold = true;

   WriteIntegratedLifecycleCloseLog(snapshot,audit);
   return audit;
}

string IntegratedLifecycleNextStateForClosePreflight(const IntegratedLifecycleSnapshot &snapshot,const IntegratedLifecycleCloseAudit &audit)
{
   if(audit.lifecycle_close_result_status != "") return audit.lifecycle_close_result_status;
   if(snapshot.integrated_lifecycle_status != "position_observed_open") return IntegratedLifecycleStateForSnapshot(snapshot);
   return IntegratedLifecycleStateForSnapshot(snapshot);
}
void EvaluateIntegratedLifecycleWatch(const datetime current_closed_bar_time)
{
   IntegratedLifecycleSnapshot snapshot;
   const string config_block_reason = IntegratedLifecycleConfigBlockReason();
   if(!InpEnableIntegratedLifecycleWatch || config_block_reason != "")
   {
      InitializeIntegratedLifecycleSnapshot(snapshot, current_closed_bar_time);
      snapshot.pending_order_count = CountPendingOrdersForCandidate();
      snapshot.integrated_lifecycle_status = "integrated_lifecycle_watch_disabled";
   }
   else
   {
      ReadIntegratedLifecycleSnapshot(snapshot, current_closed_bar_time);
   }

   WriteIntegratedLifecycleReconciliationLog(snapshot);
   WriteIntegratedLifecycleWatchLog(snapshot);
   IntegratedLifecycleCloseAudit close_audit = EvaluateIntegratedLifecycleClosePreflight(snapshot, config_block_reason);

   string decision = close_audit.close_preflight_status;
   string block_reason = close_audit.block_reason;
   const string next_state = IntegratedLifecycleNextStateForClosePreflight(snapshot, close_audit);

   WriteIntegratedLifecycleExitDecisionLog(snapshot,decision,block_reason,close_audit);
   WriteIntegratedLifecycleStateTransitionLog(snapshot,next_state,decision,close_audit);
   MarkIntegratedLifecycleEvaluated(current_closed_bar_time);
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
   DeleteRunLogFile(ENTRY_SIGNAL_FRESHNESS_LOG);
   DeleteRunLogFile(SIGNAL_LOG);
   DeleteRunLogFile(DECISION_LOG);
   DeleteRunLogFile(ORDER_CHECK_LOG);
   DeleteRunLogFile(SEND_PREFLIGHT_LOG);
   DeleteRunLogFile(ORDER_SEND_LOG);
   DeleteRunLogFile(POSITION_SIZING_LOG);
   DeleteRunLogFile(STATE_TRANSITION_LOG);
   DeleteRunLogFile(POST_SEND_RECONCILIATION_LOG);
   DeleteRunLogFile(RUN_FINAL_SUMMARY_LOG);
   DeleteRunLogFile(TRADE_TRANSACTIONS_LOG);
   DeleteRunLogFile(RECONCILIATION_LOG);
   DeleteRunLogFile(POSITION_LIFECYCLE_LOG);
   DeleteRunLogFile(INTEGRATED_LIFECYCLE_WATCH_LOG);
   DeleteRunLogFile(INTEGRATED_LIFECYCLE_EXIT_DECISION_LOG);
   DeleteRunLogFile(INTEGRATED_LIFECYCLE_RECONCILIATION_LOG);
   DeleteRunLogFile(INTEGRATED_LIFECYCLE_STATE_TRANSITION_LOG);
   DeleteRunLogFile(INTEGRATED_POSITION_CLOSE_LOG);
}

void WriteRunConfigHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","snapshot_type","candidate_id","symbol","timeframe","InpEnableOrderCheck","InpEnableSendPreflight","InpEnableOrderSend","InpEnableIntegratedLifecycleWatch","InpEnableIntegratedLifecycleClosePreflight","InpEnableIntegratedLifecycleClose","InpFinalSendAcknowledgment","final_ack_valid","InpFinalLifecycleAcknowledgment","final_lifecycle_ack_valid","InpMaxOrderSendAttempts","max_order_send_attempts_ok","InpMaxLifecycleCloseAttempts","max_lifecycle_close_attempts_ok","InpRequireDemoAccount","InpAllowLiveAccount","InpLogCommonFiles","InpVolumeLots","InpUseRiskBasedSizing","InpRiskPercentPerTrade","InpMaxRiskPercentPerTrade","risk_account_basis","InpMagicNumber","InpMaxSpreadPoints","InpMaxHoldingBars","max_holding_bars_ok","InpFridayLastEntryTime","InpFridayForcedFlatTime","account_trade_mode","is_demo_account","is_live_account","terminal_trade_allowed","expert_trade_allowed","session_instance_id");
}

void WriteRunConfigLog()
{
   bool write_header = false;
   const int handle = OpenLogForAppend(RUN_CONFIG_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteRunConfigHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),"initial_run_config_snapshot",CANDIDATE_ID,InpSymbol,TimeframeText(),BoolText(InpEnableOrderCheck),BoolText(InpEnableSendPreflight),BoolText(InpEnableOrderSend),BoolText(InpEnableIntegratedLifecycleWatch),BoolText(InpEnableIntegratedLifecycleClosePreflight),BoolText(InpEnableIntegratedLifecycleClose),InpFinalSendAcknowledgment,BoolText(InpFinalSendAcknowledgment == FINAL_SEND_ACK_TEXT),InpFinalLifecycleAcknowledgment,BoolText(IntegratedFinalLifecycleAckValid()),IntegerToString(InpMaxOrderSendAttempts),BoolText(InpMaxOrderSendAttempts == 1),IntegerToString(InpMaxLifecycleCloseAttempts),BoolText(InpMaxLifecycleCloseAttempts == 1),BoolText(InpRequireDemoAccount),BoolText(InpAllowLiveAccount),BoolText(InpLogCommonFiles),FormatNumber(InpVolumeLots),BoolText(InpUseRiskBasedSizing),FormatNumber(InpRiskPercentPerTrade),FormatNumber(InpMaxRiskPercentPerTrade),"ACCOUNT_EQUITY",SafeLongToString(InpMagicNumber),IntegerToString(InpMaxSpreadPoints),IntegerToString(InpMaxHoldingBars),BoolText(InpMaxHoldingBars == MAX_HOLDING_BARS),InpFridayLastEntryTime,InpFridayForcedFlatTime,IntegerToString((int)AccountInfoInteger(ACCOUNT_TRADE_MODE)),BoolText(IsDemoAccount()),BoolText(IsLiveAccount()),BoolText(TerminalTradeAllowed()),BoolText(ExpertTradeAllowed()),g_session_instance_id);
   FileClose(handle);
}

void WriteRunFinalSummaryHeader(const int handle)
{
   FileWrite(handle,"run_id","timestamp_server","candidate_id","order_send_called","total_order_send_attempt_count","execution_confirmed_count","rejected_count","uncertain_count","final_position_count","final_pending_order_count","final_broker_state","retry_performed","automatic_retry_allowed","max_order_send_attempts_per_attempt","note","lifecycle_close_called_count","lifecycle_close_confirmed_count","lifecycle_close_rejected_count","lifecycle_close_uncertain_count","lifecycle_close_skipped_already_closed_count","lifecycle_close_duplicate_blocked_count","lifecycle_close_time_exit_count","lifecycle_close_friday_forced_flat_count","lifecycle_close_unresolved_identity_blocked_count","manual_intervention_required_count","max_lifecycle_close_attempts_per_attempt","sizing_mode_fixed_count","sizing_mode_risk_based_count","sizing_risk_based_passed_count","sizing_fixed_volume_used_count","sizing_blocked_count","sizing_risk_percent_invalid_count","sizing_volume_below_min_lot_count","sizing_volume_above_max_lot_count","sizing_effective_risk_exceeds_policy_count","sizing_tick_value_unavailable_count","sizing_min_effective_risk_percent","sizing_max_effective_risk_percent","sizing_min_volume_lots","sizing_max_volume_lots","session_instance_id","deal_add_observed_count","deal_history_lookup_success_count","deal_history_lookup_unavailable_count","stop_loss_exit_observed_count","take_profit_exit_observed_count","other_exit_observed_count");
}

void WriteRunFinalSummaryLog(const string note)
{
   BrokerSnapshot final_snapshot = ReadBrokerSnapshot();
   bool write_header = false;
   const int handle = OpenLogForAppend(RUN_FINAL_SUMMARY_LOG, write_header);
   if(handle == INVALID_HANDLE) return;
   if(write_header) WriteRunFinalSummaryHeader(handle);
   FileWrite(handle,g_run_id,FormatTimeServer(TimeCurrent()),CANDIDATE_ID,BoolText(g_any_order_send_called),IntegerToString(g_total_order_send_attempt_count),IntegerToString(g_execution_confirmed_count),IntegerToString(g_rejected_count),IntegerToString(g_uncertain_count),IntegerToString(final_snapshot.position_count),IntegerToString(final_snapshot.pending_order_count),final_snapshot.broker_state,BoolText(g_retry_performed),BoolText(g_automatic_retry_allowed),IntegerToString(InpMaxOrderSendAttempts),note,IntegerToString(g_lifecycle_close_called_count),IntegerToString(g_lifecycle_close_confirmed_count),IntegerToString(g_lifecycle_close_rejected_count),IntegerToString(g_lifecycle_close_uncertain_count),IntegerToString(g_lifecycle_close_skipped_already_closed_count),IntegerToString(g_lifecycle_close_duplicate_blocked_count),IntegerToString(g_lifecycle_close_time_exit_count),IntegerToString(g_lifecycle_close_friday_forced_flat_count),IntegerToString(g_lifecycle_close_unresolved_identity_blocked_count),IntegerToString(g_manual_intervention_required_count),IntegerToString(InpMaxLifecycleCloseAttempts),IntegerToString(g_sizing_mode_fixed_count),IntegerToString(g_sizing_mode_risk_based_count),IntegerToString(g_sizing_risk_based_passed_count),IntegerToString(g_sizing_fixed_volume_used_count),IntegerToString(g_sizing_blocked_count),IntegerToString(g_sizing_risk_percent_invalid_count),IntegerToString(g_sizing_volume_below_min_lot_count),IntegerToString(g_sizing_volume_above_max_lot_count),IntegerToString(g_sizing_effective_risk_exceeds_policy_count),IntegerToString(g_sizing_tick_value_unavailable_count),g_sizing_effective_risk_seen ? FormatNumber(g_sizing_min_effective_risk_percent) : "",g_sizing_effective_risk_seen ? FormatNumber(g_sizing_max_effective_risk_percent) : "",g_sizing_volume_seen ? FormatNumber(g_sizing_min_volume_lots) : "",g_sizing_volume_seen ? FormatNumber(g_sizing_max_volume_lots) : "",g_session_instance_id,IntegerToString(g_deal_add_observed_count),IntegerToString(g_deal_history_lookup_success_count),IntegerToString(g_deal_history_lookup_unavailable_count),IntegerToString(g_stop_loss_exit_observed_count),IntegerToString(g_take_profit_exit_observed_count),IntegerToString(g_other_exit_observed_count));
   FileClose(handle);
}

void EnsureLogHeaders()
{
   bool write_header = false;
   int handle = OpenLogForAppend(RUN_CONFIG_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteRunConfigHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(ENTRY_SIGNAL_FRESHNESS_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteEntrySignalFreshnessHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(SIGNAL_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteSignalHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(DECISION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteDecisionHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(ORDER_CHECK_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteOrderCheckHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(SEND_PREFLIGHT_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteSendPreflightHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(ORDER_SEND_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteOrderSendHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(POSITION_SIZING_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WritePositionSizingHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(STATE_TRANSITION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteStateTransitionHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(POST_SEND_RECONCILIATION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WritePostSendReconciliationHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(RUN_FINAL_SUMMARY_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteRunFinalSummaryHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(TRADE_TRANSACTIONS_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteTradeTransactionsHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(RECONCILIATION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteReconciliationHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(POSITION_LIFECYCLE_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WritePositionLifecycleHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(INTEGRATED_LIFECYCLE_WATCH_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteIntegratedLifecycleWatchHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(INTEGRATED_LIFECYCLE_EXIT_DECISION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteIntegratedLifecycleExitDecisionHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(INTEGRATED_LIFECYCLE_RECONCILIATION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteIntegratedLifecycleReconciliationHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(INTEGRATED_LIFECYCLE_STATE_TRANSITION_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteIntegratedLifecycleStateTransitionHeader(handle); FileClose(handle); }
   handle = OpenLogForAppend(INTEGRATED_POSITION_CLOSE_LOG, write_header);
   if(handle != INVALID_HANDLE) { if(write_header) WriteIntegratedLifecycleCloseHeader(handle); FileClose(handle); }
}

void LogDuplicateBarSkipped(const datetime bar_time)
{
   WriteDecisionLog(bar_time,g_last_attempt_id,g_last_signal_id,false,IsDemoAccount(),!InpAllowLiveAccount && !IsLiveAccount(),SymbolAndInputOk(),TimeframeAndInputOk(),CurrentSpreadPoints() <= InpMaxSpreadPoints,CountPositionsForCandidate() == 0,CountPendingOrdersForCandidate() == 0,FridayEntryCutoffOk(bar_time),TerminalTradeAllowed() && SymbolTradeModeAllowsShort(),ExpertTradeAllowed(),true,true,"blocked","duplicate_bar_skipped");
}

void WriteFeatureUnavailableDecision(const datetime bar_time)
{
   WriteDecisionLog(bar_time,"","",false,IsDemoAccount(),!InpAllowLiveAccount && !IsLiveAccount(),SymbolAndInputOk(),TimeframeAndInputOk(),CurrentSpreadPoints() <= InpMaxSpreadPoints,CountPositionsForCandidate() == 0,CountPendingOrdersForCandidate() == 0,FridayEntryCutoffOk(bar_time),TerminalTradeAllowed() && SymbolTradeModeAllowsShort(),ExpertTradeAllowed(),false,false,"blocked","features_unavailable");
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
   BrokerSnapshot initial_snapshot = ReadBrokerSnapshot();
   WriteReconciliationLog(initial_snapshot);
   WritePositionLifecycleLog(snapshot.bar_time);

   if(!snapshot.signal_bool)
   {
      WriteDecisionLog(snapshot.bar_time,"","",false,IsDemoAccount(),!InpAllowLiveAccount && !IsLiveAccount(),SymbolAndInputOk(),TimeframeAndInputOk(),CurrentSpreadPoints() <= InpMaxSpreadPoints,initial_snapshot.position_count == 0,initial_snapshot.pending_order_count == 0,FridayEntryCutoffOk(snapshot.bar_time),TerminalTradeAllowed() && SymbolTradeModeAllowsShort(),ExpertTradeAllowed(),true,true,"no_signal","");
      return;
   }

   const string signal_id = SignalId(snapshot.bar_time);
   const string attempt_id = AttemptId(signal_id);
   g_last_signal_id = signal_id;
   g_last_attempt_id = attempt_id;
   WriteStateTransitionLog(attempt_id,signal_id,snapshot.bar_time,"signal_detected","signal_bool_true","signal_logic");

   const bool demo_account_ok = InpRequireDemoAccount && IsDemoAccount();
   const bool live_account_forbidden_ok = !InpAllowLiveAccount && !IsLiveAccount();
   const bool symbol_ok = SymbolAndInputOk();
   const bool timeframe_ok = TimeframeAndInputOk();
   const bool spread_ok = CurrentSpreadPoints() <= InpMaxSpreadPoints;
   const bool one_position_only_ok = initial_snapshot.position_count == 0;
   const bool pending_order_ok = initial_snapshot.pending_order_count == 0;
   const bool friday_entry_cutoff_ok = FridayEntryCutoffOk(snapshot.bar_time);
   const bool terminal_trade_ok = TerminalTradeAllowed();
   const bool symbol_trade_mode_ok = SymbolTradeModeAllowsShort();
   const bool trade_allowed_ok = terminal_trade_ok && symbol_trade_mode_ok;
   const bool expert_trade_allowed_ok = ExpertTradeAllowed();

   PositionSizingAudit sizing_audit;
   const bool sizing_ok = ComputePositionSizing(snapshot, attempt_id, signal_id, "order_check", sizing_audit);
   WritePositionSizingLog(sizing_audit);
   const bool volume_ok = sizing_ok;
   MqlTradeRequest request;
   RequestAudit request_audit = EmptyRequestAudit();
   AttachSizingAuditToRequestAudit(sizing_audit, request_audit);
   string request_block_reason = "";
   const bool sl_tp_ok = sizing_ok && BuildBrokerSafeCheckRequest(snapshot, sizing_audit, request, request_audit, request_block_reason);

   string block_reason = "";
   if(!InpRequireDemoAccount) block_reason = "demo_requirement_disabled";
   else if(!live_account_forbidden_ok) block_reason = "live_account_forbidden";
   else if(!demo_account_ok) block_reason = "demo_account_required";
   else if(!symbol_ok) block_reason = "symbol_not_locked";
   else if(!timeframe_ok) block_reason = "timeframe_not_locked";
   else if(!terminal_trade_ok) block_reason = "terminal_trade_disabled";
   else if(!expert_trade_allowed_ok) block_reason = "expert_trade_disabled";
   else if(!symbol_trade_mode_ok) block_reason = "symbol_trade_mode_block";
   else if(g_integrated_lifecycle_uncertain_hold) block_reason = "integrated_lifecycle_uncertainty_hold";
   else if(!spread_ok) block_reason = "current_spread_exceeded";
   else if(!one_position_only_ok) block_reason = "one_position_only_block";
   else if(!pending_order_ok) block_reason = "pending_order_block";
   else if(!friday_entry_cutoff_ok) block_reason = "friday_entry_cutoff_block";
   else if(!volume_ok) block_reason = sizing_audit.sizing_block_reason == "" ? "sizing_unavailable" : sizing_audit.sizing_block_reason;
   else if(!sl_tp_ok) block_reason = request_block_reason == "" ? "sl_tp_invalid" : request_block_reason;
   else if(g_last_order_check_bar_time == snapshot.bar_time) block_reason = "duplicate_order_check_block";
   else if(!InpEnableOrderCheck) block_reason = "order_check_required_before_send";

   if(block_reason != "")
   {
      WriteDecisionLog(snapshot.bar_time,attempt_id,signal_id,true,demo_account_ok,live_account_forbidden_ok,symbol_ok,timeframe_ok,spread_ok,one_position_only_ok,pending_order_ok,friday_entry_cutoff_ok,trade_allowed_ok,expert_trade_allowed_ok,volume_ok,sl_tp_ok,"blocked",block_reason,sizing_audit.sizing_mode,sizing_audit.sizing_status,sizing_audit.sizing_block_reason,sizing_audit.normalized_risk_volume_lots,sizing_audit.effective_risk_percent);
      MqlTradeCheckResult blank_result;
      ZeroMemory(blank_result);
      WriteOrderCheckLog(snapshot.bar_time,attempt_id,signal_id,request_audit,false,false,blank_result,block_reason);
      EvaluateSendPreflight(snapshot,attempt_id,signal_id,false,false,request_audit,block_reason);
      return;
   }

   g_last_order_check_bar_time = snapshot.bar_time;
   MqlTradeCheckResult check_result;
   ZeroMemory(check_result);
   const bool check_called = OrderCheck(request, check_result);
   const bool check_passed = check_called && check_result.retcode == 0;
   const string check_block_reason = check_called ? (check_passed ? "" : "order_check_failed") : "order_check_call_failed";
   WriteDecisionLog(snapshot.bar_time,attempt_id,signal_id,true,demo_account_ok,live_account_forbidden_ok,symbol_ok,timeframe_ok,spread_ok,one_position_only_ok,pending_order_ok,friday_entry_cutoff_ok,trade_allowed_ok,expert_trade_allowed_ok,volume_ok,sl_tp_ok,check_passed ? "order_check_passed" : "blocked",check_block_reason,sizing_audit.sizing_mode,sizing_audit.sizing_status,sizing_audit.sizing_block_reason,sizing_audit.normalized_risk_volume_lots,sizing_audit.effective_risk_percent);
   WriteOrderCheckLog(snapshot.bar_time,attempt_id,signal_id,request_audit,check_called,check_passed,check_result,check_block_reason);
   if(check_passed)
      WriteStateTransitionLog(attempt_id,signal_id,snapshot.bar_time,"order_check_passed","order_check_retcode_zero","order_check");
   EvaluateSendPreflight(snapshot,attempt_id,signal_id,check_called,check_passed,request_audit,check_block_reason);
}

bool ValidateChartAndInputs()
{
   if(InpAllowLiveAccount)
   {
      Print("Send preflight demo-only scaffold blocked: live account input must remain false.");
      return false;
   }
   if(InpMaxOrderSendAttempts != 1)
   {
      Print("Send preflight demo-only scaffold blocked: max attempts must equal 1.");
      return false;
   }
   if(InpSymbol != REQUIRED_SYMBOL || _Symbol != REQUIRED_SYMBOL)
   {
      Print("Send preflight demo-only scaffold blocked: symbol must be ", REQUIRED_SYMBOL);
      return false;
   }
   if(InpTimeframe != REQUIRED_TIMEFRAME || _Period != REQUIRED_TIMEFRAME)
   {
      Print("Send preflight demo-only scaffold blocked: timeframe must be M15.");
      return false;
   }
   return true;
}

void ResetEntrySignalFreshnessState()
{
   g_entry_signal_baseline_closed_bar_time = 0;
   g_entry_signal_baseline_established = false;
   g_entry_signal_first_valid_tick_observed = false;
   g_entry_signal_history_unavailable_logged = false;
   g_last_evaluated_bar_time = 0;
   g_last_duplicate_logged_bar_time = 0;
}

bool EstablishEntrySignalFreshnessBaseline(const datetime baseline_closed_bar_time,const string baseline_source)
{
   if(baseline_closed_bar_time <= 0) return false;
   g_entry_signal_baseline_closed_bar_time = baseline_closed_bar_time;
   g_entry_signal_baseline_established = true;
   g_last_evaluated_bar_time = baseline_closed_bar_time;
   g_last_duplicate_logged_bar_time = baseline_closed_bar_time;
   WriteEntrySignalFreshnessLog("initial_baseline_established",baseline_source,baseline_closed_bar_time,"entry_signal_freshness_blocked",false,"awaiting_new_closed_bar_after_baseline");
   return true;
}

void InitializeEntrySignalFreshnessBaseline()
{
   ResetEntrySignalFreshnessState();
   const datetime baseline_closed_bar_time = iTime(InpSymbol, InpTimeframe, 1);
   if(EstablishEntrySignalFreshnessBaseline(baseline_closed_bar_time,"on_init")) return;
   WriteEntrySignalFreshnessLog("initial_baseline_unavailable","on_init",0,"entry_signal_freshness_blocked",false,"closed_bar_history_unavailable");
   g_entry_signal_history_unavailable_logged = true;
}

bool EntrySignalFreshnessPassed(const datetime closed_bar_time)
{
   if(!g_entry_signal_baseline_established) return false;
   if(closed_bar_time <= g_entry_signal_baseline_closed_bar_time) return false;
   if(g_last_evaluated_bar_time > 0 && closed_bar_time <= g_last_evaluated_bar_time) return false;
   return true;
}

void OnDeinit(const int reason)
{
   WriteRunFinalSummaryLog("deinit_final_run_summary");
}

int OnInit()
{
   g_run_id = ResolveRunId();
   g_session_instance_id = BuildSessionInstanceId();
   EnsureLogFolder();
   if(InpOverwriteLogsOnInit)
      DeleteCurrentRunLogs();
   EnsureLogHeaders();
   WriteRunConfigLog();
   if(!ValidateChartAndInputs()) return INIT_PARAMETERS_INCORRECT;
   InitializeEntrySignalFreshnessBaseline();
   Print("Send preflight demo-only scaffold initialized: candidate=",CANDIDATE_ID," enable_order_check=",BoolText(InpEnableOrderCheck)," enable_send_preflight=",BoolText(InpEnableSendPreflight)," enable_transmission_input=",BoolText(InpEnableOrderSend)," require_demo=",BoolText(InpRequireDemoAccount)," allow_live=",BoolText(InpAllowLiveAccount)," run_id=",g_run_id," session_instance_id=",g_session_instance_id," log_folder=",LogFolder());
   return INIT_SUCCEEDED;
}

void OnTick()
{
   const datetime closed_bar_time = iTime(InpSymbol, InpTimeframe, 1);
   if(closed_bar_time <= 0)
   {
      if(!g_entry_signal_history_unavailable_logged)
      {
         WriteEntrySignalFreshnessLog("entry_history_unavailable","on_tick",0,"entry_signal_freshness_blocked",false,"closed_bar_history_unavailable");
         EvaluateIntegratedLifecycleWatch(0);
      }
      g_entry_signal_history_unavailable_logged = true;
      return;
   }
   g_entry_signal_history_unavailable_logged = false;

   if(!g_entry_signal_baseline_established)
   {
      EstablishEntrySignalFreshnessBaseline(closed_bar_time,"first_tick_safe_fallback");
      g_entry_signal_first_valid_tick_observed = true;
      WriteEntrySignalFreshnessLog("first_tick_historical_bar_skipped","first_tick_safe_fallback",closed_bar_time,"entry_signal_freshness_blocked",false,"first_available_closed_bar_became_baseline");
      if(IntegratedLifecycleEvaluationDue(closed_bar_time))
         EvaluateIntegratedLifecycleWatch(closed_bar_time);
      return;
   }

   const bool first_valid_tick = !g_entry_signal_first_valid_tick_observed;
   g_entry_signal_first_valid_tick_observed = true;
   if(!EntrySignalFreshnessPassed(closed_bar_time))
   {
      if(first_valid_tick || g_last_duplicate_logged_bar_time != closed_bar_time)
      {
         const string event_name = first_valid_tick ? "first_tick_historical_bar_skipped" : "closed_bar_already_observed";
         const string block_reason = first_valid_tick ? "closed_bar_not_after_initial_baseline" : "closed_bar_not_newer_than_last_observed";
         WriteEntrySignalFreshnessLog(event_name,"existing_instance_baseline",closed_bar_time,"entry_signal_freshness_blocked",false,block_reason);
         if(!first_valid_tick)
            LogDuplicateBarSkipped(closed_bar_time);
         g_last_duplicate_logged_bar_time = closed_bar_time;
      }
      if(IntegratedLifecycleEvaluationDue(closed_bar_time))
         EvaluateIntegratedLifecycleWatch(closed_bar_time);
      return;
   }

   WriteEntrySignalFreshnessLog("new_closed_bar_observed","existing_instance_baseline",closed_bar_time,"entry_signal_freshness_passed",true,"closed_bar_after_initial_baseline_and_last_observed");
   g_last_evaluated_bar_time = closed_bar_time;
   g_last_duplicate_logged_bar_time = 0;
   ProcessClosedBar(closed_bar_time);
   if(IntegratedLifecycleEvaluationDue(closed_bar_time))
      EvaluateIntegratedLifecycleWatch(closed_bar_time);
}

void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result)
{
   WriteTradeTransactionLog(trans,request,result);
}
