"""E-commerce sales analysis.

Cleans the raw Superstore sales extract, summarises performance across the
business (time, category, sub-category, customer segment, region, shipping,
discounting and customers), and produces:

  * data/processed/superstore_sales_clean.csv  - tidy, analysis-ready data
  * outputs/ecommerce_sales_analysis.xlsx      - workbook with a dashboard,
                                                 summary tables and charts
  * images/*.png                                - charts used in the README

Run from the repository root:

    python src/analysis.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter, MaxNLocator

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "superstore_sales.csv"
CLEAN = ROOT / "data" / "processed" / "superstore_sales_clean.csv"
WORKBOOK = ROOT / "outputs" / "ecommerce_sales_analysis.xlsx"
IMAGES = ROOT / "images"

# Chart styling
BLUE = "#2a78d6"
RED = "#e34948"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e4e3df"
SURFACE = "#fcfcfb"


# --------------------------------------------------------------------------
# Load and clean
# --------------------------------------------------------------------------
def load_data() -> pd.DataFrame:
    # The source file uses old-style Mac line endings and Windows-1252 text.
    df = pd.read_csv(RAW, encoding="cp1252", lineterminator="\r")
    df = df.dropna(subset=["Order ID"])  # trailing blank line

    df["Order Date"] = pd.to_datetime(df["Order Date"], format="%m/%d/%Y")
    df["Ship Date"] = pd.to_datetime(df["Ship Date"], format="%m/%d/%Y")
    for col in ["Row ID", "Order ID", "Order Quantity"]:
        df[col] = df[col].astype(int)

    df["Region"] = df["Region"].replace({"Prarie": "Prairie"})
    df["Product Name"] = df["Product Name"].str.replace("ª", "", regex=False)

    df["Year"] = df["Order Date"].dt.year
    df["Month"] = df["Order Date"].dt.to_period("M").dt.to_timestamp()
    df["Days to Ship"] = (df["Ship Date"] - df["Order Date"]).dt.days
    df["Profit Margin"] = df["Profit"] / df["Sales"]
    df["Discount Band"] = pd.cut(
        df["Discount"],
        bins=[-0.001, 0.02, 0.05, 0.08, 1],
        labels=["0-2%", "3-5%", "6-8%", "9%+"],
    )
    df["Loss Making"] = df["Profit"] < 0
    return df


# --------------------------------------------------------------------------
# Summaries
# --------------------------------------------------------------------------
def summarise(df: pd.DataFrame, by: str, sort_by_sales: bool = True) -> pd.DataFrame:
    out = df.groupby(by, observed=True).agg(
        Sales=("Sales", "sum"),
        Profit=("Profit", "sum"),
        Orders=("Order ID", "nunique"),
        Customers=("Customer Name", "nunique"),
    )
    out["Profit Margin"] = out["Profit"] / out["Sales"]
    out["Share of Sales"] = out["Sales"] / df["Sales"].sum()
    out["Avg Order Value"] = out["Sales"] / out["Orders"]
    if sort_by_sales:
        out = out.sort_values("Sales", ascending=False)
    return out.reset_index()


def kpis(df: pd.DataFrame) -> dict:
    sales, profit = df["Sales"].sum(), df["Profit"].sum()
    orders = df["Order ID"].nunique()
    return {
        "Total Sales": sales,
        "Total Profit": profit,
        "Profit Margin": profit / sales,
        "Orders": orders,
        "Customers": df["Customer Name"].nunique(),
        "Avg Order Value": sales / orders,
        "Loss-Making Order Lines": df["Loss Making"].mean(),
    }


def customer_concentration(df: pd.DataFrame) -> pd.DataFrame:
    by_cust = df.groupby("Customer Name")["Sales"].sum().sort_values(ascending=False)
    total, n = by_cust.sum(), len(by_cust)
    rows = []
    for pct in (0.05, 0.10, 0.20, 0.50):
        k = int(round(n * pct))
        rows.append({"Top Customers": f"Top {pct:.0%} ({k})", "Share of Sales": by_cust.head(k).sum() / total})
    return pd.DataFrame(rows)


def build_summaries(df: pd.DataFrame) -> dict:
    return {
        "Year": summarise(df, "Year", sort_by_sales=False),
        "Category": summarise(df, "Product Category"),
        "Sub-Category": summarise(df, "Product Sub-Category").sort_values("Profit"),
        "Segment": summarise(df, "Customer Segment"),
        "Region": summarise(df, "Region"),
        "Ship Mode": summarise(df, "Ship Mode"),
        "Priority": summarise(df, "Order Priority"),
        "Discount": summarise(df, "Discount Band", sort_by_sales=False),
        "Month": summarise(df, "Month", sort_by_sales=False),
        "Customers": customer_concentration(df),
        "Top Products": summarise(df, "Product Name").nlargest(10, "Profit"),
        "Bottom Products": summarise(df, "Product Name").nsmallest(10, "Profit"),
    }


# --------------------------------------------------------------------------
# Charts (PNG, for the README)
# --------------------------------------------------------------------------
def _money(v, _):
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v == 0:
        return "$0"
    return f"{sign}${v / 1e6:.1f}M" if v >= 1e6 else f"{sign}${v / 1e3:.0f}K"


money = FuncFormatter(_money)


def style(ax, title):
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold", color=INK, pad=10)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED, length=0, labelsize=9)
    ax.grid(axis="x" if ax.get_xaxis().get_major_formatter() else "y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def hbar(ax, labels, values, title, fmt, color_negative=True):
    colors = [RED if (color_negative and v < 0) else BLUE for v in values]
    ax.barh(labels, values, color=colors, height=0.6)
    style(ax, title)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
    ax.xaxis.set_major_formatter(fmt)
    ax.axvline(0, color=MUTED, linewidth=0.8)
    ax.invert_yaxis()


def vbar(ax, labels, values, title, fmt):
    ax.bar(labels, values, color=[RED if v < 0 else BLUE for v in values], width=0.6)
    style(ax, title)
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, steps=[1, 2, 2.5, 5, 10]))
    ax.yaxis.set_major_formatter(fmt)


def save(fig, name):
    fig.patch.set_facecolor(SURFACE)
    fig.tight_layout()
    fig.savefig(IMAGES / name, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def make_charts(df: pd.DataFrame, s: dict, k: dict) -> None:
    IMAGES.mkdir(exist_ok=True)
    pct = FuncFormatter(lambda v, _: f"{v:.1%}".replace(".0%", "%"))

    # Monthly sales trend
    fig, ax = plt.subplots(figsize=(10, 3.6))
    m = s["Month"]
    ax.plot(m["Month"], m["Sales"], color=BLUE, linewidth=2)
    style(ax, "Monthly sales, 2009-2012")
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.yaxis.set_major_formatter(money)
    save(fig, "monthly_sales.png")

    # Category: sales vs margin as two charts on separate axes
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.4))
    c = s["Category"]
    hbar(a1, c["Product Category"], c["Sales"], "Sales by category", money)
    hbar(a2, c["Product Category"], c["Profit Margin"], "Profit margin by category", pct)
    save(fig, "category_performance.png")

    # Sub-category profit
    fig, ax = plt.subplots(figsize=(10, 6))
    sc = s["Sub-Category"].sort_values("Profit", ascending=False)
    hbar(ax, sc["Product Sub-Category"], sc["Profit"], "Profit by sub-category (red = loss)", money)
    save(fig, "subcategory_profit.png")

    # Region margin
    fig, ax = plt.subplots(figsize=(10, 4.2))
    r = s["Region"]
    hbar(ax, r["Region"] + "  (" + (r["Share of Sales"] * 100).round(0).astype(int).astype(str) + "% of sales)",
         r["Profit Margin"], "Profit margin by region", pct)
    save(fig, "region_margin.png")

    # Discount & shipping
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.6))
    d = s["Discount"]
    vbar(a1, d["Discount Band"].astype(str), d["Profit Margin"], "Profit margin by discount level", pct)
    sm = s["Ship Mode"]
    vbar(a2, sm["Ship Mode"], sm["Profit Margin"], "Profit margin by ship mode", pct)
    save(fig, "discount_shipping.png")

    # One-page dashboard
    fig = plt.figure(figsize=(14, 10))
    gs = fig.add_gridspec(4, 3, height_ratios=[0.35, 1.2, 1.2, 1.2], hspace=0.6, wspace=0.45)
    fig.suptitle("E-commerce Sales Dashboard  |  Superstore, 2009-2012", x=0.02, y=0.94, ha="left",
                 fontsize=16, fontweight="bold", color=INK)
    tiles = [
        ("Total sales", f"${k['Total Sales'] / 1e6:.1f}M"),
        ("Total profit", f"${k['Total Profit'] / 1e6:.2f}M"),
        ("Profit margin", f"{k['Profit Margin']:.1%}"),
        ("Orders", f"{k['Orders']:,}"),
        ("Customers", f"{k['Customers']:,}"),
        ("Avg order value", f"${k['Avg Order Value']:,.0f}"),
    ]
    tile_ax = fig.add_subplot(gs[0, :])
    tile_ax.axis("off")
    for i, (label, value) in enumerate(tiles):
        x = i / len(tiles) + 0.01
        tile_ax.text(x, 0.75, label.upper(), fontsize=9, color=MUTED, transform=tile_ax.transAxes)
        tile_ax.text(x, 0.15, value, fontsize=20, fontweight="bold", color=INK, transform=tile_ax.transAxes)

    ax = fig.add_subplot(gs[1, :2])
    ax.plot(m["Month"], m["Sales"], color=BLUE, linewidth=2)
    style(ax, "Monthly sales")
    ax.grid(axis="x", visible=False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.yaxis.set_major_formatter(money)

    hbar(fig.add_subplot(gs[1, 2]), c["Product Category"], c["Profit Margin"], "Margin by category", pct)
    seg = s["Segment"]
    hbar(fig.add_subplot(gs[2, 0]), seg["Customer Segment"], seg["Sales"], "Sales by segment", money)
    hbar(fig.add_subplot(gs[2, 1]), r["Region"], r["Profit Margin"], "Margin by region", pct)
    vbar(fig.add_subplot(gs[2, 2]), d["Discount Band"].astype(str), d["Profit Margin"], "Margin by discount", pct)
    worst = s["Sub-Category"].head(6)
    hbar(fig.add_subplot(gs[3, :2]), worst["Product Sub-Category"], worst["Profit"],
         "Least profitable sub-categories", money)
    vbar(fig.add_subplot(gs[3, 2]), sm["Ship Mode"], sm["Profit Margin"], "Margin by ship mode", pct)
    fig.patch.set_facecolor(SURFACE)
    fig.savefig(IMAGES / "dashboard.png", dpi=130, facecolor=SURFACE, bbox_inches="tight")
    plt.close(fig)


# --------------------------------------------------------------------------
# Excel workbook
# --------------------------------------------------------------------------
def build_workbook(df: pd.DataFrame, s: dict, k: dict) -> None:
    WORKBOOK.parent.mkdir(exist_ok=True)
    with pd.ExcelWriter(WORKBOOK, engine="xlsxwriter", datetime_format="dd/mm/yyyy") as xw:
        wb = xw.book
        f_title = wb.add_format({"bold": True, "font_size": 18, "font_color": INK})
        f_sub = wb.add_format({"italic": True, "font_color": MUTED})
        f_head = wb.add_format({"bold": True, "bg_color": BLUE, "font_color": "white", "border": 1})
        f_money = wb.add_format({"num_format": "$#,##0"})
        f_pct = wb.add_format({"num_format": "0.0%"})
        f_int = wb.add_format({"num_format": "#,##0"})
        f_tile_lbl = wb.add_format({"font_color": MUTED, "font_size": 9, "bold": True, "top": 2,
                                    "top_color": BLUE, "bg_color": "#f3f6fb"})
        f_tile_val = {
            "money": wb.add_format({"bold": True, "font_size": 18, "num_format": "$#,##0", "bg_color": "#f3f6fb"}),
            "pct": wb.add_format({"bold": True, "font_size": 18, "num_format": "0.0%", "bg_color": "#f3f6fb"}),
            "int": wb.add_format({"bold": True, "font_size": 18, "num_format": "#,##0", "bg_color": "#f3f6fb"}),
        }
        col_fmt = {"Sales": f_money, "Profit": f_money, "Avg Order Value": f_money,
                   "Profit Margin": f_pct, "Share of Sales": f_pct,
                   "Orders": f_int, "Customers": f_int}

        # Dashboard sheet first so it opens on top
        dash = wb.add_worksheet("Dashboard")
        dash.hide_gridlines(2)
        dash.set_landscape()
        dash.fit_to_pages(1, 0)
        dash.set_column("A:A", 2)
        dash.set_column("B:M", 13)
        dash.write("B2", "E-commerce Sales Dashboard", f_title)
        dash.write("B3", "Superstore sales, 2009-2012  |  all values in USD", f_sub)

        tiles = [("TOTAL SALES", k["Total Sales"], "money"), ("TOTAL PROFIT", k["Total Profit"], "money"),
                 ("PROFIT MARGIN", k["Profit Margin"], "pct"), ("ORDERS", k["Orders"], "int"),
                 ("CUSTOMERS", k["Customers"], "int"), ("AVG ORDER VALUE", k["Avg Order Value"], "money")]
        for i, (label, value, kind) in enumerate(tiles):
            col = 1 + i * 2
            dash.merge_range(4, col, 4, col + 1, label, f_tile_lbl)
            dash.merge_range(5, col, 5, col + 1, value, f_tile_val[kind])
        dash.set_row(5, 30)

        # Summary sheets
        sheets = ["Year", "Category", "Sub-Category", "Segment", "Region", "Ship Mode",
                  "Priority", "Discount", "Month", "Customers", "Top Products", "Bottom Products"]
        positions = {}
        for name in sheets:
            table = s[name].copy()
            if name == "Discount":
                table["Discount Band"] = table["Discount Band"].astype(str)
            table.to_excel(xw, sheet_name=name, index=False, startrow=1)
            ws = xw.sheets[name]
            ws.write(0, 0, name if name != "Year" else "Yearly performance", wb.add_format({"bold": True, "font_size": 14}))
            for j, col in enumerate(table.columns):
                ws.write(1, j, col, f_head)
                width = max(14, min(55, int(table[col].astype(str).str.len().max()) + 2)) if j == 0 else 15
                ws.set_column(j, j, width, col_fmt.get(col))
            ws.freeze_panes(2, 0)
            positions[name] = (len(table), list(table.columns))

        def ref(sheet, col):
            n, cols = positions[sheet]
            j = cols.index(col)
            return [sheet, 2, j, 1 + n, j]

        def chart(kind, sheet, cat, val, title, fmt, color=BLUE, subtype=None):
            ch = wb.add_chart({"type": kind, **({"subtype": subtype} if subtype else {})})
            ch.add_series({"categories": ref(sheet, cat), "values": ref(sheet, val), "name": val,
                           "fill": {"color": color}, "line": {"color": color, "width": 2},
                           "invert_if_negative": False, "gap": 60})
            ch.set_title({"name": title, "name_font": {"size": 11, "bold": True}})
            ch.set_legend({"none": True})
            axis = {"num_format": fmt, "major_gridlines": {"visible": True, "line": {"color": GRID}},
                    "num_font": {"size": 8}}
            if kind == "bar":
                ch.set_x_axis(axis)
                ch.set_y_axis({"reverse": True, "crossing": "max", "num_font": {"size": 8}})
            else:
                ch.set_y_axis(axis)
                ch.set_x_axis({"num_font": {"size": 8}})
            ch.set_chartarea({"border": {"none": True}})
            ch.set_size({"width": 470, "height": 280})
            return ch

        monthly = chart("line", "Month", "Month", "Sales", "Monthly sales", "$#,##0,K")
        monthly.set_x_axis({"date_axis": True, "num_format": "mmm yy", "num_font": {"size": 8}})
        monthly.set_size({"width": 940, "height": 280})
        dash.insert_chart("B8", monthly)
        dash.insert_chart("B23", chart("bar", "Category", "Product Category", "Profit Margin", "Profit margin by category", "0%"))
        dash.insert_chart("H23", chart("bar", "Segment", "Customer Segment", "Sales", "Sales by customer segment", "$#,##0,K"))
        dash.insert_chart("B38", chart("bar", "Region", "Region", "Profit Margin", "Profit margin by region", "0%"))
        dash.insert_chart("H38", chart("column", "Discount", "Discount Band", "Profit Margin", "Profit margin by discount level", "0%"))
        dash.insert_chart("B53", chart("bar", "Sub-Category", "Product Sub-Category", "Profit", "Profit by sub-category", "$#,##0,K"))
        dash.insert_chart("H53", chart("column", "Ship Mode", "Ship Mode", "Profit Margin", "Profit margin by ship mode", "0%"))

        # Full data as an Excel Table, ready for PivotTables and slicers
        data = df.drop(columns=["Month"]).copy()
        data["Discount Band"] = data["Discount Band"].astype(str)
        data.to_excel(xw, sheet_name="Data", index=False, startrow=1, header=False)
        ws = xw.sheets["Data"]
        ws.add_table(0, 0, len(data), len(data.columns) - 1, {
            "name": "SalesData", "style": "Table Style Medium 2",
            "columns": [{"header": c} for c in data.columns],
        })
        ws.set_column(0, len(data.columns) - 1, 14)
        ws.freeze_panes(1, 0)


def main() -> None:
    df = load_data()
    CLEAN.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["Month"]).to_csv(CLEAN, index=False)

    s = build_summaries(df)
    k = kpis(df)
    make_charts(df, s, k)
    build_workbook(df, s, k)

    print("Key metrics")
    for name, value in k.items():
        print(f"  {name:<24} {value:,.3f}" if isinstance(value, float) else f"  {name:<24} {value:,}")
    print(f"\nWrote {CLEAN.relative_to(ROOT)}, {WORKBOOK.relative_to(ROOT)} and charts in {IMAGES.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
