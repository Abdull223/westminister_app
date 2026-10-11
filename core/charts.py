"""Brand-styled Altair chart builders."""

import json

import altair as alt
import pandas as pd
import streamlit as st

from core.theme import BRASS, COLORWAY, INK, LINE, MUTED, TEXT

_LEGEND_NO_TITLE = alt.Legend(title=None)

@alt.theme.register("westminister", enable=True)
def westminister_theme() -> alt.theme.ThemeConfig:
    return alt.theme.ThemeConfig(
        {
            "config": {
                "background": "transparent",
                "view": {"stroke": "transparent"},
                "font": "IBM Plex Sans, sans-serif",
                "title": {"color": TEXT, "fontSize": 15, "anchor": "start"},
                "axis": {
                    "labelColor": MUTED,
                    "titleColor": MUTED,
                    "gridColor": LINE,
                    "domainColor": LINE,
                    "tickColor": LINE,
                },
                "legend": {"labelColor": MUTED, "titleColor": MUTED},
                "range": {"category": COLORWAY},
            }
        }
    )


def area_trend(df: pd.DataFrame, x: str, y: str, title: str) -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_area(color="rgba(201,162,79,0.25)", line={"color": BRASS, "strokeWidth": 2})
        .encode(x=alt.X(f"{x}:T", title=None), y=alt.Y(f"{y}:Q", title=None), tooltip=[x, y])
        .properties(title=title, height=300)
        .interactive()
    )


def forecast_trend(actual: pd.DataFrame, forecast: pd.DataFrame, x: str, y: str, y_fc: str, title: str) -> alt.Chart:
    base = alt.Chart(actual)
    area = base.mark_area(color="rgba(201,162,79,0.18)").encode(x=alt.X(f"{x}:T", title=None), y=alt.Y(f"{y}:Q", title=None))
    line = base.mark_line(color=BRASS, strokeWidth=2).encode(x=alt.X(f"{x}:T"), y=alt.Y(f"{y}:Q"), tooltip=[x, y])
    fline = (
        alt.Chart(forecast)
        .mark_line(color="#4FA3C7", strokeWidth=2, strokeDash=[6, 4], point=True)
        .encode(x=alt.X(f"{x}:T"), y=alt.Y(f"{y_fc}:Q"), tooltip=[x, y_fc])
    )
    return (area + line + fline).properties(title=title, height=320).interactive()


def bar_h(df: pd.DataFrame, x: str, y: str, title: str) -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_bar(color=BRASS)
        .encode(x=alt.X(f"{x}:Q", title=None), y=alt.Y(f"{y}:N", title=None, sort="-x"), tooltip=[y, x])
        .properties(title=title, height=300)
    )


def scatter(df: pd.DataFrame, x: str, y: str, title: str) -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_circle(size=60, color=BRASS, opacity=0.6)
        .encode(x=alt.X(f"{x}:Q", title=x), y=alt.Y(f"{y}:Q", title=y), tooltip=[x, y])
        .properties(title=title, height=300)
        .interactive()
    )


def histogram(df: pd.DataFrame, x: str, title: str) -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_bar(color=BRASS)
        .encode(
            x=alt.X(f"{x}:Q", bin=alt.Bin(maxbins=25), title=x),
            y=alt.Y("count()", title="Records"),
            tooltip=[alt.Tooltip(f"{x}:Q", bin=alt.Bin(maxbins=25)), "count()"],
        )
        .properties(title=title, height=300)
    )


def donut(df: pd.DataFrame, value: str, label: str, title: str) -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_arc(innerRadius=70, padAngle=0.02)
        .encode(
            theta=alt.Theta(f"{value}:Q"),
            color=alt.Color(f"{label}:N", scale=alt.Scale(range=COLORWAY), legend=alt.Legend(orient="right")),
            tooltip=[label, f"{value}:Q"],
        )
        .properties(title=title, height=300)
    )


def benford_chart(table: pd.DataFrame) -> alt.Chart:
    long_ = table.melt(id_vars="Digit", value_vars=["Observed %", "Expected %"], var_name="Series", value_name="Share %")
    return (
        alt.Chart(long_)
        .mark_bar()
        .encode(
            x=alt.X("Digit:N", title="Leading digit"),
            y=alt.Y("Share %:Q", title="Share of records (%)"),
            xOffset="Series",
            color=alt.Color("Series:N", scale=alt.Scale(domain=["Observed %", "Expected %"], range=[BRASS, "#4FA3C7"]), title=None),
            tooltip=["Digit", "Series", alt.Tooltip("Share %:Q", format=".1f")],
        )
        .properties(title="Benford's Law — first-digit conformity", height=320)
    )


def heatmap(df: pd.DataFrame, x: str, y: str, value: str, title: str) -> alt.Chart:
    return (
        alt.Chart(df)
        .mark_rect()
        .encode(
            x=alt.X(f"{x}:N", title=None),
            y=alt.Y(f"{y}:N", title=None),
            color=alt.Color(
                f"{value}:Q",
                scale=alt.Scale(scheme="goldgreen"),
                legend=_LEGEND_NO_TITLE,
            ),
            tooltip=[x, y, value],
        )
        .properties(title=title, height=min(460, 90 + 34 * max(len(df[y].unique()), 1)))
    )


def spark_values(monthly: pd.DataFrame, date_col: str, metric: str) -> list[float]:
    return [float(v) for v in monthly[metric].tolist()]


_PDF_CONFIG = {
    "background": "#FFFFFF",
    "view": {"stroke": "transparent"},
    "font": "Helvetica",
    "title": {"color": INK, "fontSize": 14, "anchor": "start"},
    "axis": {
        "labelColor": "#5A6E85",
        "titleColor": "#5A6E85",
        "gridColor": "#E2E8F0",
        "domainColor": "#C4CFDA",
        "tickColor": "#C4CFDA",
    },
    "legend": {"labelColor": "#5A6E85", "titleColor": "#5A6E85"},
    "range": {"category": ["#B08A38", "#2E7EA8", "#4E8A55", "#8A6A9C", "#C0781F", "#B04A4A"]},
}


def _pdf_spec(chart: alt.Chart) -> dict:
    spec = chart.to_dict()
    spec["config"] = {**(spec.get("config") or {}), **_PDF_CONFIG}
    spec.pop("autosize", None)
    return spec


@st.cache_data(ttl=3600, show_spinner=False)
def _render_png(spec_json: str) -> bytes:
    import vl_convert as vl

    return vl.vegalite_to_png(spec_json, scale=2.0)


def chart_png(chart: alt.Chart, width: int = 560) -> bytes:
    """Render a light-themed 2x PNG of a chart for embedding in the PDF report."""
    chart = chart.properties(width=width).configure_view(stroke=None)
    return _render_png(json.dumps(_pdf_spec(chart), default=str))
