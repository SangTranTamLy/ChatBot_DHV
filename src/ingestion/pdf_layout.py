"""Layout-preserving PDF extraction helpers.

The ingestion boundary keeps the page text used by the RAG pipeline, but also
retains the native/OCR layout objects that produced that text.  Nothing in
this module is allowed to silently discard a page, table, list, or OCR token.
"""

from __future__ import annotations

from functools import lru_cache
from difflib import SequenceMatcher
import os
import re
import unicodedata
from typing import Any, Iterable


_LIST_MARKER_RE = re.compile(r"^\s*(?:(?P<bullet>[-•●▪◦*])|(?P<number>\d+[.)]))\s+(?P<text>.+?)\s*$")
_URL_RE = re.compile(r"https?://[^\s)>]+", re.IGNORECASE)
_URL_HYPHEN_WRAP_RE = re.compile(r"(https?://[^\s<>\"']*?)-\s+([A-Za-z0-9])", re.IGNORECASE)
_TABLE_HINT_RE = re.compile(
    r"\b(?:mã\s+ngành|ma\s+nganh|mã\s+xét\s+tuyển|ma\s+xet\s+tuyen|"
    r"tên\s+ngành|ten\s+nganh|tên\s+mã\s+xét\s+tuyển|ten\s+ma\s+xet\s+tuyen|"
    r"điểm\s+chuẩn|diem\s+chuan|học\s+bạ|hoc\s+ba|đgnl|học\s+phí|hoc\s+phi|"
    r"khoản\s+thu|khoan\s+thu|mức\s+phí|muc\s+phi|sđt/zalo|sdt/zalo)\b",
    re.IGNORECASE,
)


def _clean_text(value: object) -> str:
    text = str(value or "").replace("\u00a0", " ").replace("\u00ad", "")
    # PDF line wrapping can split a URL immediately after a hyphen even when
    # PyMuPDF emits a plain space instead of a newline. Repair only inside a
    # URL token; ordinary hyphenated prose keeps its spacing.
    text = _URL_HYPHEN_WRAP_RE.sub(r"\1-\2", text)
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


def _row_data(headers: list[str], values: list[str]) -> dict[str, str]:
    """Build a convenience mapping without losing cells under duplicate headers."""

    result: dict[str, str] = {}
    occurrences: dict[str, int] = {}
    for index, value in enumerate(values):
        base = str(headers[index]).strip() if index < len(headers) else f"column_{index + 1}"
        base = base or f"column_{index + 1}"
        occurrences[base] = occurrences.get(base, 0) + 1
        key = base if occurrences[base] == 1 else f"{base} [{occurrences[base]}]"
        result[key] = value
    return result


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
        for line_index, line in enumerate(block.get("lines", []) or (), start=1):
            span_text: list[str] = []
            max_font_size = 0.0
            for span in line.get("spans", []) or ():
                span_text.append(str(span.get("text") or ""))
                try:
                    max_font_size = max(max_font_size, float(span.get("size") or 0.0))
                except (TypeError, ValueError):
                    pass
            value = _clean_text("".join(span_text))
            if not value:
                continue
            marker = _list_marker(value)
            if marker is not None:
                ordered, _, item_text = marker
                # Numbered section titles such as ``1. OVERVIEW`` are
                # headings, not one-item ordered lists. Preserve actual
                # numbered content as list items.
                if ordered and _looks_like_heading(item_text, max_font_size):
                    element_type = "heading"
                    element_text = value
                    extra = {}
                else:
                    element_type = "list_item"
                    element_text = item_text
                    extra = {"ordered": ordered, "marker": value[: value.find(item_text)].strip()}
            elif re.match(r"^\d+(?:\.\d+)+\s+", value):
                element_type = "heading"
                element_text = value
                extra = {}
            elif _looks_like_heading(value, max_font_size):
                element_type = "heading"
                element_text = value
                extra = {}
            else:
                element_type = "paragraph"
                element_text = value
                extra = {}
            elements.append(
                {
                    "type": element_type,
                    "text": element_text,
                    "bbox": _bbox(line.get("bbox")) or block_box,
                    "source": "native",
                    "block_index": block_index,
                    "line_index": line_index,
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
    available_languages = set(pytesseract.get_languages(config=""))
    if {"vie", "eng"}.issubset(available_languages):
        language = "vie+eng"
    elif "vie" in available_languages:
        language = "vie"
    elif "eng" in available_languages:
        # Do not fail the whole extraction when only English traineddata is
        # installed. The caller records this reduced-language path as a QA
        # warning; raw OCR text and confidence remain available for review.
        language = "eng"
    else:
        raise RuntimeError("Tesseract has no usable language data (expected vie and/or eng).")
    data = pytesseract.image_to_data(
        image,
        lang=language,
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
                "language": language,
                "block_num": data.get("block_num", [None])[index],
                "par_num": data.get("par_num", [None])[index],
                "line_num": data.get("line_num", [None])[index],
            }
        )
    return tokens


def _ocr_page_layout(
    path: Any,
    page_index: int,
    *,
    image_regions: Iterable[object] | None = None,
) -> tuple[str, list[dict[str, object]], str, list[str]]:
    """OCR a full scan or only embedded image regions on a native-text page.

    Image OCR is clipped to the image bounding boxes so the OCR pass does not
    re-read and append the native page text a second time. Token boxes are
    translated back into PDF page coordinates before serialization.
    """

    import fitz  # type: ignore
    from PIL import Image  # type: ignore

    configured_scale = 2.0
    with fitz.open(str(path)) as pdf:
        page = pdf.load_page(page_index)
        regions = list(image_regions or ())
        clips = [fitz.Rect(region) for region in regions if region]
        clips = [clip & page.rect for clip in clips]
        clips = [clip for clip in clips if not clip.is_empty and clip.width > 0 and clip.height > 0]
        unique_clips: list[Any] = []
        seen_clips: set[tuple[float, float, float, float]] = set()
        for clip in clips:
            key = tuple(round(float(value), 1) for value in clip)
            if key not in seen_clips:
                seen_clips.add(key)
                unique_clips.append(clip)
        clips = unique_clips
        # A fully scanned page has no usable native text; OCR the complete page
        # so text outside raster-image blocks cannot be lost.
        if not clips:
            clips = [page.rect]

    tokens: list[dict[str, object]] = []
    engines: list[str] = []
    failures: list[str] = []
    with fitz.open(str(path)) as pdf:
        page = pdf.load_page(page_index)
        for clip in clips:
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(configured_scale, configured_scale),
                clip=clip,
                alpha=False,
            )
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            region_tokens: list[dict[str, object]] = []
            engine_name = "rapidocr"
            rapidocr_error: str | None = None
            try:
                region_tokens = _rapidocr_tokens(image, configured_scale)
            except Exception as exc:
                region_tokens = []
                rapidocr_error = str(exc)
            if not region_tokens:
                engine_name = "pytesseract"
                try:
                    region_tokens = _pytesseract_tokens(image, configured_scale)
                except Exception as exc:
                    failure = f"Tesseract failed for image region {tuple(clip)}: {exc}"
                    if rapidocr_error:
                        failure = f"RapidOCR failed: {rapidocr_error}; {failure}"
                    failures.append(failure)
                    region_tokens = []
                languages = sorted(
                    {str(token.get("language")) for token in region_tokens if token.get("language")}
                )
                if languages:
                    engine_name = f"pytesseract[{'+'.join(languages)}]"
            if region_tokens and engine_name not in engines:
                engines.append(engine_name)
            # Pixmap origins are pixel coordinates; convert the crop origin
            # back to the PDF page coordinate system and offset every token.
            offset_x = float(pixmap.x) / configured_scale
            offset_y = float(pixmap.y) / configured_scale
            for token in region_tokens:
                value = dict(token)
                box = value.get("bbox")
                if isinstance(box, (list, tuple)) and len(box) == 4:
                    value["bbox"] = [
                        round(float(box[0]) + offset_x, 3),
                        round(float(box[1]) + offset_y, 3),
                        round(float(box[2]) + offset_x, 3),
                        round(float(box[3]) + offset_y, 3),
                    ]
                tokens.append(value)
    lines = _group_ocr_tokens(tokens)
    text = "\n".join(str(line.get("text") or "").strip() for line in lines if str(line.get("text") or "").strip()).strip()
    engine = "+".join(engines)
    return text, tokens, engine, failures


def _line_identity(line: dict[str, object]) -> tuple[str, tuple[float, ...]]:
    box = line.get("bbox") or ()
    return (
        _matching_text(str(line.get("text") or "")),
        tuple(round(float(value), 1) for value in box) if isinstance(box, (list, tuple)) else (),
    )


def _ocr_elements(
    tokens: list[dict[str, object]],
    *,
    included_lines: set[tuple[str, tuple[float, ...]]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    elements: list[dict[str, object]] = []
    lines = _group_ocr_tokens(tokens)
    for index, line in enumerate(lines, start=1):
        if included_lines is not None and _line_identity(line) not in included_lines:
            continue
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


def _merge_list_continuations(elements: list[dict[str, object]]) -> list[dict[str, object]]:
    """Attach only strongly-indented, adjacent wrapped lines to a list item.

    Ambiguous paragraphs stay as paragraphs: page text is still preserved, and
    losing a structural merge is safer than silently moving prose into a list.
    """

    merged: list[dict[str, object]] = []
    previous_item: dict[str, object] | None = None
    for original in elements:
        element = dict(original)
        if element.get("type") == "paragraph" and previous_item is not None:
            previous_box = previous_item.get("bbox")
            current_box = element.get("bbox")
            if (
                previous_item.get("source") == element.get("source")
                and isinstance(previous_box, (list, tuple))
                and len(previous_box) == 4
                and isinstance(current_box, (list, tuple))
                and len(current_box) == 4
            ):
                vertical_gap = float(current_box[1]) - float(previous_box[3])
                previous_left = float(previous_box[0])
                current_left = float(current_box[0])
                indent_delta = current_left - previous_left
                previous_width = max(1.0, float(previous_box[2]) - previous_left)
                current_width = max(1.0, float(current_box[2]) - current_left)
                horizontal_overlap = min(float(previous_box[2]), float(current_box[2])) - max(
                    previous_left, current_left
                )
                continuation_text = str(element.get("text") or "").strip()
                previous_text = str(previous_item.get("text") or "").rstrip()
                begins_as_continuation = bool(
                    continuation_text
                    and (
                        continuation_text[0].islower()
                        or previous_text.endswith((",", "-", "–"))
                    )
                )
                previous_is_open = bool(previous_text and previous_text[-1] not in ".!?;:")
                line_height = max(1.0, float(previous_box[3]) - float(previous_box[1]))
                plausible_wrap = (
                    8.0 <= indent_delta <= 36.0
                    and horizontal_overlap > 0
                    and begins_as_continuation
                    and previous_is_open
                    and previous_width >= 28.0
                    and current_width >= 8.0
                )
                maximum_gap = min(10.0, line_height * 0.75)
                if 0 <= vertical_gap <= maximum_gap and plausible_wrap:
                    prior_text = str(previous_item.get("text") or "").rstrip()
                    previous_item["text"] = f"{prior_text} {continuation_text}".strip()
                    previous_item["bbox"] = [
                        round(min(float(previous_box[0]), float(current_box[0])), 3),
                        round(min(float(previous_box[1]), float(current_box[1])), 3),
                        round(max(float(previous_box[2]), float(current_box[2])), 3),
                        round(max(float(previous_box[3]), float(current_box[3])), 3),
                    ]
                    continue
        merged.append(element)
        previous_item = element if element.get("type") == "list_item" else None
    return merged


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
    if sum("|" in line for line in text.splitlines()) >= 3 and _TABLE_HINT_RE.search(text):
        return True
    folded = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    header_groups = (
        ("ma nganh", "ten nganh"),
        ("ma nganh", "ten chuong trinh", "chi tieu"),
        ("ma xet tuyen", "ten ma xet tuyen"),
        ("khoan thu", "muc phi"),
        ("hoc bong dau vao", "ho tro hki"),
        ("so luong tan sinh vien", "muc ho tro hkii"),
        ("ten zalo", "sdt/zalo"),
    )
    # A run of numbered prose (deadlines, score formulas, scholarship tiers)
    # is not sufficient evidence of a table. Require a recognizable pair of
    # table headers, or repeated coded rows such as admission/major codes.
    if any(all(header in folded for header in group) for group in header_groups):
        return True
    code_rows = [
        line
        for line in text.splitlines()
        if re.search(r"(?<!\d)\d{7,9}(?!\d)", line)
        and len(re.findall(r"(?<!\w)\d+(?:[.,]\d+)?%?(?!\w)", line)) >= 2
    ]
    return len(code_rows) >= 3


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


def _elements_outside_tables(
    elements: list[dict[str, object]],
    tables: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Exclude text cells already represented by a structured native table.

    Column-like positions inside a successfully extracted table do not make
    the page's reading order uncertain: table headers, rows, and cells retain
    their own explicit order/geometry. Only non-table content should feed the
    multi-column warning heuristic.
    """

    table_boxes = [
        box
        for table in tables
        if isinstance(table, dict)
        and (box := _bbox(table.get("bbox"))) is not None
    ]
    if not table_boxes:
        return elements
    retained: list[dict[str, object]] = []
    for element in elements:
        box = _bbox(element.get("bbox"))
        if box is None:
            retained.append(element)
            continue
        center_x = (box[0] + box[2]) / 2
        center_y = (box[1] + box[3]) / 2
        if any(x0 <= center_x <= x1 and y0 <= center_y <= y1 for x0, y0, x1, y1 in table_boxes):
            continue
        retained.append(element)
    return retained


def _table_header_row(row: list[str]) -> bool:
    joined = " ".join(row).casefold()
    if any(
        marker in joined
        for marker in (
            "mã ngành",
            "ma nganh",
            "tên ngành",
            "ten nganh",
            "học bạ",
            "hoc ba",
            "đgnl",
            "học phí",
            "hoc phi",
            "khoản thu",
            "khoan thu",
            "mức phí",
            "muc phi",
            "tên zalo",
            "ten zalo",
            "sđt/zalo",
            "sdt/zalo",
            "học bổng đầu vào",
            "hoc bong dau vao",
            "hỗ trợ hki",
            "ho tro hki",
            "hki cần đóng",
            "hki can dong",
            "giảm tiếp hkii",
            "giam tiep hkii",
            "tổng ưu đãi",
            "tong uu dai",
            "số lượng tân sinh viên",
            "so luong tan sinh vien",
            "mức hỗ trợ hkii",
            "muc ho tro hkii",
        )
    ):
        return True
    nonempty = [cell for cell in row if cell]
    return bool(nonempty) and sum(cell.upper() == cell and any(character.isalpha() for character in cell) for cell in nonempty) >= max(1, len(nonempty) - 1)


def _coordinate_table_from_tokens(
    tokens: list[dict[str, object]],
    *,
    page_number: int,
    source: str,
    native_text: str = "",
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Reconstruct a conservative table from OCR coordinates.

    OCR is intentionally treated as a layout source, not as a flat string.
    The reconstruction only claims a table when several OCR lines contain
    multiple horizontally separated tokens.  Uneven rows are retained and
    marked partial instead of being silently discarded.
    """

    warnings: list[dict[str, object]] = []
    untrusted_lines = 0
    if source == "ocr":
        tokens, low_confidence_lines, conflicting_lines = _filter_ocr_table_tokens(native_text, tokens)
        untrusted_lines = low_confidence_lines + conflicting_lines
        if untrusted_lines:
            reasons = []
            if low_confidence_lines:
                reasons.append(f"{low_confidence_lines} low-confidence line(s)")
            if conflicting_lines:
                reasons.append(f"{conflicting_lines} numeric-conflict line(s)")
            warnings.append(
                {
                    "type": "OCR_TABLE_CONTENT_UNTRUSTED",
                    "page": page_number,
                    "message": (
                        "OCR lines were retained in raw OCR fields but excluded from structured table cells: "
                        + ", ".join(reasons)
                        + "."
                    ),
                }
            )

    lines = [line for line in _group_ocr_tokens(tokens) if line.get("tokens")]
    if len(lines) < 3:
        return [], [], warnings
    token_rows: list[list[dict[str, object]]] = []
    for line in lines:
        row_tokens = sorted(
            [dict(token) for token in line.get("tokens", []) if str(token.get("text") or "").strip()],
            key=lambda token: float((token.get("bbox") or [0])[0]),
        )
        if len(row_tokens) >= 2:
            token_rows.append(row_tokens)
    if len(token_rows) < 3 or max(len(row) for row in token_rows) < 2:
        return [], [], warnings
    if not _looks_table_like("\n".join(str(line.get("text") or "") for line in lines)):
        return [], [], warnings

    # Paragraph lines can be much longer than table rows.  Prefer the
    # coordinate rows carrying numeric values, which are the strongest table
    # signal for scores, fees, phone numbers, quotas, and dates.  Keep a
    # preceding short header line when it is recognisable.
    all_token_rows = token_rows
    strong_rows = [
        (index, row)
        for index, row in enumerate(all_token_rows)
        if sum(bool(re.search(r"\d{2,}", str(token.get("text") or ""))) for token in row) >= 2
    ]
    if len(strong_rows) < 3:
        return [], [], warnings
    if len(strong_rows) >= 3:
        # Restrict reconstruction to the longest vertically contiguous run of
        # numeric rows.  This prevents a date in prose above a real table from
        # turning the entire page into a false table.
        runs: list[list[tuple[int, list[dict[str, object]]]]] = []
        current: list[tuple[int, list[dict[str, object]]]] = []
        previous_y: float | None = None
        for row_index, row in strong_rows:
            y0 = float((row[0].get("bbox") or [0, 0])[1])
            if previous_y is not None and y0 - previous_y > 55:
                if current:
                    runs.append(current)
                current = []
            current.append((row_index, row))
            previous_y = y0
        if current:
            runs.append(current)
        bounded_rows = max(runs, key=len, default=[])
        bounded_rows = [(index, row) for index, row in bounded_rows if 2 <= len(row) <= 12]
        if len(bounded_rows) < 3:
            return [], [], warnings
        row_lengths = [len(row) for _, row in bounded_rows]
        mode_length = max(set(row_lengths), key=row_lengths.count)
        selected_rows = [item for item in bounded_rows if abs(len(item[1]) - mode_length) <= 2]
        if len(selected_rows) < 3 or mode_length < 2:
            return [], [], warnings
        anchor = next(row for _, row in selected_rows if len(row) == mode_length)
        token_rows = [row for _, row in selected_rows]
    else:
        anchor = max(token_rows, key=len)

    # A table's first visibly multi-token row is the best available column
    # anchor for scanned documents.  Later rows are assigned to the nearest
    # anchor while retaining their original token boxes and confidence.
    anchors = [float((token.get("bbox") or [0])[0]) for token in anchor]
    if source == "native" and len(anchors) > 8:
        warnings.append(
            {
                "type": "TABLE_RECONSTRUCTION_REJECTED",
                "page": page_number,
                "message": "Native word-layout candidate produced more than eight apparent columns; kept the source text and declined to invent a table schema.",
            }
        )
        return [], [], warnings
    if strong_rows:
        first_data_index = min(index for index, _ in selected_rows)
        data_top = min(float((token.get("bbox") or [0, 0])[1]) for token in selected_rows[0][1])
        preceding = [
            (index, row)
            for index, row in enumerate(all_token_rows[:first_data_index])
            if row and data_top - max(float((token.get("bbox") or [0, 0, 0, 0])[3]) for token in row) <= 36
        ]
        if preceding:
            _, header_candidate = max(
                preceding,
                key=lambda item: max(float((token.get("bbox") or [0, 0])[1]) for token in item[1]),
            )
            header_cells: list[list[dict[str, object]]] = [[] for _ in anchors]
            for token in header_candidate:
                x0 = float((token.get("bbox") or [0])[0])
                nearest = min(range(len(anchors)), key=lambda index: abs(anchors[index] - x0))
                header_cells[nearest].append(token)
            header_values = [
                " ".join(str(token.get("text") or "").strip() for token in cell).strip()
                for cell in header_cells
            ]
            if _table_header_row(header_values):
                token_rows = [header_candidate, *token_rows]
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
        return [], [], warnings

    first_values = [str(cell["text"]) for cell in rows[0]]
    header_detected = _table_header_row(first_values)
    if source == "native" and not header_detected:
        warnings.append(
            {
                "type": "TABLE_RECONSTRUCTION_REJECTED",
                "page": page_number,
                "message": "Native word-layout candidate lacks a defensible header row; kept the source text and declined to infer column names.",
            }
        )
        return [], [], warnings
    headers = first_values if header_detected else [f"column_{index + 1}" for index in range(len(anchors))]
    data_rows = rows[1:] if header_detected else rows
    table_id = f"page_{page_number}_table_{source}_layout_1"
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
                "data": _row_data(headers, values),
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
        "reconstructed_from_ocr": source == "ocr",
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
    partial = partial or bool(untrusted_lines)
    if partial:
        warnings.append(
            {
                "type": "PARTIAL_TABLE",
                "page": page_number,
                "message": (
                    f"{source.title()} table reconstruction is partial because rows are uneven or untrusted lines were excluded; "
                    "the page text and source tokens remain available for review."
                ),
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
                    "data": _row_data(headers, row_values),
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
    additions, conflict = _supplemental_ocr_lines(
        native,
        [{"text": line.strip(), "confidence": 1.0} for line in ocr.splitlines() if line.strip()],
        minimum_confidence=0.0,
    )
    if not additions:
        return native, conflict
    addition_text = "\n".join(str(line.get("text") or "").strip() for line in additions)
    return f"{native}\n\n{addition_text}".strip(), conflict


def _matching_text(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold().replace("đ", "d"))
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", folded.encode("ascii", "ignore").decode("ascii")))


def _number_signature(text: str) -> tuple[str, ...]:
    """Normalize Vietnamese decimal/thousands punctuation for OCR comparisons."""

    values: list[str] = []
    for token in re.findall(r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)", text):
        value = token
        if "." in value and "," in value:
            decimal_mark = "." if value.rfind(".") > value.rfind(",") else ","
            integer_part, decimal_part = value.rsplit(decimal_mark, 1)
            value = re.sub(r"[.,]", "", integer_part) + "." + decimal_part
        elif "." in value or "," in value:
            mark = "." if "." in value else ","
            left, right = value.rsplit(mark, 1)
            if len(right) == 3 and len(left) <= 3:
                value = left + right
            else:
                value = left + "." + right
        try:
            from decimal import Decimal

            values.append(format(Decimal(value).normalize(), "f"))
        except Exception:
            values.append(value)
    return tuple(values)


def _native_text_windows(native_text: str) -> list[str]:
    native_lines = [line.strip() for line in native_text.splitlines() if line.strip()]
    windows = list(native_lines)
    windows.extend(
        " ".join(native_lines[index : index + window])
        for window in (2, 3)
        for index in range(max(0, len(native_lines) - window + 1))
    )
    return windows


def _ocr_text_conflicts_with_native(ocr_text: str, native_windows: list[str]) -> bool:
    """Detect a near-duplicate OCR line whose numeric facts disagree."""

    ocr_key = _matching_text(ocr_text)
    ocr_numbers = _number_signature(ocr_text)
    if not ocr_key or not ocr_numbers:
        return False
    for native_line in native_windows:
        native_key = _matching_text(native_line)
        if not native_key:
            continue
        similar = (
            ocr_key == native_key
            or (len(ocr_key) >= 12 and (ocr_key in native_key or native_key in ocr_key))
            or (
                min(len(ocr_key), len(native_key)) >= 18
                and SequenceMatcher(None, ocr_key, native_key, autojunk=False).ratio() >= 0.90
            )
        )
        if not similar:
            continue
        native_numbers = _number_signature(native_line)
        if native_numbers and native_numbers != ocr_numbers:
            return True
    return False


def _filter_ocr_table_tokens(
    native_text: str,
    tokens: list[dict[str, object]],
    *,
    minimum_confidence: float = 0.75,
) -> tuple[list[dict[str, object]], int, int]:
    """Return only OCR lines safe enough to expose as structured table cells."""

    native_windows = _native_text_windows(native_text)
    accepted: list[dict[str, object]] = []
    low_confidence_lines = 0
    conflicting_lines = 0
    for line in _group_ocr_tokens(tokens):
        line_tokens = [dict(token) for token in line.get("tokens", []) if str(token.get("text") or "").strip()]
        if not line_tokens:
            continue
        confidences: list[float] = []
        for token in line_tokens:
            try:
                confidence = float(token.get("confidence"))
            except (TypeError, ValueError):
                confidence = -1.0
            confidences.append(confidence)
        if any(confidence < minimum_confidence for confidence in confidences):
            low_confidence_lines += 1
            continue
        line_text = str(line.get("text") or "").strip()
        if native_windows and _ocr_text_conflicts_with_native(line_text, native_windows):
            conflicting_lines += 1
            continue
        accepted.extend(line_tokens)
    return accepted, low_confidence_lines, conflicting_lines


def _supplemental_ocr_lines(
    native_text: str,
    ocr_lines: list[dict[str, object]],
    *,
    minimum_confidence: float = 0.75,
) -> tuple[list[dict[str, object]], bool]:
    """Keep unique, sufficiently confident image OCR for native-text pages."""

    if not native_text.strip():
        return list(ocr_lines), False
    native_windows = _native_text_windows(native_text)
    native_keys = [_matching_text(line) for line in native_windows]
    additions: list[dict[str, object]] = []
    conflicts = False
    for line in ocr_lines:
        confidence = line.get("confidence")
        if confidence is None or float(confidence) < minimum_confidence:
            continue
        ocr_text = str(line.get("text") or "").strip()
        ocr_key = _matching_text(ocr_text)
        if not ocr_key:
            continue
        duplicate = False
        for native_line, native_key in zip(native_windows, native_keys):
            if not native_key:
                continue
            if ocr_key == native_key or (len(ocr_key) >= 12 and (ocr_key in native_key or native_key in ocr_key)):
                duplicate = True
            elif min(len(ocr_key), len(native_key)) >= 18 and SequenceMatcher(None, ocr_key, native_key, autojunk=False).ratio() >= 0.90:
                duplicate = True
            else:
                continue
            if duplicate:
                break
        if _ocr_text_conflicts_with_native(ocr_text, native_windows):
            conflicts = True
            continue
        if not duplicate:
            additions.append(line)
    return additions, conflicts


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
            image_regions = [element.get("bbox") for element in image_blocks if element.get("bbox")]
            needs_ocr = not native_text or bool(image_regions)
            ocr_text = ""
            ocr_tokens: list[dict[str, object]] = []
            ocr_engine = ""
            if needs_ocr:
                try:
                    ocr_text, ocr_tokens, ocr_engine, ocr_failures = _ocr_page_layout(
                        path,
                        page_index,
                        image_regions=image_regions if native_text else None,
                    )
                    for failure in ocr_failures:
                        page_warnings.append(
                            {
                                "type": "OCR_REGION_FAILED" if ocr_tokens else "OCR_FAILED",
                                "page": page_number,
                                "message": failure,
                            }
                        )
                except Exception as exc:
                    page_warnings.append(
                        {
                            "type": "OCR_FAILED",
                            "page": page_number,
                            "message": str(exc),
                        }
                    )
            raw_ocr_lines = _group_ocr_tokens(ocr_tokens)
            if native_text:
                supplemental_lines, native_ocr_conflict = _supplemental_ocr_lines(
                    native_text,
                    raw_ocr_lines,
                )
            else:
                supplemental_lines, native_ocr_conflict = raw_ocr_lines, False
            final_text = native_text
            supplemental_text = "\n".join(
                str(line.get("text") or "").strip()
                for line in supplemental_lines
                if str(line.get("text") or "").strip()
            )
            if supplemental_text:
                final_text = f"{native_text}\n\n{supplemental_text}".strip() if native_text else supplemental_text
            if native_ocr_conflict:
                page_warnings.append(
                    {
                        "type": "NATIVE_OCR_CONFLICT",
                        "page": page_number,
                        "message": "Conflicting OCR was retained in ocr_text/ocr_boxes but excluded from final text; review the source image.",
                    }
                )
            if "pytesseract[eng]" in ocr_engine:
                page_warnings.append(
                    {
                        "type": "OCR_LANGUAGE_FALLBACK",
                        "page": page_number,
                        "message": "Only English Tesseract data was available; Vietnamese OCR coverage may be incomplete.",
                    }
                )
            supplemental_keys = {_line_identity(line) for line in supplemental_lines}
            ocr_elements, ocr_lines = _ocr_elements(ocr_tokens, included_lines=supplemental_keys)
            ocr_tables: list[dict[str, object]] = []
            ocr_table_elements: list[dict[str, object]] = []
            ocr_table_warnings: list[dict[str, object]] = []
            if not native_tables and (bool(ocr_tokens) or _looks_table_like(final_text)):
                if ocr_tokens:
                    ocr_tables, ocr_table_elements, ocr_table_warnings = _coordinate_table_from_tokens(
                        ocr_tokens,
                        page_number=page_number,
                        source="ocr",
                        native_text=native_text,
                    )
                if not ocr_tables and _looks_table_like(final_text):
                    native_tables_fallback, native_table_elements, native_table_warnings = _coordinate_table_from_tokens(
                        native_words,
                        page_number=page_number,
                        source="native",
                    )
                    ocr_tables = native_tables_fallback
                    ocr_table_elements = native_table_elements
                    ocr_table_warnings.extend(native_table_warnings)
                page_warnings.extend(ocr_table_warnings)
            elements = _merge_list_continuations(
                native_elements + ocr_elements + table_elements + ocr_table_elements
            )
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
            if _has_interleaved_columns(
                _elements_outside_tables(native_elements, native_tables),
                float(page.rect.width),
            ):
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
                "page_bbox": [round(float(value), 3) for value in page.rect],
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
