"""Data Exporter Service - exports crawled data to various formats.

Provides utilities for exporting structured data (records as dictionaries)
to Excel files with automatic column detection and formatting.
"""
from pathlib import Path
from typing import Iterable, Mapping
from loguru import logger
from openpyxl import Workbook


def export_to_excel(rows: Iterable[Mapping], path: Path) -> Path:
    """Export a list of dictionaries to an Excel file.

        Automatically detects columns, creates a header row, and fills data.
        Handles empty data gracefully.

        Args:
            rows: Iterable of record dictionaries to export.
            path: Output file path (must be .xlsx).

        Returns:
            The path to the created Excel file.
        """
    wb = Workbook()
    ws = wb.active
    ws.title = "data"

    rows = list(rows)
    if not rows:
        wb.save(path)
        logger.info(f"Excel 为空数据，已创建文件: {path}")
        return path

    # 统一列顺序
    columns = sorted({k for row in rows for k in row.keys()})
    ws.append(columns)
    for row in rows:
        ws.append([row.get(col, "") for col in columns])

    wb.save(path)
    logger.info(f"Excel 导出完成: {path}")
    return path
