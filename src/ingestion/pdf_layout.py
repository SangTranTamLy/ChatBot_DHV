"""Layout-preserving PDF extraction helpers.

The ingestion boundary keeps the page text used by the RAG pipeline, but also
retains the native/OCR layout objects that produced that text.  Nothing in
this module is allowed to silently discard a page, table, list, or OCR token.
"""

from __future__ import annotations

from functools import lru_cache
import os
import re
from typing import Any, Iterable


_LIST_MARKER_RE = re.compile(r"^\s*(?:(?P<bullet>[-•●▪◦*])|(?P<number>\d+[.)]))\s+(?P<text>.+?)\s*$")
_URL_RE = re.compile(r"https?://[^\s)>]+", re.IGNORECASE)
_TABLE_HINT_RE = re.compile(
    r"\b(?:mã\s+ngành|ma\s+nganh|tên\s+ngành|ten\s+nganh|học\s+bạ|hoc\s+ba|đgnl|học\s+phí|hoc\s+phi)\b",
    re.IGNORECASE,
)


def _clean_text(value: object) -> str:
    text = str(value or "").replace("\u00a0", " ").replace("\u00ad", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _bbox(value: object) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return [round(float(part), 3) for part in value]
    except (TypeError, ValueError):
        return None


def _bbox_from_points(value: object) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or not value:
        return _bbox(value)
    points: list[tuple[float, float]] = []
    for point in value:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            points.append((float(point[0]), float(point[1])))
        except (TypeError, ValueError):
            continue
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3)]


def _looks_like_heading(text: str, max_font_size: float = 0.0) -> bool:
    compact = " ".join(text.split())
    if not compact or len(compact) > 180:
        return False
    if max_font_size >= 15:
        return True
    letters = [character for character in compact if character.isalpha()]
    uppercase_ratio = (
        sum(character.isupper() for character in letters) / len(letters)
        if letters
        else 0.0
    )
    return uppercase_ratio >= 0.72 and len(compact.split()) <= 18


def _list_marker(text: str) -> tuple[bool, bool, str] | None:
    match = _LIST_MARKER_RE.match(text)
    if not match:
        return None
    return bool(match.group("number")), bool(match.group("bullet")), match.group("text").strip()


def _native_words(page: Any) -> list[dict[str, object]]:
    words: list[dict[str, object]] = []
    for index, item in enumerate(page.get_text("words", sort=True) or (), start=1):
        if len(item) < 8:
            continue
        text = _clean_text(item[4])
        if not text:
            continue
        words.append(
            {
                "word_index": index,
                "text": text,
                "bbox": _bbox(item[:4]),
                "block_index": int(item[5]),
                "line_index": int(item[6]),
                "word_in_line": int(item[7]),
                "source": "native",
            }
        )
    return words


def _native_elements(page: Any) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    elements: list[dict[str, object]] = []
    raw_dict = page.get_text("dict", sort=True) or {}
    for block_index, block in enumerate(raw_dict.get("blocks", []), start=1):
        block_type = int(block.get("type", 0))
        block_box = _bbox(block.get("bbox"))
        if block_type == 1:
            elements.append(
                {
                    "type": "image",
                    "text": "",
                    "bbox": block_box,
                    "source": "native",
                    "block_index": block_index,
                }
            )
            continue
        lines: list[str] = []
        max_font_size = 0.0
        for line in block.get("lines", []) or ():
            span_text: list[str] = []
            for span in line.get("spans", []) or ():
                span_text.append(str(span.get("text") or ""))
                try:
                    max_font_size = max(max_font_size, float(span.get("size") or 0.0))
                except (TypeError, ValueError):
                    pass
            value = _clean_text("".join(span_text))
            if value:
                lines.append(value)
        text = _clean_text("\n".join(lines))
        if not text:
            continue
        marker = _list_marker(text)
        if marker is not None:
            ordered, _, item_text = marker
            element_type = "list_item"
            element_text = item_text
            extra = {"ordered": ordered, "marker": text[: text.find(item_text)].strip()}
        elif _looks_like_heading(text, max_font_size):
            element_type = "heading"
            element_text = text
            extra = {}
        else:
            element_type = "paragraph"
            element_text = text
            extra = {}
        elements.append(
            {
                "type": element_type,
                "text": element_text,
                "bbox": block_box,
                "source": "native",
                "block_index": block_index,
                "reading_order": len(elements) + 1,
                **extra,
            }
        )
    return elements, _native_words(page)


def _group_ocr_tokens(tokens: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    ordered = sorted(
        (dict(token) for token in tokens if str(token.get("text") or "").strip()),
        key=lambda token: (
            float((token.get("bbox") or [0, 0])[1]),
            float((token.get("bbox") or [0, 0])[0]),
        ),
    )
    lines: list[dict[str, object]] = []
    for token in ordered:
        box = token.get("bbox") or [0, 0, 0, 0]
        y0 = float(box[1])
        y1 = float(box[3])
        center = (y0 + y1) / 2
        target = None
        for line in reversed(lines[-3:]):
            line_box = line["bbox"]
            line_center = (float(line_box[1]) + float(line_box[3])) / 2
            tolerance = max(4.0, min(float(box[3]) - y0, float(line_box[3]) - float(line_box[1])) * 0.65)
            if abs(center - line_center) <= tolerance:
                target = line
                break
        if target is None:
            lines.append(
                {
                    "text": str(token["text"]).strip(),
                    "bbox": list(box),
                    "confidence": token.get("confidence"),
                    "source": "ocr",
                    "tokens": [token],
                }
            )
        else:
            target["tokens"].append(token)
            target["tokens"].sort(key=lambda item: float((item.get("bbox") or [0])[0]))
            target["text"] = " ".join(str(item.get("text") or "").strip() for item in target["tokens"]).strip()
            boxes = [item.get("bbox") or [0, 0, 0, 0] for item in target["tokens"]]
            target["bbox"] = [
                round(min(float(item[0]) for item in boxes), 3),
                round(min(float(item[1]) for item in boxes), 3),
                round(max(float(item[2]) for item in boxes), 3),
                round(max(float(item[3]) for item in boxes), 3),
            ]
            confidences = [item.get("confidence") for item in target["tokens"] if item.get("confidence") is not None]
            target["confidence"] = min(confidences) if confidences else None
    return lines


def _rapidocr_tokens(image: Any, scale: float) -> list[dict[str, object]]:
    try:
        import numpy as np  # type: ignore
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
    except ImportError:
        return []
    engine = _rapidocr_engine()
    result, _ = engine(np.asarray(image))
    tokens: list[dict[str, object]] = []
    for item in result or ():
        if not isinstance(item, (list, tuple)) or len(item) < 3:
            continue
        box = _bbox_from_points(item[0])
        text = _clean_text(item[1])
        if not box or not text:
            continue
        tokens.append(
            {
                "text": text,
                "bbox": [round(value / scale, 3) for value in box],
                "confidence": round(float(item[2]), 4),
                "source": "rapidocr",
            }
        )
    return tokens


@lru_cache(maxsize=1)
def _rapidocr_engine() -> Any:
    from rapidocr_onnxruntime import RapidOCR  # type: ignore

    return RapidOCR()


def _pytesseract_tokens(image: Any, scale: float) -> list[dict[str, object]]:
    import pytesseract  # type: ignore
    from pytesseract import Output  # type: ignore

    configured_tesseract = os.getenv("TESSERACT_CMD", "").strip()
    if configured_tesseract:
        pytesseract.pytesseract.tesseract_cmd = configured_tesseract
    data = pytesseract.image_to_data(
        image,
        lang="vie+eng",
        output_type=Output.DICT,
    )
    tokens: list[dict[str, object]] = []
    for index, text in enumerate(data.get("text", [])):
        value = _clean_text(text)
        if not value:
            continue
        try:
            confidence = float(data.get("conf", ["-1"])[index]) / 100.0
        except (TypeError, ValueError, IndexError):
            confidence = None
        if confidence is not None and confidence < 0:
            confidence = None
        left = float(data.get("left", [0])[index]) / scale
        top = float(data.get("top", [0])[index]) / scale
        width = float(data.get("width", [0])[index]) / scale
        height = float(data.get("height", [0])[index]) / scale
        tokens.append(
            {
                "text": value,
                "bbox": [round(left, 3), round(top, 3), round(left + width, 3), round(top + height, 3)],
                "confidence": round(confidence, 4) if confidence is not None else None,
                "source": "pytesseract",
                "block_num": data.get("block_num", [None])[index],
                "par_num": data.get("par_num", [None])[index],
                "line_num": data.get("line_num", [None])[index],
            }
        )
    return tokens


def _ocr_page_layout(path: Any, page_index: int) -> tuple[str, list[dict[str, object]], str]:
    import fitz  # type: ignore
    from PIL import Image  # type: ignore

    configured_scale = 2.0
    with fitz.open(str(path)) as pdf:
        page = pdf.load_page(page_index)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(configured_scale, configured_scale), alpha=False)
        image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
    tokens: list[dict[str, object]] = []
    engine_name = "rapidocr"
    try:
        tokens = _rapidocr_tokens(image, configured_scale)
    except Exception:
        tokens = []
    if not tokens:
        engine_name = "pytesseract"
        tokens = _pytesseract_tokens(image, configured_scale)
    lines = _group_ocr_tokens(tokens)
    text = "\n".join(str(line.get("text") or "").strip() for line in lines if str(line.get("text") or "").strip()).strip()
    return text, tokens, engine_name


def _ocr_elements(tokens: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    elements: list[dict[str, object]] = []
    lines = _group_ocr_tokens(tokens)
    for index, line in enumerate(lines, start=1):
        text = str(line.get("text") or "").strip()
        marker = _list_marker(text)
        if marker is not None:
            ordered, _, item_text = marker
            elements.append(
                {
                    "type": "list_item",
                    "text": item_text,
                    "ordered": ordered,
                    "marker": text[: text.find(item_text)].strip(),
                    "bbox": line.get("bbox"),
                    "confidence": line.get("confidence"),
                    "source": "ocr",
                    "reading_order": index,
                }
            )
        else:
            elements.append(
                {
                    "type": "paragraph",
                    "text": text,
                    "bbox": line.get("bbox"),
                    "confidence": line.get("confidence"),
                    "source": "ocr",
                    "reading_order": index,
                }
            )
    return elements, lines


def _lists_from_elements(elements: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    lists: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for element in elements:
        if element.get("type") != "list_item":
            current = None
            continue
        ordered = bool(element.get("ordered"))
        if current is None or bool(current.get("ordered")) != ordered:
            current = {
                "list_id": f"list_{len(lists) + 1:03d}",
                "type": "list",
                "ordered": ordered,
                "items": [],
                "source": element.get("source", "native"),
            }
            lists.append(current)
        items = current["items"]
        items.append(
            {
                "index": len(items) + 1,
                "text": str(element.get("text") or "").strip(),
                "bbox": element.get("bbox"),
                "source": element.get("source", "native"),
                **({"confidence": element["confidence"]} if element.get("confidence") is not None else {}),
            }
        )
    return lists


def _looks_table_like(text: str) -> bool:
    return bool(_TABLE_HINT_RE.search(text) and (len(re.findall(r"\d{2,}", text)) >= 2 or "|" in text))


def _has_interleaved_columns(elements: list[dict[str, object]], page_width: float) -> bool:
    """Detect likely text columns without treating ordinary table cells as columns."""

    blocks = [
        element
        for element in elements
        if element.get("type") in {"heading", "paragraph", "list_item"} and element.get("bbox")
    ]
    if len(blocks) < 4 or page_width <= 0:
        return False
    left = [element for element in blocks if float(element["bbox"][0]) < page_width * 0.45]
    right = [element for element in blocks if float(element["bbox"][0]) > page_width * 0.55]
    if len(left) < 2 or len(right) < 2:
        return False
    left_y = sorted(float(element["bbox"][1]) for element in left)
    right_y = sorted(float(element["bbox"][1]) for element in right)
    return bool(left_y and right_y and max(left_y[0], right_y[0]) < min(float(element["bbox"][3]) for element in blocks))


def _table_header_row(row: list[str]) -> bool:
    joined = " ".join(row).casefold()
    if any(marker in joined for marker in ("mã ngành", "ma nganh", "tên ngành", "ten nganh", "học bạ", "hoc ba", "đgnl", "học phí", "hoc phi")):
        return True
    nonempty = [cell for cell in row if cell]
    return bool(nonempty) and sum(cell.upper() == cell and any(character.isalpha() for character in cell) for cell in nonempty) >= max(1, len(nonempty) - 1)


def _coordinate_table_from_tokens(
    tokens: list[dict[str, object]],
    *,
    page_number: int,
    source: str,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Reconstruct a conservative table from OCR coordinates.

    OCR is intentionally treated as a layout source, not as a flat string.
    The reconstruction only claims a table when several OCR lines contain
    multiple horizontally separated tokens.  Uneven rows are retained and
    marked partial instead of being silently discarded.
    """

    lines = [line for line in _group_ocr_tokens(tokens) if line.get("tokens")]
    if len(lines) < 3:
        return [], [], []
    token_rows: list[list[dict[str, object]]] = []
    for line in lines:
        row_tokens = sorted(
            [dict(token) for token in line.get("tokens", []) if str(token.get("text") or "").strip()],
            key=lambda token: float((token.get("bbox") or [0])[0]),
        )
        if len(row_tokens) >= 2:
            token_rows.append(row_tokens)
    if len(token_rows) < 3 or max(len(row) for row in token_rows) < 2:
        return [], [], []
    if not _looks_table_like("\n".join(str(token.get("text") or "") for row in token_rows for token in row)):
        return [], [], []

    # Paragraph lines can be much longer than table rows.  Prefer the
    # coordinate rows carrying numeric values, which are the strongest table
    # signal for scores, fees, phone numbers, quotas, and dates.  Keep a
    # preceding short header line when it is recognisable.
    strong_rows = [
        (index, row)
        for index, row in enumerate(token_rows)
        if sum(bool(re.search(r"\d{2,}", str(token.get("text") or ""))) for token in row) >= 2
    ]
    if len(strong_rows) < 3:
        return [], [], []
    if len(strong_rows) >= 3:
        # Restrict reconstruction to the longest vertically contiguous run of
        # numeric rows.  This prevents a date in prose above a real table from
        # turning the entire page into a false table.
        runs: list[list[list[dict[str, object]]]] = []
        current: list[list[dict[str, object]]] = []
        previous_y: float | None = None
        for _, row in strong_rows:
            y0 = float((row[0].get("bbox") or [0, 0])[1])
            if previous_y is not None and y0 - previous_y > 55:
                if current:
                    runs.append(current)
                current = []
            current.append(row)
            previous_y = y0
        if current:
            runs.append(current)
        bounded_rows = max(runs, key=len, default=[])
        bounded_rows = [row for row in bounded_rows if 2 <= len(row) <= 12]
        if len(bounded_rows) < 3:
            return [], [], []
        row_lengths = [len(row) for row in bounded_rows]
        mode_length = max(set(row_lengths), key=row_lengths.count)
        token_rows = [row for row in bounded_rows if abs(len(row) - mode_length) <= 2]
        if len(token_rows) < 3 or mode_length < 2:
            return [], [], []
        anchor = next(row for row in token_rows if len(row) == mode_length)
    else:
        anchor = max(token_rows, key=len)

    # A table's first visibly multi-token row is the best available column
    # anchor for scanned documents.  Later rows are assigned to the nearest
    # anchor while retaining their original token boxes and confidence.
    anchors = [float((token.get("bbox") or [0])[0]) for token in anchor]
    rows: list[list[dict[str, object]]] = []
    partial = False
    for row_tokens in token_rows:
        cells: list[list[dict[str, object]]] = [[] for _ in anchors]
        for token in row_tokens:
            x0 = float((token.get("bbox") or [0])[0])
            nearest = min(range(len(anchors)), key=lambda index: abs(anchors[index] - x0))
            cells[nearest].append(token)
        values: list[str] = []
        for cell_tokens in cells:
            value = " ".join(str(token.get("text") or "").strip() for token in cell_tokens).strip()
            values.append(value)
        if sum(bool(value) for value in values) < 2:
            partial = True
            continue
        if any(not value for value in values):
            partial = True
        rows.append([{"tokens": cell_tokens, "text": value} for cell_tokens, value in zip(cells, values)])
    if len(rows) < 3:
        return [], [], []

    first_values = [str(cell["text"]) for cell in rows[0]]
    header_detected = _table_header_row(first_values)
    headers = first_values if header_detected else [f"column_{index + 1}" for index in range(len(anchors))]
    data_rows = rows[1:] if header_detected else rows
    table_id = f"page_{page_number}_table_ocr_1"
    table_rows: list[dict[str, object]] = []
    for row_index, row in enumerate(data_rows, start=1):
        cells: list[dict[str, object]] = []
        for column_index, cell in enumerate(row):
            cell_tokens = cell["tokens"]
            boxes = [token.get("bbox") or [0, 0, 0, 0] for token in cell_tokens]
            confidences = [token.get("confidence") for token in cell_tokens if token.get("confidence") is not None]
            cell_box = None
            if boxes:
                cell_box = [
                    round(min(float(box[0]) for box in boxes), 3),
                    round(min(float(box[1]) for box in boxes), 3),
                    round(max(float(box[2]) for box in boxes), 3),
                    round(max(float(box[3]) for box in boxes), 3),
                ]
            cells.append(
                {
                    "row_index": row_index,
                    "column_index": column_index,
                    "header": headers[column_index],
                    "text": str(cell["text"]),
                    "bbox": cell_box,
                    "confidence": min(confidences) if confidences else None,
                    "source": source,
                }
            )
        values = [str(cell["text"]) for cell in cells]
        table_rows.append(
            {
                "row_index": row_index,
                "values": values,
                "cells": cells,
                "data": {headers[index]: value for index, value in enumerate(values)},
            }
        )
    table = {
        "type": "table",
        "table_id": table_id,
        "page_number": page_number,
        "bbox": None,
        "headers": headers,
        "rows": table_rows,
        "row_count": len(table_rows),
        "column_count": len(headers),
        "source": f"{source}_layout",
        "header_detected": header_detected,
        "reconstructed_from_ocr": True,
    }
    element = {
        "type": "table",
        "table_id": table_id,
        "text": " | ".join(headers),
        "bbox": None,
        "source": f"{source}_layout",
        "row_count": len(table_rows),
        "column_count": len(headers),
    }
    warnings: list[dict[str, object]] = []
    if partial:
        warnings.append(
            {
                "type": "PARTIAL_TABLE",
                "page": page_number,
                "message": "OCR table rows had uneven column occupancy; all OCR cells were retained with coordinates.",
            }
        )
    return [table], [element], warnings


def _native_tables(page: Any, page_number: int) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    tables: list[dict[str, object]] = []
    elements: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    try:
        finder = page.find_tables()
        raw_tables = list(getattr(finder, "tables", ()) or ())
    except Exception as exc:
        raw_tables = []
        warnings.append(
            {
                "type": "TABLE_EXTRACTION_FAILED",
                "page": page_number,
                "message": str(exc),
            }
        )
    for table_index, table in enumerate(raw_tables, start=1):
        table_id = f"page_{page_number}_table_{table_index}"
        extracted = [[_clean_text(cell) for cell in row] for row in (table.extract() or [])]
        extracted = [row for row in extracted if any(row)]
        header_row = extracted[0] if extracted and _table_header_row(extracted[0]) else []
        headers = header_row or [f"column_{index + 1}" for index in range(int(getattr(table, "col_count", 0) or (max((len(row) for row in extracted), default=0))))]
        data_rows = extracted[1:] if header_row else extracted
        cell_boxes = list(getattr(table, "cells", ()) or ())
        col_count = int(getattr(table, "col_count", 0) or len(headers))
        rows: list[dict[str, object]] = []
        for data_index, values in enumerate(data_rows):
            row_index = data_index + (1 if header_row else 0)
            cells: list[dict[str, object]] = []
            for column_index in range(max(col_count, len(values))):
                # PyMuPDF's ``cells`` follows the extracted matrix and does
                # not include an external header row.  Keep the source cell
                # bbox aligned even when the first row is promoted to headers.
                row_count = int(getattr(table, "row_count", 0) or len(extracted))
                raw_row_index = data_index + (1 if header_row else 0)
                # PyMuPDF exposes cells column-major: all row boxes for
                # column 0, then all row boxes for column 1, and so on.
                cell_index = column_index * row_count + raw_row_index
                value = values[column_index] if column_index < len(values) else ""
                cells.append(
                    {
                        "row_index": row_index,
                        "column_index": column_index,
                        "header": headers[column_index] if column_index < len(headers) else f"column_{column_index + 1}",
                        "text": value,
                        "bbox": _bbox(cell_boxes[cell_index]) if cell_index < len(cell_boxes) else None,
                    }
                )
            row_values = [cell["text"] for cell in cells]
            rows.append(
                {
                    "row_index": row_index,
                    "values": row_values,
                    "cells": cells,
                    "data": {
                        str(headers[index] if index < len(headers) else f"column_{index + 1}"): value
                        for index, value in enumerate(row_values)
                    },
                }
            )
        table_value = {
            "type": "table",
            "table_id": table_id,
            "page_number": page_number,
            "bbox": _bbox(getattr(table, "bbox", None)),
            "headers": headers,
            "rows": rows,
            "row_count": len(rows),
            "column_count": len(headers),
            "source": "native",
            "header_detected": bool(header_row),
        }
        tables.append(table_value)
        elements.append(
            {
                "type": "table",
                "table_id": table_id,
                "text": " | ".join(headers),
                "bbox": table_value["bbox"],
                "source": "native",
                "row_count": len(rows),
                "column_count": len(headers),
            }
        )
    return tables, elements, warnings


def _merge_text(native_text: str, ocr_text: str) -> tuple[str, bool]:
    native = _clean_text(native_text)
    ocr = _clean_text(ocr_text)
    if not native:
        return ocr, False
    if not ocr:
        return native, False
    folded_native = " ".join(native.casefold().split())
    folded_ocr = " ".join(ocr.casefold().split())
    if folded_ocr in folded_native:
        return native, False
    if folded_native in folded_ocr:
        return ocr, False
    native_numbers = set(re.findall(r"\d[\d.,]*", native))
    ocr_numbers = set(re.findall(r"\d[\d.,]*", ocr))
    conflict = bool(native_numbers and ocr_numbers and native_numbers != ocr_numbers)
    return f"{native}\n\n{ocr}".strip(), conflict


def extract_pdf_pages(path: Any) -> list[dict[str, object]]:
    """Extract native/OCR/layout content while retaining a complete page text."""

    try:
        import fitz  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency is part of requirements
        raise RuntimeError("PyMuPDF is required for layout-preserving PDF extraction") from exc

    pages: list[dict[str, object]] = []
    with fitz.open(str(path)) as pdf:
        for page_index in range(len(pdf)):
            page_number = page_index + 1
            page = pdf.load_page(page_index)
            native_elements, native_words = _native_elements(page)
            native_tables, table_elements, page_warnings = _native_tables(page, page_number)
            # The default PDF text order is usually the semantic order inside
            # tables.  For genuine non-table multi-column layouts, use the
            # coordinate-sorted order and emit a review warning below.
            if _has_interleaved_columns(native_elements, float(page.rect.width)) and not native_tables:
                native_text = _clean_text(page.get_text("text", sort=True) or "")
            else:
                native_text = _clean_text(page.get_text("text", sort=False) or "")
            image_blocks = [element for element in native_elements if element.get("type") == "image"]
            needs_ocr = not native_text or bool(image_blocks)
            ocr_text = ""
            ocr_tokens: list[dict[str, object]] = []
            ocr_engine = ""
            if needs_ocr:
                try:
                    ocr_text, ocr_tokens, ocr_engine = _ocr_page_layout(path, page_index)
                except Exception as exc:
                    page_warnings.append(
                        {
                            "type": "OCR_FAILED",
                            "page": page_number,
                            "message": str(exc),
                        }
                    )
            final_text, native_ocr_conflict = _merge_text(native_text, ocr_text)
            if native_ocr_conflict:
                page_warnings.append(
                    {
                        "type": "NATIVE_OCR_CONFLICT",
                        "page": page_number,
                        "message": "Native and OCR numeric tokens differ; both sources were retained.",
                    }
                )
            ocr_elements, ocr_lines = _ocr_elements(ocr_tokens)
            ocr_tables: list[dict[str, object]] = []
            ocr_table_elements: list[dict[str, object]] = []
            ocr_table_warnings: list[dict[str, object]] = []
            if not native_tables and _looks_table_like(final_text):
                if ocr_tokens:
                    ocr_tables, ocr_table_elements, ocr_table_warnings = _coordinate_table_from_tokens(
                        ocr_tokens,
                        page_number=page_number,
                        source="ocr",
                    )
                if not ocr_tables:
                    native_tables_fallback, native_table_elements, native_table_warnings = _coordinate_table_from_tokens(
                        native_words,
                        page_number=page_number,
                        source="native",
                    )
                    ocr_tables = native_tables_fallback
                    ocr_table_elements = native_table_elements
                    ocr_table_warnings = native_table_warnings
                page_warnings.extend(ocr_table_warnings)
            elements = native_elements + ocr_elements + table_elements + ocr_table_elements
            lists = _lists_from_elements(elements)
            tables = native_tables + ocr_tables
            if not tables and _looks_table_like(final_text):
                page_warnings.append(
                    {
                        "type": "UNPARSED_TABLE",
                        "page": page_number,
                        "message": "Table-like content was retained in page text but no native table relation was detected.",
                    }
                )
            if ocr_tokens and any(
                token.get("confidence") is not None and float(token["confidence"]) < 0.75
                for token in ocr_tokens
            ):
                page_warnings.append(
                    {
                        "type": "LOW_OCR_CONFIDENCE",
                        "page": page_number,
                        "message": "At least one OCR token has confidence below 0.75.",
                    }
                )
            if _has_interleaved_columns(native_elements, float(page.rect.width)):
                page_warnings.append(
                    {
                        "type": "READING_ORDER_UNCERTAIN",
                        "page": page_number,
                        "message": "Multiple horizontal layout regions were detected; inspect reading order.",
                    }
                )
            if needs_ocr and not ocr_text:
                page_warnings.append(
                    {
                        "type": "OCR_EMPTY_OR_LOW_QUALITY",
                        "page": page_number,
                        "message": "OCR was attempted for a page with image/empty native content but returned no usable text.",
                    }
                )
            extraction_method = "native" if native_text and not ocr_text else ("ocr" if ocr_text and not native_text else "mixed")
            page_value: dict[str, object] = {
                "page": page_number,
                "page_number": page_number,
                "text": final_text,
                "native_text": native_text,
                "ocr_text": ocr_text,
                "native_blocks": [
                    {
                        "bbox": element.get("bbox"),
                        "text": element.get("text", ""),
                        "type": element.get("type"),
                        "block_index": element.get("block_index"),
                    }
                    for element in native_elements
                    if element.get("type") != "table"
                ],
                "native_words": native_words,
                "ocr_boxes": ocr_tokens,
                "ocr_lines": ocr_lines,
                "elements": elements,
                "tables": tables,
                "lists": lists,
                "extraction_method": extraction_method,
                "ocr_engine": ocr_engine,
            }
            if page_warnings:
                page_value["warnings"] = page_warnings
            pages.append(page_value)
    if not any(str(page.get("text") or "").strip() for page in pages):
        raise ValueError("PDF has no extractable text")
    return pages


__all__ = ["extract_pdf_pages"]
