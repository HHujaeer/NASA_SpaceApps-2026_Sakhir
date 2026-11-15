"""Build chart points from source rows; model output selects columns, never values."""
import math
import re

from services.csv_service import InvalidRequest, _NUM_RE


def numeric(value):
    # Charts preserve raw numbers and header units; mixed strings are not guessed.
    if value is None or not _NUM_RE.fullmatch(str(value).strip()):
        return None
    number = float(_NUM_RE.fullmatch(str(value).strip()).group(1))
    return number if math.isfinite(number) else None


def build_chart(spec, profile, df):
    if spec is None:
        return None
    if not isinstance(spec, dict) or spec.get('type') not in ('scatter', 'line', 'bar'):
        raise InvalidRequest('Chart type must be scatter, line, or bar.')
    x, y = spec.get('x'), spec.get('y')
    if not isinstance(x, str) or not isinstance(y, str) or x not in df.columns or y not in df.columns:
        raise InvalidRequest('Chart axes must name existing source columns.')
    for column in ([y] if spec['type'] == 'bar' else [x, y]):
        units = {match.group(2).lower() for value in df[column] if value is not None
                 and (match := _NUM_RE.fullmatch(str(value).strip())) and match.group(2)}
        if len(units) > 1:
            raise InvalidRequest(f"Column '{column}' mixes units; an explicit conversion is required before plotting.")
    points = []
    skipped = 0
    for rn, row in df.iterrows():
        xv = row[x] if spec['type'] == 'bar' else numeric(row[x])
        yv = numeric(row[y])
        if xv is None or yv is None:
            skipped += 1
            continue
        points.append(dict(x=xv, y=yv, row_number=int(rn),
                           source=dict(file=profile['file'], row_number=int(rn))))
    if not points:
        raise InvalidRequest('The selected columns have no paired values to plot.')
    if spec['type'] == 'line':
        points.sort(key=lambda p: (p['x'], p['row_number']))
    return dict(type=spec['type'], x=x, y=y, title=f'{y} vs {x}',
                investigation_id=profile['id'], points=points[:2000],
                total_points=len(points), omitted_points=max(0, len(points)-2000),
                skipped_rows=skipped, source_file=profile['file'],
                note='Raw source values; no interpolation, aggregation, or unit conversion. Lines connect samples only.')
