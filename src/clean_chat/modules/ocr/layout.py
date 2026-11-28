"""검출 영역을 화면상의 행으로 합치는 공통 함수."""


def group_rows(results: list) -> list[tuple[str, float]]:
    """위에서 아래, 같은 행 안에서는 왼쪽에서 오른쪽으로 정렬한다."""
    rows = []
    for box, text, confidence in sorted(results, key=lambda item: min(p[1] for p in item[0])):
        top, bottom = min(p[1] for p in box), max(p[1] for p in box)
        center = (top + bottom) / 2
        row = next((r for r in rows if abs(r[0] - center) <= min(r[1], bottom - top) * 0.5), None)
        if row is None:
            row = [center, bottom - top, []]
            rows.append(row)
        row[2].append((min(p[0] for p in box), text, float(confidence)))
    return [
        (" ".join(part[1] for part in sorted(row[2])), min(part[2] for part in row[2]))
        for row in sorted(rows, key=lambda row: row[0])
    ]
