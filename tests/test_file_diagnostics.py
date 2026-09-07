from pathlib import Path

from ioaudit import inspect_csv


def test_csv_file_diagnostics(tmp_path: Path):
    path = tmp_path / "table.csv"
    path.write_text(
        "sector,A,B\n"
        "A,\"1,234\",5.0\n"
        "B,－,x\n"
        "\n"
        "単位：百万円\n"
        "A,1,234,5,678,\n"
        "sector,A,B\n",
        encoding="utf-8",
    )
    result = inspect_csv(path)
    assert result.encoding == "utf-8"
    assert result.delimiter == ","
    assert result.internal_blank_lines == [4]
    assert result.trailing_blank_lines == []
    assert result.trailing_delimiter == [6]
    assert result.unexpected_text_rows[0]["line"] == 5
    assert result.repeated_header_rows == [7]
    assert result.possible_unquoted_thousands_separator is True
    assert result.missing_value_tokens["－"] == 1
    assert result.non_numeric_tokens["x"] == 1
    assert result.status == "FAIL"


def test_bom_cp932_and_header_diagnostics(tmp_path: Path):
    path = tmp_path / "table.csv"
    path.write_bytes("部門,部門,\n農業,1,2\n".encode("utf-8-sig"))
    result = inspect_csv(path)
    assert result.encoding == "utf-8-sig"
    assert result.bom is True
    assert result.duplicate_headers == ["部門"]
    assert result.empty_headers == [2]
    assert result.status == "FAIL"


def test_cp932_encoding_detection(tmp_path: Path):
    path = tmp_path / "table_cp932.csv"
    path.write_bytes("部門,A\n農業,1\n".encode("cp932"))
    result = inspect_csv(path)
    assert result.encoding == "cp932"
    assert result.numeric_columns["A"]["numeric_percentage"] == 100.0


def test_quoting_anomaly_and_serialization(tmp_path: Path):
    path = tmp_path / "broken.csv"
    path.write_text("A,B\n\"unclosed,2\n", encoding="utf-8")
    result = inspect_csv(path)
    assert result.quoting_anomaly is True
    assert result.parse_error
    assert "quoting_anomaly" in result.to_json()
    assert not result.to_dataframe().empty


def test_auto_delimiter_does_not_confuse_quoted_thousands(tmp_path: Path):
    path = tmp_path / "semicolon.csv"
    path.write_text(
        "sector;A;B\nA;\"1,234\";\"5,678\"\nB;2;3\n",
        encoding="utf-8",
    )
    result = inspect_csv(path, delimiter=None)
    assert result.delimiter == ";"
    assert result.inconsistent_column_count == []


def test_completely_blank_csv_row_is_reported(tmp_path: Path):
    path = tmp_path / "blank.csv"
    path.write_text("A,B\n1,2\n,,\n3,4\n", encoding="utf-8")
    result = inspect_csv(path)
    assert result.completely_blank_rows == [3]
    assert result.status == "WARNING"
