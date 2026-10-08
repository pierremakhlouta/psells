"""The geometry of the analytics page's charts, worked out here so the
template only places it.

Every page's policy allows no scripts, so a chart is SVG drawn on the server:
rectangles, a line and labels, positioned here in Python and written out by
templates/analytics.html, which does no arithmetic of its own (a test reads
every template to hold it to that). These functions take the figures the
warehouse's views gave and return positions, sizes and the values to label
them with; they read nothing and format nothing, so money stays whole cents
for the template's money filter.

Coordinates are SVG user units, rounded to one decimal. That rounding is of
pixels, not of money: no figure shown is ever changed by it.
"""

import math


# Room for the axis labels on the left and the month names below.
LEFT = 72
BOTTOM = 28
TOP = 12
RIGHT = 12


def nice_step(largest, ticks=4):
    """A round step (1, 2 or 5 times a power of ten) that divides 0 to
    largest into about `ticks` intervals."""
    if largest <= 0:
        return 1
    rough = largest / ticks
    power = 10 ** math.floor(math.log10(rough))
    for multiple in (1, 2, 5, 10):
        if rough <= multiple * power:
            # Whole numbers only: the values are cents or counts.
            return max(1, round(multiple * power))
    return max(1, round(10 * power))


def value_ticks(low, high, ticks=4):
    """Round values from at or below low to at or above high, 0 always one
    of them, in nice steps."""
    step = nice_step(max(high, -low, 0), ticks)
    first = math.floor(min(low, 0) / step) * step
    last = math.ceil(max(high, 0) / step) * step
    if first == last:
        last = first + step
    return list(range(int(first), int(last) + 1, int(step)))


def _scale(ticks, top, bottom):
    """A function from a value to its y, with ticks[0] at bottom and
    ticks[-1] at top."""
    low, high = ticks[0], ticks[-1]

    def y(value):
        return round(bottom - (value - low) / (high - low) * (bottom - top), 1)

    return y


def bar_chart(labels, series, width=720, height=260):
    """Grouped vertical bars: one group per label, one bar per series.

    series is a list of lists of whole numbers, each as long as labels. A
    negative value draws below the zero line. Returns the chart's size, its
    bars, its value ticks and its labels; an empty chart if there are no
    labels.
    """
    chart = {"width": width, "height": height, "bars": [], "ticks": [],
             "labels": [], "zero_y": None}
    if not labels:
        return chart

    values = [value for values in series for value in values]
    ticks = value_ticks(min(values), max(values))
    top, bottom = TOP, height - BOTTOM
    y = _scale(ticks, top, bottom)
    plot_width = width - LEFT - RIGHT
    group = plot_width / len(labels)
    bar = group * 0.8 / len(series)
    zero = y(0)

    for index, label in enumerate(labels):
        start = LEFT + index * group + group * 0.1
        for number, values in enumerate(series):
            value = values[index]
            top_y = min(y(value), zero)
            chart["bars"].append({
                "x": round(start + number * bar, 1), "y": top_y,
                "width": round(bar, 1),
                "height": round(abs(y(value) - zero), 1),
                "series": number, "label": label, "value": value,
            })
        chart["labels"].append({"x": round(LEFT + index * group + group / 2, 1),
                                "y": height - 8, "text": label})
    chart["ticks"] = [{"y": y(value), "value": value} for value in ticks]
    chart["zero_y"] = zero
    chart["left"] = LEFT
    chart["right"] = width - RIGHT
    return chart


def line_chart(labels, values, width=720, height=200):
    """A line through one value per label, as SVG polyline points, with a
    dot at each value."""
    chart = {"width": width, "height": height, "points": "", "dots": [],
             "ticks": [], "labels": []}
    if not labels:
        return chart

    ticks = value_ticks(min(values), max(values))
    y = _scale(ticks, TOP, height - BOTTOM)
    plot_width = width - LEFT - RIGHT
    step = plot_width / len(labels)

    for index, (label, value) in enumerate(zip(labels, values)):
        x = round(LEFT + index * step + step / 2, 1)
        chart["dots"].append({"x": x, "y": y(value), "label": label,
                              "value": value})
        chart["labels"].append({"x": x, "y": height - 8, "text": label})
    chart["points"] = " ".join(f"{d['x']},{d['y']}" for d in chart["dots"])
    chart["ticks"] = [{"y": y(value), "value": value} for value in ticks]
    chart["left"] = LEFT
    chart["right"] = width - RIGHT
    return chart


def horizontal_bars(labels, values, width=720, row=26, label_width=160):
    """One horizontal bar per label, the longest for the largest value;
    a value of 0 or less draws no bar."""
    largest = max([value for value in values if value > 0], default=0)
    plot_width = width - label_width - RIGHT
    bars = []
    for index, (label, value) in enumerate(zip(labels, values)):
        length = plot_width * value / largest if largest and value > 0 else 0
        bars.append({"x": label_width, "y": index * row + 4,
                     "width": round(length, 1), "height": row - 8,
                     "label_y": index * row + row / 2 + 4,
                     "label": label, "value": value})
    return {"width": width, "height": len(labels) * row, "bars": bars,
            "label_x": label_width - 8}
