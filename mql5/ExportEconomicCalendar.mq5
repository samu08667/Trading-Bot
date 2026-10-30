//+------------------------------------------------------------------+
//|                                      ExportEconomicCalendar.mq5   |
//|  Exports MetaTrader 5 economic calendar values to CSV.            |
//+------------------------------------------------------------------+
#property copyright "Trading Bot"
#property version   "1.00"
#property strict
#property script_show_inputs

input string   InpCurrencies     = "EUR,USD,GBP,JPY,CHF,AUD,CAD,NZD";
input datetime InpDateFrom;
input datetime InpDateTo;
input string   InpFileName       = "economic_calendar.csv";
input int      InpMinImportance  = 0;

string NormalizeToken(string value)
{
   StringTrimLeft(value);
   StringTrimRight(value);
   StringToUpper(value);
   return value;
}

int ParseCurrencies(string source, string &currencies[])
{
   string parts[];
   int count = StringSplit(source, ',', parts);
   ArrayResize(currencies, 0);

   for(int i = 0; i < count; i++)
   {
      string token = NormalizeToken(parts[i]);
      if(token == "")
         continue;

      int size = ArraySize(currencies);
      ArrayResize(currencies, size + 1);
      currencies[size] = token;
   }

   return ArraySize(currencies);
}

bool CurrencyAllowed(const string currency, string &allowed_currencies[])
{
   if(ArraySize(allowed_currencies) == 0)
      return true;

   string normalized = NormalizeToken(currency);
   for(int i = 0; i < ArraySize(allowed_currencies); i++)
   {
      if(normalized == allowed_currencies[i])
         return true;
   }

   return false;
}

string CalendarLongToText(const long value)
{
   if(value == LONG_MIN)
      return "";

   return DoubleToString((double)value / 1000000.0, 6);
}

string DateTimeToText(const datetime value)
{
   if(value <= 0)
      return "";

   return TimeToString(value, TIME_DATE | TIME_SECONDS);
}

string DateTimeRangeToText(const datetime from_time, const datetime to_time)
{
   return DateTimeToText(from_time) + " -> " + DateTimeToText(to_time);
}

//+------------------------------------------------------------------+
//| Script program start function                                    |
//+------------------------------------------------------------------+
void OnStart()
{
   datetime from_time = InpDateFrom;
   datetime to_time = InpDateTo;

   if(from_time <= 0 || to_time <= 0 || to_time < from_time)
   {
      Print("Invalid export date range: ", DateTimeRangeToText(from_time, to_time));
      return;
   }

   string allowed_currencies[];
   ParseCurrencies(InpCurrencies, allowed_currencies);

   Print("Economic calendar export selected date range: ", DateTimeRangeToText(from_time, to_time));
   Print("Economic calendar export selected currencies: ", InpCurrencies);
   Print("Economic calendar export minimum importance: ", InpMinImportance);

   MqlCalendarValue values[];
   ResetLastError();
   int values_read = CalendarValueHistory(values, from_time, to_time);
   int count = ArraySize(values);

   if(values_read <= 0 || count <= 0)
   {
      Print(
         "CalendarValueHistory failed or returned no usable data. Range: ",
         DateTimeRangeToText(from_time, to_time),
         ". Error: ",
         GetLastError(),
         ". Function return: ",
         values_read,
         ". Values returned: ",
         count
      );
      return;
   }

   Print("Economic calendar values read: ", count);

   int file_handle = FileOpen(InpFileName, FILE_WRITE | FILE_CSV | FILE_ANSI, ';');
   if(file_handle == INVALID_HANDLE)
   {
      Print("Could not open output file: ", InpFileName, ". Error: ", GetLastError());
      return;
   }

   FileWrite(
      file_handle,
      "value_id",
      "event_id",
      "time_server",
      "currency",
      "event_name",
      "event_code",
      "importance",
      "impact_type",
      "actual",
      "forecast",
      "previous",
      "revised_previous",
      "period",
      "revision",
      "source"
   );

   int exported = 0;

   for(int i = 0; i < count; i++)
   {
      MqlCalendarEvent event;
      MqlCalendarCountry country;

      string currency = "";
      string event_name = "";
      string event_code = "";
      int importance = 0;

      ResetLastError();
      if(CalendarEventById(values[i].event_id, event))
      {
         event_name = event.name;
         event_code = event.event_code;
         importance = (int)event.importance;

         if(CalendarCountryById(event.country_id, country))
            currency = country.currency;
      }
      else
      {
         Print(
            "CalendarEventById failed. Event ID: ",
            values[i].event_id,
            ". Value ID: ",
            values[i].id,
            ". Error: ",
            GetLastError()
         );
         continue;
      }

      if(!CurrencyAllowed(currency, allowed_currencies))
         continue;

      if(importance < InpMinImportance)
         continue;

      FileWrite(
         file_handle,
         IntegerToString((long)values[i].id),
         IntegerToString((long)values[i].event_id),
         DateTimeToText(values[i].time),
         currency,
         event_name,
         event_code,
         IntegerToString(importance),
         IntegerToString((int)values[i].impact_type),
         CalendarLongToText(values[i].actual_value),
         CalendarLongToText(values[i].forecast_value),
         CalendarLongToText(values[i].prev_value),
         CalendarLongToText(values[i].revised_prev_value),
         DateTimeToText(values[i].period),
         IntegerToString((int)values[i].revision),
         "MT5"
      );

      exported++;
   }

   FileClose(file_handle);

   Print("Economic calendar export complete.");
   Print("Output file: ", InpFileName, " in the MetaTrader 5 MQL5/Files sandbox.");
   Print("Exported records: ", exported);
}
