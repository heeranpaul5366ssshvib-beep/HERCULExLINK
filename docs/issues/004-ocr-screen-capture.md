# Issue 004 — OCR & Screen-Capture Adapter

Priority: Medium
Estimate: 1–2 person-weeks

Goal
- Implement a screen-capture + OCR adapter to enable UI understanding and text extraction from screen regions.

Acceptance criteria
- A `perception/vision/screen_adapter.py` that captures screenshots and returns images.
- An OCR adapter (Tesseract or alternative) that converts images to text with bounding boxes.
- Integration demo that extracts text from a selected region.

Files to change (suggested)
- `perception/vision/vision_processor.py` — add connector to screen adapter
- `perception/vision/` — add `screen_adapter.py`, `ocr_adapter.py`
