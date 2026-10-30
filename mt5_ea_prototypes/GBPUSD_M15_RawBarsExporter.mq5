#property strict
#property version   "0.1"
#property description "Raw GBPUSD M15 closed-bar CSV exporter for parity work."
#property description "No signal calculation, no broker operations, no retry."

input string InpOutputCsv = "gbpusd_m15_mt5_raw_bars.csv";
input datetime InpOutputStartTime = D'2026.06.17 01:15:00';
input datetime InpOutputEndTime = D'2026.06.29 22:45:00';
input int InpMaxOutputRows = 0;

const string REQUIRED_SYMBOL = "GBPUSD";
const ENUM_TIMEFRAMES REQUIRED_TIMEFRAME = PERIOD_M15;

int g_file_handle = INVALID_HANDLE;
bool g_export_performed = false;

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
   if(total_bars <= 0)
      return false;

   const int copied = CopyRates(REQUIRED_SYMBOL, REQUIRED_TIMEFRAME, 0, total_bars, rates);
   if(copied <= 0)
      return false;

   ArraySetAsSeries(rates, false);
   if(ArraySize(rates) >= 2 && rates[0].time > rates[ArraySize(rates) - 1].time)
      ReverseRates(rates);

   return ArraySize(rates) > 0;
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
      "spread"
   );
}

void WriteRawRow(MqlRates &rates[], const int index)
{
   FileWrite(
      g_file_handle,
      FormatTimeServer(rates[index].time),
      FormatNumber(rates[index].open),
      FormatNumber(rates[index].high),
      FormatNumber(rates[index].low),
      FormatNumber(rates[index].close),
      IntegerToString(rates[index].tick_volume),
      IntegerToString(rates[index].spread)
   );
}

bool ExportRawBarsCsv()
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
      "Raw bars export diagnostics: output_start=",
      FormatTimeServer(InpOutputStartTime),
      " output_end=",
      FormatTimeServer(InpOutputEndTime),
      " rows_exported=",
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
         Print("Raw bars export warning: unable to delete existing output file: ", InpOutputCsv);
         return false;
      }
   }

   g_file_handle = FileOpen(InpOutputCsv, FILE_WRITE | FILE_CSV | FILE_ANSI, ',');
   if(g_file_handle == INVALID_HANDLE)
   {
      Print("Unable to open raw bars CSV: ", InpOutputCsv);
      return false;
   }

   WriteHeader();
   int rows_written = 0;
   for(int output_pos = 0; output_pos < ArraySize(output_indices); output_pos++)
   {
      WriteRawRow(rates, output_indices[output_pos]);
      rows_written++;
   }

   FileFlush(g_file_handle);
   FileClose(g_file_handle);
   g_file_handle = INVALID_HANDLE;

   Print("Raw bars export complete: rows_written=", rows_written, " output_file=", InpOutputCsv);
   return rows_written == ArraySize(output_indices);
}

bool ValidateChart()
{
   if(_Symbol != REQUIRED_SYMBOL)
   {
      Print("Raw bars exporter blocked: chart symbol must be ", REQUIRED_SYMBOL);
      return false;
   }
   if(_Period != REQUIRED_TIMEFRAME)
   {
      Print("Raw bars exporter blocked: chart timeframe must be M15.");
      return false;
   }
   return true;
}

int OnInit()
{
   if(!ValidateChart())
      return INIT_PARAMETERS_INCORRECT;
   return INIT_SUCCEEDED;
}

void OnTick()
{
   // Intentionally empty. This exporter writes closed historical bars on teardown.
}

void OnDeinit(const int reason)
{
   if(!ExportRawBarsCsv())
      Print("Raw bars export failed or produced no rows.");
}
