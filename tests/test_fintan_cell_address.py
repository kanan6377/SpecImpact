from specimpact.benchmarks.fintan import _has_cell_range


def test_cell_range_validation_requires_real_excel_address() -> None:
    assert _has_cell_range("[設計書.xlsx / シート1!A1:D20] [B12] プロジェクト名")
    assert _has_cell_range("[シート1!AD62] 項目")
    assert not _has_cell_range("approval!]")
    assert not _has_cell_range("[シート1!A0:B2]")
    assert not _has_cell_range("[シート1!row12]")
