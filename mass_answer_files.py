"""Validated CSV/Excel parsing and safe mass-answer output serialization."""

from __future__ import annotations

import csv
import io
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass

import pandas as pd


SUPPORTED_EXTENSIONS = {".csv", ".xlsx"}
QUERY_COLUMN_ALIASES = {"question", "query", "سوال", "سؤال", "پرسش"}
OUTPUT_COLUMNS = (
    "Answer (پاسخ)",
    "status",
    "error_code",
    "error_message",
    "processing_time_ms",
    "intent",
    "rewritten_query",
    "related_questions",
)
FORMULA_PREFIXES = ("=", "+", "-", "@")


class MassAnswerFileError(ValueError):
    pass


@dataclass
class ParsedMassAnswerFile:
    dataframe: pd.DataFrame
    question_column: object
    input_extension: str
    output_extension: str
    filename: str


async def read_upload_limited(upload, *, max_bytes: int) -> bytes:
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(min(1024 * 1024, max_bytes + 1 - total))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise MassAnswerFileError("Uploaded file exceeds the size limit")
        chunks.append(chunk)
    if not chunks:
        raise MassAnswerFileError("Uploaded file is empty")
    return b"".join(chunks)


def normalize_column_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    text = text.replace("ي", "ی").replace("ك", "ک")
    text = re.sub(r"\s+", " ", text)
    return text


def parse_mass_answer_file(
    *, contents: bytes, filename: str, max_rows: int
) -> ParsedMassAnswerFile:
    safe_name = os.path.basename(filename or "batch")
    extension = os.path.splitext(safe_name)[1].lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise MassAnswerFileError(
            "Unsupported file format; use .csv or .xlsx"
        )
    if max_rows < 1:
        raise ValueError("max_rows must be positive")
    if extension == ".csv":
        dataframe, headers = _parse_csv(contents, max_rows=max_rows)
    else:
        dataframe, headers = _parse_excel(
            contents, extension=extension, max_rows=max_rows
        )
    question_column = _validate_columns(headers)
    if dataframe.empty:
        raise MassAnswerFileError("Input file has a header but no data rows")
    if len(dataframe.index) > max_rows:
        raise MassAnswerFileError(f"Input file exceeds the {max_rows}-row limit")
    return ParsedMassAnswerFile(
        dataframe=dataframe,
        question_column=question_column,
        input_extension=extension,
        output_extension=extension,
        filename=safe_name,
    )


def _parse_csv(contents: bytes, *, max_rows: int):
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MassAnswerFileError(
            "CSV must be UTF-8 or UTF-8 with BOM"
        ) from exc
    if not text.strip():
        raise MassAnswerFileError("Uploaded CSV is empty")
    sample = text[:65536]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    try:
        rows = list(csv.reader(io.StringIO(text), dialect=dialect, strict=True))
    except csv.Error as exc:
        raise MassAnswerFileError("CSV is malformed") from exc
    if not rows or not rows[0] or not any(str(cell).strip() for cell in rows[0]):
        raise MassAnswerFileError("CSV header is missing")
    if any(row and len(row) != len(rows[0]) for row in rows[1:]):
        raise MassAnswerFileError("CSV has an inconsistent number of columns")
    headers = rows[0]
    try:
        dataframe = pd.read_csv(
            io.StringIO(text),
            sep=dialect.delimiter,
            nrows=max_rows + 1,
            skip_blank_lines=False,
        )
    except Exception as exc:
        raise MassAnswerFileError("CSV is malformed") from exc
    return dataframe, headers


def _parse_excel(contents: bytes, *, extension: str, max_rows: int):
    source = io.BytesIO(contents)
    try:
        header_frame = pd.read_excel(source, header=None, nrows=1)
        source.seek(0)
        dataframe = pd.read_excel(source, nrows=max_rows + 1)
    except Exception as exc:
        raise MassAnswerFileError("Excel workbook is malformed or unsupported") from exc
    if header_frame.empty:
        raise MassAnswerFileError("Excel header is missing")
    headers = header_frame.iloc[0].tolist()
    if not any(not pd.isna(value) and str(value).strip() for value in headers):
        raise MassAnswerFileError("Excel header is missing")
    return dataframe, headers


def _validate_columns(headers: list[object]) -> object:
    normalized: dict[str, object] = {}
    for header in headers:
        if pd.isna(header) or not str(header).strip():
            raise MassAnswerFileError("Column names cannot be empty")
        name = normalize_column_name(header)
        if name in normalized:
            raise MassAnswerFileError(
                f"Duplicate column name after normalization: {name}"
            )
        normalized[name] = header
    output_names = {normalize_column_name(name) for name in OUTPUT_COLUMNS}
    collision = output_names.intersection(normalized)
    if collision:
        raise MassAnswerFileError(
            "Input contains reserved output column: " + sorted(collision)[0]
        )
    matches = [
        original
        for name, original in normalized.items()
        if name in QUERY_COLUMN_ALIASES
    ]
    if not matches:
        raise MassAnswerFileError(
            "Required query column is missing; use question, query, سوال, سؤال, or پرسش"
        )
    if len(matches) > 1:
        raise MassAnswerFileError("Input contains more than one query column")
    return matches[0]


def write_safe_output(
    dataframe: pd.DataFrame,
    *,
    extension: str,
    output_path: str | None = None,
) -> str:
    if extension not in {".csv", ".xlsx"}:
        raise ValueError("output extension must be .csv or .xlsx")
    path = output_path
    if path is None:
        descriptor, path = tempfile.mkstemp(suffix=extension)
        os.close(descriptor)
    safe_frame = dataframe.map(_neutralize_formula)
    try:
        if extension == ".csv":
            safe_frame.to_csv(
                path, index=False, encoding="utf-8-sig", lineterminator="\n"
            )
        else:
            safe_frame.to_excel(path, index=False, engine="openpyxl")
        return path
    except Exception:
        if path and os.path.exists(path):
            os.remove(path)
        raise


def _neutralize_formula(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value
