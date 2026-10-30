from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest


EA_PATH = Path("mt5_ea_prototypes/GBPUSD_FixedCandidate_OrderSendDemoOnly.mq5")
CURRENT_PATCH_A_DOCS = [
    Path("README.md"),
    Path("docs/research/PROJECT_STATE.md"),
    Path("docs/demo_live_smoke_runbook.md"),
]


@dataclass(frozen=True)
class HistoryGetterContract:
    property_id: str
    helper: str
    getter_destination: str
    observation_variable: str
    validity_flag: str
    csv_column: str
    csv_expression: str


HISTORY_GETTER_CONTRACT = (
    HistoryGetterContract(
        "DEAL_TICKET",
        "ReadHistoryDealInteger",
        "history_deal_ticket",
        "deal_ticket",
        "deal_ticket_valid",
        "deal_ticket",
        'deal_observation.deal_ticket_valid ? SafeLongToString((long)deal_observation.deal_ticket) : ""',
    ),
    HistoryGetterContract(
        "DEAL_ORDER",
        "ReadHistoryDealInteger",
        "history_order_ticket",
        "order_ticket",
        "order_ticket_valid",
        "order_ticket",
        'deal_observation.order_ticket_valid ? SafeLongToString((long)deal_observation.order_ticket) : ""',
    ),
    HistoryGetterContract(
        "DEAL_POSITION_ID",
        "ReadHistoryDealInteger",
        "observation.deal_position_id",
        "deal_position_id",
        "deal_position_id_valid",
        "deal_position_id",
        'deal_observation.deal_position_id_valid ? SafeLongToString(deal_observation.deal_position_id) : ""',
    ),
    HistoryGetterContract(
        "DEAL_MAGIC",
        "ReadHistoryDealInteger",
        "observation.magic",
        "magic",
        "magic_valid",
        "deal_magic",
        'deal_observation.magic_valid ? SafeLongToString(deal_observation.magic) : ""',
    ),
    HistoryGetterContract(
        "DEAL_TIME",
        "ReadHistoryDealInteger",
        "observation.deal_time",
        "deal_time",
        "deal_time_valid",
        "deal_time",
        'deal_observation.deal_time_valid ? FormatTimeServer((datetime)deal_observation.deal_time) : ""',
    ),
    HistoryGetterContract(
        "DEAL_TIME_MSC",
        "ReadHistoryDealInteger",
        "observation.deal_time_msc",
        "deal_time_msc",
        "deal_time_msc_valid",
        "deal_time_msc",
        'deal_observation.deal_time_msc_valid ? SafeLongToString(deal_observation.deal_time_msc) : ""',
    ),
    HistoryGetterContract(
        "DEAL_TYPE",
        "ReadHistoryDealInteger",
        "observation.deal_type_raw",
        "deal_type_raw",
        "deal_type_valid",
        "deal_type_raw",
        'deal_observation.deal_type_valid ? SafeLongToString(deal_observation.deal_type_raw) : ""',
    ),
    HistoryGetterContract(
        "DEAL_ENTRY",
        "ReadHistoryDealInteger",
        "observation.deal_entry_raw",
        "deal_entry_raw",
        "deal_entry_valid",
        "deal_entry_raw",
        'deal_observation.deal_entry_valid ? SafeLongToString(deal_observation.deal_entry_raw) : ""',
    ),
    HistoryGetterContract(
        "DEAL_REASON",
        "ReadHistoryDealInteger",
        "observation.deal_reason_raw",
        "deal_reason_raw",
        "deal_reason_valid",
        "deal_reason_raw",
        'deal_observation.deal_reason_valid ? SafeLongToString(deal_observation.deal_reason_raw) : ""',
    ),
    HistoryGetterContract(
        "DEAL_PRICE",
        "ReadHistoryDealDouble",
        "observation.deal_price",
        "deal_price",
        "deal_price_valid",
        "deal_price",
        'deal_observation.deal_price_valid ? FormatNumber(deal_observation.deal_price) : ""',
    ),
    HistoryGetterContract(
        "DEAL_VOLUME",
        "ReadHistoryDealDouble",
        "observation.deal_volume",
        "deal_volume",
        "deal_volume_valid",
        "deal_volume",
        'deal_observation.deal_volume_valid ? FormatNumber(deal_observation.deal_volume) : ""',
    ),
    HistoryGetterContract(
        "DEAL_PROFIT",
        "ReadHistoryDealDouble",
        "observation.deal_profit",
        "deal_profit",
        "deal_profit_valid",
        "deal_profit",
        'deal_observation.deal_profit_valid ? FormatNumber(deal_observation.deal_profit) : ""',
    ),
    HistoryGetterContract(
        "DEAL_COMMISSION",
        "ReadHistoryDealDouble",
        "observation.deal_commission",
        "deal_commission",
        "deal_commission_valid",
        "deal_commission",
        'deal_observation.deal_commission_valid ? FormatNumber(deal_observation.deal_commission) : ""',
    ),
    HistoryGetterContract(
        "DEAL_SWAP",
        "ReadHistoryDealDouble",
        "observation.deal_swap",
        "deal_swap",
        "deal_swap_valid",
        "deal_swap",
        'deal_observation.deal_swap_valid ? FormatNumber(deal_observation.deal_swap) : ""',
    ),
    HistoryGetterContract(
        "DEAL_FEE",
        "ReadHistoryDealDouble",
        "observation.deal_fee",
        "deal_fee",
        "deal_fee_valid",
        "deal_fee",
        'deal_observation.deal_fee_valid ? FormatNumber(deal_observation.deal_fee) : ""',
    ),
    HistoryGetterContract(
        "DEAL_SYMBOL",
        "ReadHistoryDealString",
        "observation.symbol",
        "symbol",
        "symbol_valid",
        "deal_symbol",
        'deal_observation.symbol_valid ? CsvEscape(deal_observation.symbol) : ""',
    ),
    HistoryGetterContract(
        "DEAL_COMMENT",
        "ReadHistoryDealString",
        "observation.deal_comment",
        "deal_comment",
        "deal_comment_valid",
        "deal_comment",
        'deal_observation.deal_comment_valid ? CsvEscape(deal_observation.deal_comment) : ""',
    ),
    HistoryGetterContract(
        "DEAL_EXTERNAL_ID",
        "ReadHistoryDealString",
        "observation.deal_external_id",
        "deal_external_id",
        "deal_external_id_valid",
        "deal_external_id",
        'deal_observation.deal_external_id_valid ? CsvEscape(deal_observation.deal_external_id) : ""',
    ),
)


def read_ea() -> str:
    return EA_PATH.read_text(encoding="utf-8")


def function_body(source: str, function_name: str) -> str:
    signature = source.index(f"{function_name}(")
    open_brace = source.index("{", signature)
    depth = 0
    for index in range(open_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace + 1 : index]
    raise AssertionError(f"Unterminated MQL5 function: {function_name}")


def normalize_mql(text: str) -> str:
    return " ".join(text.split())


def replace_function_body(source: str, function_name: str, replacement: str) -> str:
    original = function_body(source, function_name)
    assert source.count(original) == 1, f"Function body is not unique: {function_name}"
    return source.replace(original, replacement, 1)


def swap_once(text: str, left: str, right: str) -> str:
    assert text.count(left) == 1, f"Mutation target must occur once: {left}"
    assert text.count(right) == 1, f"Mutation target must occur once: {right}"
    placeholder = "__PATCH_A_MUTATION_SWAP_PLACEHOLDER__"
    assert placeholder not in text
    return text.replace(left, placeholder, 1).replace(right, left, 1).replace(
        placeholder, right, 1
    )


def mutate_function_swap(
    source: str, function_name: str, left: str, right: str
) -> str:
    body = function_body(source, function_name)
    return replace_function_body(source, function_name, swap_once(body, left, right))


def split_top_level_arguments(call_text: str) -> list[str]:
    arguments: list[str] = []
    start = 0
    depth = 0
    in_string = False
    for index, char in enumerate(call_text):
        if char == '"' and (index == 0 or call_text[index - 1] != chr(92)):
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                arguments.append(call_text[start:index].strip())
                start = index + 1
    arguments.append(call_text[start:].strip())
    return arguments


def file_write_arguments(source: str, function_name: str) -> list[str]:
    body = function_body(source, function_name)
    marker = "FileWrite("
    call_start = body.index(marker) + len(marker)
    depth = 0
    in_string = False
    for index in range(call_start, len(body)):
        char = body[index]
        if char == '"' and body[index - 1] != chr(92):
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    return split_top_level_arguments(body[call_start:index])
                depth -= 1
    raise AssertionError(f"FileWrite call not terminated in {function_name}")


def header_names(source: str, function_name: str) -> list[str]:
    return [argument.strip('"') for argument in file_write_arguments(source, function_name)[1:]]


def record_by_header(
    source: str, header_function: str, record_function: str
) -> dict[str, str]:
    headers = header_names(source, header_function)
    record = file_write_arguments(source, record_function)[1:]
    assert len(headers) == len(record)
    return dict(zip(headers, record, strict=True))


def extract_history_getter_mapping(source: str) -> dict[str, dict[str, str]]:
    build = function_body(source, "BuildDealHistoryObservation")
    pattern = re.compile(
        r"observation[.](?P<validity_flag>\w+)\s*=\s*"
        r"(?P<helper>ReadHistoryDeal(?:Integer|Double|String))\s*[(]\s*"
        r"trans[.]deal\s*,\s*(?P<property_id>DEAL_[A-Z0-9_]+)\s*,\s*"
        r'"(?P<field_name>DEAL_[A-Z0-9_]+)"\s*,\s*'
        r"(?P<getter_destination>[A-Za-z_][A-Za-z0-9_.]*)\s*,\s*"
        r"observation\s*[)]\s*;"
    )
    mapping: dict[str, dict[str, str]] = {}
    for match in pattern.finditer(build):
        property_id = match.group("property_id")
        assert property_id not in mapping, f"Duplicate getter property: {property_id}"
        mapping[property_id] = match.groupdict()
    return mapping


def validate_history_getter_mapping(source: str) -> None:
    mapping = extract_history_getter_mapping(source)
    expected_properties = {item.property_id for item in HISTORY_GETTER_CONTRACT}
    assert set(mapping) == expected_properties, (
        "History getter property set mismatch: "
        f"missing={sorted(expected_properties - set(mapping))}, "
        f"unexpected={sorted(set(mapping) - expected_properties)}"
    )
    normalized_build = normalize_mql(
        function_body(source, "BuildDealHistoryObservation")
    )
    for item in HISTORY_GETTER_CONTRACT:
        actual = mapping[item.property_id]
        for key, expected in [
            ("helper", item.helper),
            ("field_name", item.property_id),
            ("getter_destination", item.getter_destination),
            ("validity_flag", item.validity_flag),
        ]:
            assert actual[key] == expected, (
                f"{item.property_id}: {key} expected {expected}, got {actual[key]}"
            )
        direct_destination = f"observation.{item.observation_variable}"
        if item.getter_destination == direct_destination:
            continue
        assignment = normalize_mql(
            f"""
            if(observation.{item.validity_flag})
               observation.{item.observation_variable} =
                  (ulong){item.getter_destination};
            """
        )
        assert assignment in normalized_build, (
            f"{item.property_id}: getter destination is not copied to "
            f"observation.{item.observation_variable} under {item.validity_flag}"
        )


def validate_csv_field_mapping(source: str) -> None:
    headers = header_names(source, "WriteTradeTransactionsHeader")
    record_arguments = file_write_arguments(source, "WriteTradeTransactionLog")[1:]
    assert len(headers) == len(record_arguments), (
        f"trade transaction header/record mismatch: {len(headers)} != "
        f"{len(record_arguments)}"
    )
    assert len(headers) == len(set(headers)), "Duplicate trade transaction CSV header"
    record = dict(zip(headers, record_arguments, strict=True))
    for item in HISTORY_GETTER_CONTRACT:
        actual = normalize_mql(record[item.csv_column])
        expected = normalize_mql(item.csv_expression)
        assert actual == expected, (
            f"CSV column {item.csv_column}: expected {expected}, got {actual}"
        )
    direct_contract = {
        "position": "SafeLongToString((long)trans.position)",
        "transaction_position_ticket": (
            "SafeLongToString((long)deal_observation.transaction_position_ticket)"
        ),
        "transaction_data_source": "transaction_data_source",
        "history_lookup_status": "deal_observation.history_lookup_status",
        "missing_history_fields": (
            "CsvEscape(deal_observation.missing_history_fields)"
        ),
    }
    for column, expected in direct_contract.items():
        actual = normalize_mql(record[column])
        assert actual == normalize_mql(expected), (
            f"CSV column {column}: expected {expected}, got {actual}"
        )
    initialize = normalize_mql(
        function_body(source, "InitializeDealHistoryObservation")
    )
    assert (
        "observation.transaction_position_ticket = trans.position;" in initialize
    ), "transaction_position_ticket must come directly from trans.position"


def validate_classification_branches(source: str) -> None:
    classification = normalize_mql(
        function_body(source, "ClassifyDealHistoryObservation")
    )
    ordered_branches = [
        (
            "history_lookup_unavailable",
            'if(!observation.history_lookup_succeeded) return "history_lookup_unavailable";',
        ),
        (
            "history_data_incomplete",
            'if(!observation.classification_core_getters_valid) return "history_data_incomplete";',
        ),
        (
            "unknown_deal_type",
            'if(!observation.deal_type_recognized) return "unknown_deal_type";',
        ),
        (
            "non_position_deal",
            'if(!IsPositionDealType(observation.deal_type_raw)) return "non_position_deal";',
        ),
        (
            "entry_deal",
            'if(observation.deal_entry_raw == (long)DEAL_ENTRY_IN) return "entry_deal";',
        ),
        (
            "reversal_deal",
            'if(observation.deal_entry_raw == (long)DEAL_ENTRY_INOUT) return "reversal_deal";',
        ),
        (
            "validated_exit",
            "if(IsExitDealEntry(observation.deal_entry_raw))",
        ),
        (
            "broker_stop_loss_exit",
            'if(observation.deal_reason_raw == (long)DEAL_REASON_SL) return "broker_stop_loss_exit";',
        ),
        (
            "broker_take_profit_exit",
            'if(observation.deal_reason_raw == (long)DEAL_REASON_TP) return "broker_take_profit_exit";',
        ),
        (
            "ea_or_manual_exit",
            "if(observation.deal_reason_raw == (long)DEAL_REASON_EXPERT || "
            "observation.deal_reason_raw == (long)DEAL_REASON_CLIENT || "
            "observation.deal_reason_raw == (long)DEAL_REASON_MOBILE || "
            'observation.deal_reason_raw == (long)DEAL_REASON_WEB) return "ea_or_manual_exit";',
        ),
    ]
    positions: list[int] = []
    for label, fragment in ordered_branches:
        normalized_fragment = normalize_mql(fragment)
        position = classification.find(normalized_fragment)
        assert position >= 0, f"classification branch mismatch: {label}"
        positions.append(position)
    assert positions == sorted(positions), "classification branch order mismatch"
    assert classification.count('return "external_or_unknown_exit";') == 2
    assert "deal_price" not in classification
    assert "position_sl" not in classification

    position_type = normalize_mql(function_body(source, "IsPositionDealType"))
    assert (
        "return deal_type_raw == (long)DEAL_TYPE_BUY || "
        "deal_type_raw == (long)DEAL_TYPE_SELL;" in position_type
    ), "Known BUY/SELL deal-type predicate changed"
    exit_entry = normalize_mql(function_body(source, "IsExitDealEntry"))
    assert (
        "return deal_entry_raw == (long)DEAL_ENTRY_OUT || "
        "deal_entry_raw == (long)DEAL_ENTRY_OUT_BY;" in exit_entry
    ), "OUT/OUT_BY exit-entry predicate changed"


def _guarded_request_result_block_spans(body: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    guard = re.compile(
        r"if\s*[(]\s*(?:request_context_valid|"
        r"trans[.]type\s*==\s*TRADE_TRANSACTION_REQUEST)\s*[)]\s*[{]"
    )
    for match in guard.finditer(body):
        open_brace = body.index("{", match.start())
        depth = 0
        for index in range(open_brace, len(body)):
            if body[index] == "{":
                depth += 1
            elif body[index] == "}":
                depth -= 1
                if depth == 0:
                    spans.append((open_brace, index))
                    break
        else:
            raise AssertionError("Unterminated request/result guard block")
    return spans


def validate_request_result_guards(source: str) -> list[str]:
    body = function_body(source, "WriteTradeTransactionLog")
    assert (
        "const bool request_context_valid = "
        "trans.type == TRADE_TRANSACTION_REQUEST;" in normalize_mql(body)
    )
    assert "InpMagicNumber" not in body
    guarded_spans = _guarded_request_result_block_spans(body)
    accessors: list[str] = []
    for match in re.finditer(r"\b(request|result)[.]([A-Za-z_]\w*)", body):
        accessor = match.group(0)
        accessors.append(accessor)
        statement_start = body.rfind(";", 0, match.start()) + 1
        statement_end = body.find(";", match.end())
        assert statement_end >= 0, f"Unterminated statement containing {accessor}"
        statement = body[statement_start : statement_end + 1]
        ternary_guard = re.search(
            r"(?:request_context_valid|"
            r"trans[.]type\s*==\s*TRADE_TRANSACTION_REQUEST)\s*[?]",
            statement,
        )
        ternary_guarded = False
        if ternary_guard is not None:
            question = statement.find("?", ternary_guard.start())
            false_branch = statement.find(":", question + 1)
            accessor_offset = match.start() - statement_start
            ternary_guarded = question < accessor_offset < false_branch
        block_guarded = any(
            start < match.start() < end for start, end in guarded_spans
        )
        assert ternary_guarded or block_guarded, (
            f"unguarded {accessor} in WriteTradeTransactionLog"
        )
    assert accessors, "No request/result accessors found in transaction logger"
    return accessors


def extract_transaction_data_source_values(
    source: str,
) -> dict[tuple[bool, bool], str]:
    body = normalize_mql(function_body(source, "TradeTransactionDataSource"))
    base_match = re.search(r'string source = "([^"]+)";', body)
    request_match = re.search(
        r'if\(request_context_valid\) source \+= "([^"]+)";', body
    )
    history_match = re.search(
        r'if\(deal_history_available\) source \+= "([^"]+)";', body
    )
    assert base_match is not None, "transaction_data_source base source missing"
    assert request_match is not None, "request/result provenance branch missing"
    assert history_match is not None, "deal-history provenance branch missing"
    assert "return source;" in body
    writer = function_body(source, "WriteTradeTransactionLog")
    assert re.search(
        r"const\s+string\s+transaction_data_source\s*=\s*"
        r"TradeTransactionDataSource\s*[(]\s*request_context_valid\s*,\s*"
        r"deal_observation[.]history_lookup_succeeded\s*[)]\s*;",
        writer,
    ), "transaction logger does not derive provenance from validated contexts"

    base = base_match.group(1)
    request_suffix = request_match.group(1)
    history_suffix = history_match.group(1)
    return {
        (False, False): base,
        (True, False): base + request_suffix,
        (False, True): base + history_suffix,
        (True, True): base + request_suffix + history_suffix,
    }


def classification_contract(
    *,
    history_selected: bool,
    type_valid: bool,
    entry_valid: bool,
    reason_valid: bool,
    type_recognized: bool,
    position_type: bool,
    entry: str,
    reason: str,
) -> str:
    if not history_selected:
        return "history_lookup_unavailable"
    if not (type_valid and entry_valid and reason_valid):
        return "history_data_incomplete"
    if not type_recognized:
        return "unknown_deal_type"
    if not position_type:
        return "non_position_deal"
    if entry == "IN":
        return "entry_deal"
    if entry == "INOUT":
        return "reversal_deal"
    if entry in {"OUT", "OUT_BY"}:
        if reason == "SL":
            return "broker_stop_loss_exit"
        if reason == "TP":
            return "broker_take_profit_exit"
        if reason in {"EXPERT", "CLIENT", "MOBILE", "WEB"}:
            return "ea_or_manual_exit"
        return "external_or_unknown_exit"
    return "external_or_unknown_exit"


def test_session_instance_id_is_created_once_per_on_init_and_not_used_as_state() -> None:
    source = read_ea()
    on_init = function_body(source, "OnInit")
    builder = function_body(source, "BuildSessionInstanceId")

    assert on_init.count("g_session_instance_id = BuildSessionInstanceId();") == 1
    assert source.count("g_session_instance_id = BuildSessionInstanceId();") == 1
    assert on_init.index("g_session_instance_id = BuildSessionInstanceId();") < on_init.index(
        "EnsureLogFolder();"
    )
    for token in ["TimeLocal()", "ChartID()", "GetTickCount64()", "GetMicrosecondCount()"]:
        assert token in builder
    assert "g_session_instance_id" not in function_body(source, "AttemptId")
    assert "g_session_instance_id" not in function_body(source, "LifecycleCloseAttemptCanonical")


def test_session_instance_id_is_appended_to_required_artifacts() -> None:
    source = read_ea()
    assert header_names(source, "WriteRunConfigHeader")[-1] == "session_instance_id"
    assert "g_session_instance_id" in function_body(source, "WriteRunConfigLog")
    assert "session_instance_id" in header_names(source, "WriteTradeTransactionsHeader")
    assert "g_session_instance_id" in function_body(source, "WriteTradeTransactionLog")
    assert "session_instance_id" in header_names(source, "WriteRunFinalSummaryHeader")
    assert "g_session_instance_id" in function_body(source, "WriteRunFinalSummaryLog")


def test_docs_bound_session_identity_and_legacy_csv_append_contract() -> None:
    combined = " ".join(
        path.read_text(encoding="utf-8").lower() for path in CURRENT_PATCH_A_DOCS
    )
    assert "practically unique" in combined
    assert "mathematical uniqueness guarantee" in combined
    assert "csv schema change" in combined
    assert "new `inprunid`" in combined
    assert "`inpoverwritelogsoninit=false`" in combined


def test_deal_add_uses_exactly_one_one_shot_history_lookup_with_trans_deal() -> None:
    source = read_ea()
    build = function_body(source, "BuildDealHistoryObservation")

    assert source.count("HistoryDealSelect(") == 1
    assert "HistorySelect(" not in source
    assert "if(!HistoryDealSelect(trans.deal))" in build
    assert build.index("if(!observation.is_deal_add)") < build.index(
        "if(!HistoryDealSelect(trans.deal))"
    )
    for forbidden in ["Sleep(", "OnTimer(", "EventSetTimer(", "EventSetMillisecondTimer(", "while(", "while ("]:
        assert forbidden not in source
    for forbidden in ["for(", "for (", "while(", "while ("]:
        assert forbidden not in build


def test_history_lookup_failure_is_nonblocking_and_preserves_transaction_fields() -> None:
    source = read_ea()
    initialize = function_body(source, "InitializeDealHistoryObservation")
    build = function_body(source, "BuildDealHistoryObservation")
    record = record_by_header(
        source, "WriteTradeTransactionsHeader", "WriteTradeTransactionLog"
    )
    failure_start = build.index("if(!HistoryDealSelect(trans.deal))")
    success_start = build.index("observation.history_lookup_succeeded = true;")
    failure_block = build[failure_start:success_start]

    for token in [
        "observation.transaction_position_ticket = trans.position",
        "observation.deal_ticket = 0",
        "observation.order_ticket = 0",
        "observation.deal_position_id = 0",
        'observation.symbol = ""',
        "observation.deal_price = 0.0",
        "observation.deal_volume = 0.0",
        '"unavailable_at_callback"',
        '"not_attempted"',
    ]:
        assert token in initialize
    assert record["order"] == "SafeLongToString((long)trans.order)"
    assert record["deal"] == "SafeLongToString((long)trans.deal)"
    assert record["position"] == "SafeLongToString((long)trans.position)"
    assert record["price"] == "FormatNumber(trans.price)"
    assert record["volume"] == "FormatNumber(trans.volume)"
    for token in [
        "GetLastError()",
        '"HistoryDealSelect_failed_at_callback"',
        "g_deal_history_lookup_unavailable_count++",
        "return;",
    ]:
        assert token in failure_block


def test_transaction_position_ticket_and_deal_position_id_are_never_conflated() -> None:
    source = read_ea()
    initialize = function_body(source, "InitializeDealHistoryObservation")
    build = function_body(source, "BuildDealHistoryObservation")
    record = record_by_header(
        source, "WriteTradeTransactionsHeader", "WriteTradeTransactionLog"
    )

    assert "observation.transaction_position_ticket = trans.position;" in initialize
    assert "observation.deal_position_id = trans.position" not in source
    assert (
        'ReadHistoryDealInteger(trans.deal,DEAL_POSITION_ID,"DEAL_POSITION_ID",'
        "observation.deal_position_id,observation)"
    ) in build
    assert "observation.transaction_position_ticket =" not in build
    assert record["transaction_position_ticket"] == (
        "SafeLongToString((long)deal_observation.transaction_position_ticket)"
    )
    assert record["deal_position_id"] == (
        "deal_observation.deal_position_id_valid ? "
        'SafeLongToString(deal_observation.deal_position_id) : ""'
    )


def test_history_property_variable_validity_and_csv_contract_matches_real_mql() -> None:
    source = read_ea()
    validate_history_getter_mapping(source)
    validate_csv_field_mapping(source)


@pytest.mark.parametrize(
    ("left_property", "right_property"),
    [
        ("DEAL_PROFIT", "DEAL_COMMISSION"),
        ("DEAL_SWAP", "DEAL_FEE"),
        ("DEAL_TYPE", "DEAL_ENTRY"),
        ("DEAL_ORDER", "DEAL_POSITION_ID"),
    ],
)
def test_history_mapping_validator_rejects_swapped_getter_properties(
    left_property: str, right_property: str
) -> None:
    source = read_ea()
    mutated = mutate_function_swap(
        source,
        "BuildDealHistoryObservation",
        f",{left_property},",
        f",{right_property},",
    )
    with pytest.raises(AssertionError, match="DEAL_") as error:
        validate_history_getter_mapping(mutated)
    assert left_property in str(error.value)


@pytest.mark.parametrize(
    ("left_column", "right_column"),
    [
        ("deal_profit", "deal_commission"),
        ("deal_swap", "deal_fee"),
        ("deal_type_raw", "deal_entry_raw"),
        ("order_ticket", "deal_position_id"),
    ],
)
def test_csv_mapping_validator_rejects_swapped_filewrite_expressions(
    left_column: str, right_column: str
) -> None:
    source = read_ea()
    by_column = {item.csv_column: item for item in HISTORY_GETTER_CONTRACT}
    mutated = mutate_function_swap(
        source,
        "WriteTradeTransactionLog",
        by_column[left_column].csv_expression,
        by_column[right_column].csv_expression,
    )
    with pytest.raises(AssertionError, match="CSV column") as error:
        validate_csv_field_mapping(mutated)
    assert left_column in str(error.value)


def test_required_history_properties_raw_enums_names_and_costs_are_exported() -> None:
    source = read_ea()
    build = function_body(source, "BuildDealHistoryObservation")
    header = header_names(source, "WriteTradeTransactionsHeader")

    for token in [
        "DEAL_TICKET",
        "DEAL_ORDER",
        "DEAL_POSITION_ID",
        "DEAL_SYMBOL",
        "DEAL_MAGIC",
        "DEAL_TIME",
        "DEAL_TIME_MSC",
        "DEAL_TYPE",
        "DEAL_ENTRY",
        "DEAL_REASON",
        "DEAL_PRICE",
        "DEAL_VOLUME",
        "DEAL_PROFIT",
        "DEAL_COMMISSION",
        "DEAL_SWAP",
        "DEAL_FEE",
        "ReadHistoryDealInteger",
        "ReadHistoryDealDouble",
        "ReadHistoryDealString",
    ]:
        assert token in build

    for field in [
        "deal_ticket",
        "order_ticket",
        "transaction_position_ticket",
        "deal_position_id",
        "deal_symbol",
        "deal_magic",
        "deal_time",
        "deal_time_msc",
        "deal_type_raw",
        "deal_type_name",
        "deal_entry_raw",
        "deal_entry_name",
        "deal_reason_raw",
        "deal_reason_name",
        "deal_price",
        "deal_volume",
        "deal_profit",
        "deal_commission",
        "deal_swap",
        "deal_fee",
        "history_lookup_status",
        "history_lookup_error_code",
        "history_lookup_error_text",
        "history_getter_status",
        "history_getter_error_code",
        "history_getter_error_text",
        "missing_history_fields",
    ]:
        assert field in header


def test_history_getters_use_boolean_overloads_and_report_partial_failures() -> None:
    source = read_ea()
    build = function_body(source, "BuildDealHistoryObservation")
    failure_recorder = function_body(source, "RecordHistoryGetterFailure")

    calls = re.findall(
        r"HistoryDealGet(?:Integer|Double|String)[(]([^)]+)[)]", source
    )
    assert len(calls) == 3
    assert all(len(split_top_level_arguments(call)) == 3 for call in calls)
    for helper, value_type in [
        ("ReadHistoryDealInteger", "long &value"),
        ("ReadHistoryDealDouble", "double &value"),
        ("ReadHistoryDealString", "string &value"),
    ]:
        signature_start = source.index(f"{helper}(")
        signature = source[signature_start : source.index("{", signature_start)]
        body = function_body(source, helper)
        assert value_type in signature
        assert "ResetLastError();" in body
        assert "return true;" in body
        assert "RecordHistoryGetterFailure" in body
        assert "GetLastError()" in body
        assert "return false;" in body

    assert 'observation.history_lookup_status = "history_select_success";' in build
    assert '"core_getters_success"' in build
    assert '"economic_getters_complete"' in build
    assert '"text_getters_complete"' in build
    assert '"|partial_getter_failure"' in build
    assert "observation.missing_history_fields += field_name" in failure_recorder
    assert "observation.history_getter_error_code" in failure_recorder
    assert "observation.history_getter_error_text" in failure_recorder


def test_valid_zero_history_values_are_distinct_from_missing_values() -> None:
    source = read_ea()
    record = record_by_header(
        source, "WriteTradeTransactionsHeader", "WriteTradeTransactionLog"
    )
    validity_guards = {
        "deal_magic": "deal_observation.magic_valid",
        "deal_reason_raw": "deal_observation.deal_reason_valid",
        "deal_profit": "deal_observation.deal_profit_valid",
        "deal_commission": "deal_observation.deal_commission_valid",
        "deal_swap": "deal_observation.deal_swap_valid",
        "deal_fee": "deal_observation.deal_fee_valid",
    }
    for field, validity_guard in validity_guards.items():
        expression = record[field]
        assert expression.startswith(f"{validity_guard} ? ")
        assert expression.endswith(': ""')
        assert "> 0" not in expression
        assert "!= 0" not in expression

    assert record["history_getter_status"] == "deal_observation.history_getter_status"
    assert record["missing_history_fields"] == (
        "CsvEscape(deal_observation.missing_history_fields)"
    )


def test_classification_is_guarded_by_validated_type_entry_and_reason() -> None:
    source = read_ea()
    build = function_body(source, "BuildDealHistoryObservation")
    classification = function_body(source, "ClassifyDealHistoryObservation")
    normalized_build = " ".join(build.split())

    assert (
        "observation.classification_core_getters_valid = "
        "observation.deal_type_valid && observation.deal_entry_valid && "
        "observation.deal_reason_valid;"
    ) in normalized_build
    history_guard = classification.index("!observation.history_lookup_succeeded")
    core_guard = classification.index("!observation.classification_core_getters_valid")
    unknown_guard = classification.index("!observation.deal_type_recognized")
    position_guard = classification.index("!IsPositionDealType")
    assert history_guard < core_guard < unknown_guard < position_guard
    assert '"history_data_incomplete"' in classification
    assert '"unknown_deal_type"' in classification


def test_enum_names_have_conservative_unknown_numeric_fallback() -> None:
    source = read_ea()
    fallback = function_body(source, "EnumNameOrUnknown")
    for function_name, enum_type in [
        ("DealTypeName", "ENUM_DEAL_TYPE"),
        ("DealEntryName", "ENUM_DEAL_ENTRY"),
        ("DealReasonName", "ENUM_DEAL_REASON"),
    ]:
        body = function_body(source, function_name)
        assert "EnumToString" in body
        assert enum_type in body
        assert "EnumNameOrUnknown" in body
    assert '"unknown_" + SafeLongToString(raw_value)' in fallback


def test_event_classification_uses_type_entry_reason_and_never_price_equality() -> None:
    source = read_ea()
    classification = function_body(source, "ClassifyDealHistoryObservation")
    normalized = " ".join(classification.split())

    for token in [
        "deal_type_raw",
        "deal_entry_raw",
        "deal_reason_raw",
        "DEAL_ENTRY_IN",
        "DEAL_ENTRY_OUT",
        "DEAL_ENTRY_OUT_BY",
        "DEAL_ENTRY_INOUT",
        "DEAL_REASON_SL",
        "DEAL_REASON_TP",
        "DEAL_REASON_EXPERT",
        "DEAL_REASON_CLIENT",
        '"broker_stop_loss_exit"',
        '"broker_take_profit_exit"',
        '"ea_or_manual_exit"',
        '"entry_deal"',
        '"reversal_deal"',
        '"external_or_unknown_exit"',
        '"non_position_deal"',
        '"unknown_deal_type"',
        '"history_data_incomplete"',
        '"history_lookup_unavailable"',
    ]:
        assert token in classification or token in function_body(source, "IsExitDealEntry")
    for branch in [
        'if(observation.deal_entry_raw == (long)DEAL_ENTRY_IN) return "entry_deal";',
        'if(observation.deal_entry_raw == (long)DEAL_ENTRY_INOUT) return "reversal_deal";',
        'if(observation.deal_reason_raw == (long)DEAL_REASON_SL) return "broker_stop_loss_exit";',
        'if(observation.deal_reason_raw == (long)DEAL_REASON_TP) return "broker_take_profit_exit";',
    ]:
        assert branch in normalized
    for forbidden in ["deal_price", "position_sl", "price_sl", "deal_sl"]:
        assert forbidden not in classification


def test_real_mql_classification_branch_contract_and_order() -> None:
    validate_classification_branches(read_ea())


@pytest.mark.parametrize(
    ("left_classification", "right_classification"),
    [
        ("unknown_deal_type", "non_position_deal"),
        ("broker_stop_loss_exit", "broker_take_profit_exit"),
        ("entry_deal", "reversal_deal"),
        ("history_lookup_unavailable", "history_data_incomplete"),
    ],
)
def test_classification_validator_rejects_swapped_mql_returns(
    left_classification: str, right_classification: str
) -> None:
    source = read_ea()
    mutated = mutate_function_swap(
        source,
        "ClassifyDealHistoryObservation",
        f'"{left_classification}"',
        f'"{right_classification}"',
    )
    with pytest.raises(
        AssertionError, match="classification branch mismatch"
    ) as error:
        validate_classification_branches(mutated)
    assert left_classification in str(error.value)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"history_selected": False}, "history_lookup_unavailable"),
        ({"reason_valid": False}, "history_data_incomplete"),
        ({"type_recognized": False}, "unknown_deal_type"),
        ({"position_type": False}, "non_position_deal"),
        ({"entry": "IN"}, "entry_deal"),
        ({"entry": "INOUT"}, "reversal_deal"),
        ({"entry": "OUT", "reason": "SL"}, "broker_stop_loss_exit"),
        ({"entry": "OUT", "reason": "TP"}, "broker_take_profit_exit"),
        ({"entry": "OUT", "reason": "EXPERT"}, "ea_or_manual_exit"),
        ({"entry": "OUT_BY", "reason": "OTHER"}, "external_or_unknown_exit"),
    ],
)
def test_classification_contract_table(overrides: dict[str, object], expected: str) -> None:
    case: dict[str, object] = {
        "history_selected": True,
        "type_valid": True,
        "entry_valid": True,
        "reason_valid": True,
        "type_recognized": True,
        "position_type": True,
        "entry": "OUT",
        "reason": "OTHER",
    }
    case.update(overrides)
    assert classification_contract(**case) == expected


def test_transaction_and_history_sources_are_explicit_and_broker_text_is_escaped() -> None:
    source = read_ea()
    writer = function_body(source, "WriteTradeTransactionLog")
    escape = function_body(source, "CsvEscape")
    for token in [
        '"MqlTradeTransaction"',
        "TradeTransactionFieldsStatus(trans.type)",
        "deal_core_fields_source",
        "history_lookup_status",
        "history_getter_status",
        "missing_history_fields",
        "trans_deal_type_raw",
        "trans_deal_type_name",
    ]:
        assert token in source
    for token in [
        "CsvEscape(tx_symbol)",
        "CsvEscape(deal_observation.symbol)",
        "CsvEscape(deal_observation.deal_comment)",
        "CsvEscape(deal_observation.deal_external_id)",
        "CsvEscape(deal_observation.history_lookup_error_text)",
        "CsvEscape(deal_observation.history_getter_error_text)",
        "CsvEscape(deal_observation.missing_history_fields)",
    ]:
        assert token in writer
    assert "CharToString(34)" in escape
    assert 'StringFind(value, ",")' in escape
    assert "StringReplace(value, quote, quote + quote)" in escape


def test_request_and_result_are_read_only_for_trade_transaction_request() -> None:
    source = read_ea()
    writer = function_body(source, "WriteTradeTransactionLog")
    record = record_by_header(
        source, "WriteTradeTransactionsHeader", "WriteTradeTransactionLog"
    )
    accessors = validate_request_result_guards(source)

    assert (
        "const bool request_context_valid = "
        "trans.type == TRADE_TRANSACTION_REQUEST;"
    ) in writer
    assert "InpMagicNumber" not in writer
    assert set(accessors) == {
        "request.symbol",
        "request.magic",
        "request.action",
        "result.retcode",
        "result.comment",
    }

    assert record["symbol"] == "CsvEscape(tx_symbol)"
    assert "const string tx_symbol = trans.symbol;" in writer
    assert record["request_context_status"] == "request_context_status"
    assert record["request_symbol"] == "CsvEscape(request_symbol)"
    assert record["request_magic"] == "request_magic"
    assert record["result_comment"] == "CsvEscape(result_comment)"
    assert '"not_applicable"' in writer
    assert "TradeTransactionDataSource(" in writer


@pytest.mark.parametrize("unguarded_accessor", ["request.volume", "result.order"])
def test_generic_request_result_guard_rejects_new_unguarded_accessors(
    unguarded_accessor: str,
) -> None:
    source = read_ea()
    body = function_body(source, "WriteTradeTransactionLog")
    anchor = (
        "const bool request_context_valid = "
        "trans.type == TRADE_TRANSACTION_REQUEST;"
    )
    assert body.count(anchor) == 1
    mutated_body = body.replace(
        anchor,
        anchor + f"\n   const string mutation_probe = {unguarded_accessor};",
        1,
    )
    mutated = replace_function_body(
        source, "WriteTradeTransactionLog", mutated_body
    )
    with pytest.raises(
        AssertionError, match=rf"unguarded {re.escape(unguarded_accessor)}"
    ):
        validate_request_result_guards(mutated)


def test_generic_request_result_guard_rejects_accessor_in_false_ternary_branch() -> None:
    source = read_ea()
    body = function_body(source, "WriteTradeTransactionLog")
    anchor = (
        "const bool request_context_valid = "
        "trans.type == TRADE_TRANSACTION_REQUEST;"
    )
    mutated_body = body.replace(
        anchor,
        anchor
        + '\n   const string mutation_probe = request_context_valid ? "" : result.deal;',
        1,
    )
    mutated = replace_function_body(
        source, "WriteTradeTransactionLog", mutated_body
    )
    with pytest.raises(AssertionError, match=r"unguarded result[.]deal"):
        validate_request_result_guards(mutated)


@pytest.mark.parametrize(
    ("case_name", "request_context_valid", "deal_history_available", "expected"),
    [
        (
            "non_request_without_history",
            False,
            False,
            "MqlTradeTransaction",
        ),
        (
            "request_callback",
            True,
            False,
            "MqlTradeTransaction+MqlTradeRequest+MqlTradeResult",
        ),
        (
            "deal_add_history_success",
            False,
            True,
            "MqlTradeTransaction+DealHistory",
        ),
        (
            "deal_add_history_unavailable",
            False,
            False,
            "MqlTradeTransaction",
        ),
    ],
)
def test_transaction_data_source_tracks_only_sources_actually_consumed(
    case_name: str,
    request_context_valid: bool,
    deal_history_available: bool,
    expected: str,
) -> None:
    del case_name
    values = extract_transaction_data_source_values(read_ea())
    assert values[(request_context_valid, deal_history_available)] == expected


def test_transaction_data_source_supports_combined_valid_contexts_and_keeps_statuses() -> None:
    source = read_ea()
    values = extract_transaction_data_source_values(source)
    assert values[(True, True)] == (
        "MqlTradeTransaction+MqlTradeRequest+MqlTradeResult+DealHistory"
    )
    record = record_by_header(
        source, "WriteTradeTransactionsHeader", "WriteTradeTransactionLog"
    )
    assert record["transaction_data_source"] == "transaction_data_source"
    assert record["history_lookup_status"] == "deal_observation.history_lookup_status"
    assert record["request_context_status"] == "request_context_status"


def test_runbook_documents_provenance_and_unavailable_history_semantics() -> None:
    runbook = Path("docs/demo_live_smoke_runbook.md").read_text(encoding="utf-8")
    for token in [
        "`transaction_data_source` lists only sources actually consumed",
        "`MqlTradeTransaction`",
        "`MqlTradeRequest+MqlTradeResult`",
        "`DealHistory` only after a successful deal-history select",
        "`history_lookup_status=unavailable_at_callback`",
    ]:
        assert token in runbook


def test_csv_headers_and_records_have_matching_column_counts() -> None:
    source = read_ea()
    pairs = [
        ("WriteRunConfigHeader", "WriteRunConfigLog"),
        ("WriteTradeTransactionsHeader", "WriteTradeTransactionLog"),
        ("WriteRunFinalSummaryHeader", "WriteRunFinalSummaryLog"),
    ]
    for header_function, record_function in pairs:
        header_arguments = file_write_arguments(source, header_function)
        record_arguments = file_write_arguments(source, record_function)
        assert len(header_arguments) == len(record_arguments), (
            header_function,
            len(header_arguments) - 1,
            record_function,
            len(record_arguments) - 1,
        )
        assert len(header_arguments) - 1 <= 63


def test_observational_key_does_not_create_a_durable_deduplication_policy() -> None:
    source = read_ea()
    key = function_body(source, "TradeTransactionObservationKey")
    on_trade_transaction = function_body(source, "OnTradeTransaction")

    for token in [
        "g_session_instance_id",
        "trans.type",
        "trans.deal",
        "trans.order",
        "deal_time_msc",
    ]:
        assert token in key
    assert on_trade_transaction.count("WriteTradeTransactionLog(trans,request,result);") == 1
    assert function_body(source, "WriteTradeTransactionLog").count("FileWrite(") == 1
    assert "observational_event_key" not in function_body(source, "EvaluateSendPreflight")
    assert "observational_event_key" not in function_body(
        source, "EvaluateIntegratedLifecycleClosePreflight"
    )


def test_final_summary_observability_counters_are_appended_without_execution_changes() -> None:
    source = read_ea()
    summary_header = header_names(source, "WriteRunFinalSummaryHeader")
    assert summary_header[-7:] == [
        "session_instance_id",
        "deal_add_observed_count",
        "deal_history_lookup_success_count",
        "deal_history_lookup_unavailable_count",
        "stop_loss_exit_observed_count",
        "take_profit_exit_observed_count",
        "other_exit_observed_count",
    ]
    assert source.count("OrderSend(") == 2
    for forbidden in [
        "OrderSendAsync(",
        "PositionClose(",
        "CTrade",
        "trade.Buy(",
        "trade.Sell(",
        "retry_performed = true",
        "automatic_retry_allowed = true",
    ]:
        assert forbidden not in source


def test_request_construction_demo_gates_and_lifecycle_close_are_unchanged() -> None:
    source = read_ea()
    entry_request = function_body(source, "BuildBrokerSafeCheckRequest")
    close_request = function_body(source, "BuildLifecycleCloseRequest")
    for token in [
        "request.action = TRADE_ACTION_DEAL",
        "request.type = ORDER_TYPE_SELL",
        "request.price = price",
        "request.sl = sl",
        "request.tp = tp",
        "request.magic = (ulong)InpMagicNumber",
    ]:
        assert token in entry_request
    for token in [
        "close_request.action = TRADE_ACTION_DEAL",
        "close_request.type = ORDER_TYPE_BUY",
        "close_request.position = snapshot.position_ticket",
        "close_request.volume = close_volume",
        "close_request.price = NormalizeSymbolPrice(ask_price)",
    ]:
        assert token in close_request
    for token in [
        "input int InpMaxOrderSendAttempts = 1;",
        "input int InpMaxLifecycleCloseAttempts = 1;",
        "input bool InpRequireDemoAccount = true;",
        "input bool InpAllowLiveAccount = false;",
        "InpMaxSpreadPoints = 15",
        "InpMaxRiskPercentPerTrade = 0.5",
    ]:
        assert token in source
