#property strict
#property version   "0.2"
#property description "Signal-only parity prototype for gbpusd_short_h10_1_5_off_hours."
#property description "No broker execution, no position mutation, no retry."

input string InpOutputCsv = "gbpusd_short_h10_1_5_off_hours_mql5_signal_only.csv";
input datetime InpOutputStartTime = D'2026.06.17 01:15:00';
input datetime InpOutputEndTime = D'2026.06.29 22:45:00';
input int InpMaxOutputRows = 500;

const string REQUIRED_SYMBOL = "GBPUSD";
const ENUM_TIMEFRAMES REQUIRED_TIMEFRAME = PERIOD_M15;
const int ATR_PERIOD = 20;
const int MA_FAST_PERIOD = 20;
const int TICK_VOLUME_PERCENTILE_WINDOW = 100;
const int MAX_HOLDING_BARS = 10;
const int M15_SECONDS = 15 * 60;
const bool NO_WEEKEND_HOLD = true;
const bool FORCED_FRIDAY_EXIT_ENABLED = true;
const int FRIDAY_DAY_OF_WEEK = 5;
const int FRIDAY_LAST_ENTRY_HOUR = 23;
const int FRIDAY_LAST_ENTRY_MINUTE = 15;
const int FRIDAY_FORCED_FLAT_HOUR = 23;
const int FRIDAY_FORCED_FLAT_MINUTE = 45;
const double MAX_SPREAD_POINTS = 15.0;
const double CLOSE_TO_MA_LOW_MID = -0.4303672057741361;
const double CLOSE_TO_MA_MID_HIGH = 0.5954421525644814;
const double TICK_VOLUME_LOW_MID = 0.14;
const double TICK_VOLUME_MID_HIGH = 0.37;
const double SL_ATR_MULTIPLIER = 1.0;
const double TP_ATR_MULTIPLIER = 1.5;

int g_file_handle = INVALID_HANDLE;
bool g_export_performed = false;

string BoolText(const bool value)
{
   return value ? "true" : "false";
}

string FormatNumber(const double value)
{
   return DoubleToString(value, 12);
}

string FormatTimeServer(const datetime value)
{
   if(value <= 0)
      return "";

   string text = TimeToString(value, TIME_DATE | TIME_SECONDS);
   StringReplace(text, ".", "-");
   return text;
}

string HourSession(const datetime server_time)
{
   MqlDateTime parts;
   TimeToStruct(server_time, parts);
   if(parts.hour >= 0 && parts.hour <= 7)
      return "Asia";
   if(parts.hour >= 8 && parts.hour <= 13)
      return "London";
   if(parts.hour >= 14 && parts.hour <= 21)
      return "New_York";
   return "Off_hours";
}

string BucketForValue(
   const double value,
   const double low_mid_cutoff,
   const double mid_high_cutoff
)
{
   if(value <= low_mid_cutoff)
      return "low_tercile";
   if(value <= mid_high_cutoff)
      return "mid_tercile";
   return "high_tercile";
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

bool LoadRatesOldestToNewest(MqlRates &rates[])
{
   const int total_bars = Bars(REQUIRED_SYMBOL, REQUIRED_TIMEFRAME);
   if(total_bars <= TICK_VOLUME_PERCENTILE_WINDOW)
      return false;

   const int copied = CopyRates(REQUIRED_SYMBOL, REQUIRED_TIMEFRAME, 0, total_bars, rates);
   if(copied <= TICK_VOLUME_PERCENTILE_WINDOW)
      return false;

   ArraySetAsSeries(rates, false);
   if(ArraySize(rates) >= 2 && rates[0].time > rates[ArraySize(rates) - 1].time)
      ReverseRates(rates);

   return ArraySize(rates) > TICK_VOLUME_PERCENTILE_WINDOW;
}

bool TrueRangeAtIndex(MqlRates &rates[], const int index, double &true_range)
{
   if(index <= 0 || index >= ArraySize(rates))
      return false;

   const double previous_close = rates[index - 1].close;
   const double high_low = rates[index].high - rates[index].low;
   const double high_previous_close = MathAbs(rates[index].high - previous_close);
   const double low_previous_close = MathAbs(rates[index].low - previous_close);
   true_range = MathMax(high_low, MathMax(high_previous_close, low_previous_close));
   return true;
}

bool Atr20AtIndex(MqlRates &rates[], const int index, double &atr_value)
{
   if(index < ATR_PERIOD)
      return false;

   double sum = 0.0;
   for(int offset = 0; offset < ATR_PERIOD; offset++)
   {
      double true_range = 0.0;
      if(!TrueRangeAtIndex(rates, index - offset, true_range))
         return false;
      sum += true_range;
   }
   atr_value = sum / ATR_PERIOD;
   return true;
}

bool MaFastAtIndex(MqlRates &rates[], const int index, double &ma_value)
{
   if(index < MA_FAST_PERIOD - 1)
      return false;

   double sum = 0.0;
   for(int offset = 0; offset < MA_FAST_PERIOD; offset++)
      sum += rates[index - offset].close;

   ma_value = sum / MA_FAST_PERIOD;
   return true;
}

bool TickVolumePercentile100AtIndex(MqlRates &rates[], const int index, double &percentile)
{
   if(index < TICK_VOLUME_PERCENTILE_WINDOW - 1)
      return false;

   const long current_tick_volume = rates[index].tick_volume;
   int inclusive_count = 0;
   for(int offset = 0; offset < TICK_VOLUME_PERCENTILE_WINDOW; offset++)
   {
      if(rates[index - offset].tick_volume <= current_tick_volume)
         inclusive_count++;
   }

   percentile = (double)inclusive_count / (double)TICK_VOLUME_PERCENTILE_WINDOW;
   return true;
}

bool FeaturesAvailableAtIndex(MqlRates &rates[], const int index)
{
   if(index < TICK_VOLUME_PERCENTILE_WINDOW - 1)
      return false;
   if(index < ATR_PERIOD)
      return false;
   if(index < MA_FAST_PERIOD - 1)
      return false;
   if(index >= ArraySize(rates))
      return false;
   return true;
}

datetime SameDayTime(const datetime timestamp, const int hour, const int minute)
{
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

bool LifecycleEntryAllowedByBarOpenTime(const datetime timestamp)
{
   if(!NO_WEEKEND_HOLD)
      return true;
   if(!IsFriday(timestamp))
      return true;

   const datetime last_entry_time = SameDayTime(
      timestamp,
      FRIDAY_LAST_ENTRY_HOUR,
      FRIDAY_LAST_ENTRY_MINUTE
   );
   return timestamp <= last_entry_time;
}

bool ExportedRateTimeExists(
   MqlRates &rates[],
   int &output_indices[],
   const int start_output_pos,
   const datetime target_time
)
{
   for(int output_pos = start_output_pos; output_pos < ArraySize(output_indices); output_pos++)
   {
      const int index = output_indices[output_pos];
      if(index < 0 || index >= ArraySize(rates))
         continue;

      const datetime exported_time = rates[index].time;
      if(exported_time == target_time)
         return true;
      if(exported_time > target_time)
         return false;
   }
   return false;
}

datetime TenthFutureM15TimeIfAvailable(
   MqlRates &rates[],
   int &output_indices[],
   const int output_pos
)
{
   if(output_pos < 0 || output_pos >= ArraySize(output_indices))
      return 0;

   const int index = output_indices[output_pos];
   if(index < 0 || index >= ArraySize(rates))
      return 0;

   const datetime target_time = (datetime)((long)rates[index].time + MAX_HOLDING_BARS * M15_SECONDS);
   if(ExportedRateTimeExists(rates, output_indices, output_pos + 1, target_time))
      return target_time;
   return 0;
}

datetime FridayForcedFlatTimeIfApplicable(const datetime timestamp)
{
   if(!NO_WEEKEND_HOLD || !FORCED_FRIDAY_EXIT_ENABLED)
      return 0;
   if(!IsFriday(timestamp))
      return 0;

   const datetime forced_flat_time = SameDayTime(
      timestamp,
      FRIDAY_FORCED_FLAT_HOUR,
      FRIDAY_FORCED_FLAT_MINUTE
   );
   if(timestamp <= forced_flat_time)
      return forced_flat_time;
   return 0;
}

bool IsWithinOutputRange(const datetime bar_time)
{
   if(InpOutputStartTime > 0 && bar_time < InpOutputStartTime)
      return false;
   if(InpOutputEndTime > 0 && bar_time > InpOutputEndTime)
      return false;
   return true;
}

void AppendIndex(int &indices[], const int value)
{
   const int size = ArraySize(indices);
   ArrayResize(indices, size + 1);
   indices[size] = value;
}

void BuildOutputIndices(MqlRates &rates[], int &output_indices[], int &duplicate_times_skipped)
{
   ArrayResize(output_indices, 0);
   duplicate_times_skipped = 0;
   const datetime current_bar_time = iTime(REQUIRED_SYMBOL, REQUIRED_TIMEFRAME, 0);
   datetime last_selected_time = 0;

   for(int index = 0; index < ArraySize(rates); index++)
   {
      const datetime bar_time = rates[index].time;
      if(current_bar_time > 0 && bar_time >= current_bar_time)
         continue;
      if(!IsWithinOutputRange(bar_time))
         continue;
      if(!FeaturesAvailableAtIndex(rates, index))
         continue;
      if(bar_time == last_selected_time)
      {
         duplicate_times_skipped++;
         continue;
      }
      AppendIndex(output_indices, index);
      last_selected_time = bar_time;
   }

   if(InpMaxOutputRows > 0 && ArraySize(output_indices) > InpMaxOutputRows)
      ArrayResize(output_indices, InpMaxOutputRows);
}

string MaxExitTimeServerForOutputIndex(
   MqlRates &rates[],
   int &output_indices[],
   const int output_pos
)
{
   if(output_pos < 0 || output_pos >= ArraySize(output_indices))
      return "";

   const int index = output_indices[output_pos];
   if(index < 0 || index >= ArraySize(rates))
      return "";

   datetime selected_exit_time = 0;
   const datetime tenth_future_time = TenthFutureM15TimeIfAvailable(rates, output_indices, output_pos);
   if(tenth_future_time > 0)
      selected_exit_time = tenth_future_time;

   const datetime forced_flat_time = FridayForcedFlatTimeIfApplicable(rates[index].time);
   if(forced_flat_time > 0 && (selected_exit_time == 0 || forced_flat_time < selected_exit_time))
      selected_exit_time = forced_flat_time;

   return FormatTimeServer(selected_exit_time);
}

void WriteHeader()
{
   FileWrite(
      g_file_handle,
      "time_server",
      "open",
      "high",
      "low",
      "close",
      "tick_volume",
      "spread",
      "atr_20",
      "ma_fast",
      "close_to_ma_fast_atr_20",
      "tick_volume_percentile_100",
      "hour_session",
      "close_to_ma_fast_atr_20_bucket",
      "tick_volume_percentile_100_bucket",
      "signal_bool",
      "entry_reference_price",
      "sl_price_preview",
      "tp_price_preview",
      "max_holding_bars",
      "max_exit_time_server"
   );
}

bool WriteSignalRow(
   MqlRates &rates[],
   int &output_indices[],
   const int output_pos
)
{
   const int index = output_indices[output_pos];
   double atr_20 = 0.0;
   double ma_fast = 0.0;
   double tick_volume_percentile_100 = 0.0;
   if(!Atr20AtIndex(rates, index, atr_20))
      return false;
   if(!MaFastAtIndex(rates, index, ma_fast))
      return false;
   if(!TickVolumePercentile100AtIndex(rates, index, tick_volume_percentile_100))
      return false;
   if(atr_20 <= 0.0 || rates[index].close <= 0.0)
      return false;

   const double close_to_ma_fast_atr_20 = (rates[index].close - ma_fast) / atr_20;
   const string hour_session = HourSession(rates[index].time);
   const string close_bucket = BucketForValue(
      close_to_ma_fast_atr_20,
      CLOSE_TO_MA_LOW_MID,
      CLOSE_TO_MA_MID_HIGH
   );
   const string volume_bucket = BucketForValue(
      tick_volume_percentile_100,
      TICK_VOLUME_LOW_MID,
      TICK_VOLUME_MID_HIGH
   );
   const double spread_points = (double)rates[index].spread;
   const bool signal_bool = (
      hour_session == "Off_hours" &&
      close_bucket == "high_tercile" &&
      volume_bucket == "mid_tercile" &&
      spread_points <= MAX_SPREAD_POINTS &&
      rates[index].close > 0.0 &&
      atr_20 > 0.0
   );

   string entry_reference_price = "";
   string sl_price_preview = "";
   string tp_price_preview = "";
   if(signal_bool)
   {
      entry_reference_price = FormatNumber(rates[index].close);
      sl_price_preview = FormatNumber(rates[index].close + SL_ATR_MULTIPLIER * atr_20);
      tp_price_preview = FormatNumber(rates[index].close - TP_ATR_MULTIPLIER * atr_20);
   }

   FileWrite(
      g_file_handle,
      FormatTimeServer(rates[index].time),
      FormatNumber(rates[index].open),
      FormatNumber(rates[index].high),
      FormatNumber(rates[index].low),
      FormatNumber(rates[index].close),
      IntegerToString(rates[index].tick_volume),
      IntegerToString(rates[index].spread),
      FormatNumber(atr_20),
      FormatNumber(ma_fast),
      FormatNumber(close_to_ma_fast_atr_20),
      FormatNumber(tick_volume_percentile_100),
      hour_session,
      close_bucket,
      volume_bucket,
      BoolText(signal_bool),
      entry_reference_price,
      sl_price_preview,
      tp_price_preview,
      IntegerToString(MAX_HOLDING_BARS),
      MaxExitTimeServerForOutputIndex(rates, output_indices, output_pos)
   );
   return true;
}

bool ExportSignalOnlyParityCsv()
{
   if(g_export_performed)
      return true;
   g_export_performed = true;

   MqlRates rates[];
   if(!LoadRatesOldestToNewest(rates))
      return false;

   int output_indices[];
   int duplicate_times_skipped = 0;
   BuildOutputIndices(rates, output_indices, duplicate_times_skipped);
   Print(
      "Signal-only parity export diagnostics: output_start=",
      FormatTimeServer(InpOutputStartTime),
      " output_end=",
      FormatTimeServer(InpOutputEndTime),
      " rows_selected=",
      ArraySize(output_indices),
      " duplicate_times_skipped=",
      duplicate_times_skipped,
      " output_file=",
      InpOutputCsv
   );

   if(ArraySize(output_indices) <= 0)
      return false;

   if(FileIsExist(InpOutputCsv))
   {
      if(!FileDelete(InpOutputCsv))
      {
         Print("Signal-only parity export warning: unable to delete existing output file: ", InpOutputCsv);
         return false;
      }
   }

   g_file_handle = FileOpen(InpOutputCsv, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(g_file_handle == INVALID_HANDLE)
   {
      Print("Unable to open signal-only parity CSV: ", InpOutputCsv);
      return false;
   }

   WriteHeader();

   int rows_written = 0;
   for(int output_pos = 0; output_pos < ArraySize(output_indices); output_pos++)
   {
      if(WriteSignalRow(rates, output_indices, output_pos))
         rows_written++;
   }

   FileFlush(g_file_handle);
   FileClose(g_file_handle);
   g_file_handle = INVALID_HANDLE;

   Print("Signal-only parity export complete: rows_written=", rows_written, " output_file=", InpOutputCsv);
   return rows_written == ArraySize(output_indices);
}

bool ValidateChart()
{
   if(_Symbol != REQUIRED_SYMBOL)
   {
      Print("Signal-only prototype blocked: chart symbol must be ", REQUIRED_SYMBOL);
      return false;
   }
   if(_Period != REQUIRED_TIMEFRAME)
   {
      Print("Signal-only prototype blocked: chart timeframe must be M15.");
      return false;
   }
   return true;
}

int OnInit()
{
   if(!ValidateChart())
      return INIT_PARAMETERS_INCORRECT;

   // Future execution-capable EA only:
   // - enforce one-position-only and ignore later signals while a position is open;
   // - track the entry bar and time-exit after 10 closed M15 bars;
   // - reject new Friday entries after 23:15 server time;
   // - force Friday flat by 23:45 server time if still open;
   // - add broker preflight and broker transmission only after separate review.
   Print(
      "Signal-only lifecycle metadata: no_weekend_hold=",
      BoolText(NO_WEEKEND_HOLD),
      " friday_last_entry=23:15",
      " friday_forced_flat=23:45",
      " bar_time_basis=MqlRates.time_open"
   );
   return INIT_SUCCEEDED;
}

void OnTick()
{
   // Intentionally empty. This prototype exports signal parity data on teardown
   // from a closed-bar historical buffer and never performs trade operations.
}

void OnDeinit(const int reason)
{
   if(!ExportSignalOnlyParityCsv())
      Print("Signal-only parity export failed or produced no rows.");
}
