import logging
import pathlib
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import testing_farm.tfutil as tfutil


def create_figure(df: pd.DataFrame, perf_kind: str, y_column_name: str) -> go.Figure:
    """Creates a figure for performance visualization.

    When no package_name is specified, the whole dataframe is used.

    Args:
        df (pd.DataFrame): The complete dataframe to grab information from
        perf_kind (str): The kind of performance that is measured

    Returns:
        go.Figure: A line figure with all chroots in one graph
    """
    perf_kind_label = perf_kind.capitalize().replace("_", "-")
    column_label = y_column_name.replace("perf_", "")

    fig = px.line(
        data_frame=df,
        x="date",
        y=y_column_name,
        color="legend_name",
        markers=True,
        line_shape="linear",
        title=f"Peformance improvment for: {perf_kind_label} (aggregate: {column_label})",
        symbol="legend_name",
        hover_data=[
            y_column_name,
            "date",
            "chroot",
            "total_iterations",
            "cpu_info_model_name",
            "cpu_info_vendor_id",
            "cpu_info_architecture",
            "cpu_info_cpus",
            "cpu_info_byte_order",
            # Don't change position of the testing_farm_artifacts_url as it is referenced by the JS script below at index 7
            "testing_farm_artifacts_url",
            "perf_max",
            "perf_mean",
            "perf_median",
            "perf_min",
            "perf_std",
            "perf_sum",
            "perf_var",
        ],
        labels={
            "date": "Date",
            "chroot": "OS + Arch",
            "total_iterations": "Total test iterations",
            "perf_max": f"{perf_kind_label} (max)",
            "perf_mean": f"{perf_kind_label} (mean)",
            "perf_median": f"{perf_kind_label} (median)",
            "perf_min": f"{perf_kind_label} (min)",
            "perf_std": f"{perf_kind_label} (std)",
            "perf_sum": f"{perf_kind_label} (sum)",
            "perf_var": f"{perf_kind_label} (var)",
            "cpu_info_model_name": "CPU Model Name",
            "cpu_info_vendor_id": "CPU Vendor ID",
            "cpu_info_architecture": "CPU Architecture",
            "cpu_info_cpus": "Number of CPUs",
            "cpu_info_byte_order": "Byte Order",
            "cpu_info_flags": "CPU Flags",
            "legend_name": "Legend",
            "testing_farm_artifacts_url": "Testing Farm Artifacts URL",
        },
        text=[f"{x:0.2f}" for x in df[y_column_name]],  # To show text at each location
    )

    # Increase the size of markers
    fig.update_traces(marker_size=7)
    fig.update_traces(textposition="bottom left")
    fig.update_xaxes(minor=dict(ticks="outside", showgrid=True))

    # Create a watermark background
    # See https://stackoverflow.com/a/74665137/835098
    # https://plotly.com/python/templates/
    pio.templates["draft"] = go.layout.Template(
        layout_annotations=[
            dict(
                name="draft watermark",
                text="WARNING: DO NOT USE THESE GRAPHS",
                textangle=-30,
                opacity=0.1,
                font=dict(color="red", size=100),
                xref="paper",
                yref="paper",
                x=0.5,
                y=0.5,
                showarrow=False,
            )
        ]
    )
    fig.update_layout(yaxis={"ticksuffix": " %"}, template="plotly+draft")

    return fig


def save_figure(fig: go.Figure, filepath: str) -> None:
    """Saves a figure to an HTML file.

    Args:
        fig (go.Figure): The figure object to save
        filepath (str): The filepath to save to

    Returns:
        None
    """

    post_script = """
    // We inject this script into the final HTML page in order to be able to click on
    // a point on a line and be taken to the testing farm artifacts page.
    var plot_element = document.getElementById("{plot_id}");
    plot_element.on('plotly_click', function(data){{
        console.log(data);
        var point = data.points[0];
        if (point) {{
            console.log(point.customdata);
            testing_farm_artifacts_url = point.customdata[7]
            window.open(testing_farm_artifacts_url);
        }}
    }})
    """

    fig.write_html(
        file=filepath,
        include_plotlyjs="cdn",
        full_html=True,
        post_script=post_script,
        div_id="plotly_div_id",
    )


def add_html_header_menu(
    filepath: str,
    plotly_div_id: str = "plotly_div_id",
    perf_kinds: list[str] = [],
    perf_aggregates: list[str] = [],
) -> None:
    """Replace plotly's opening HTML-div element with itself and an additional
       menu so that you can navigate to different pages.

    Args:
        filepath (str): HTML file in which to do the replacement.
    """

    # Plotly's HTML div's ID. Defaults to "plotly_div_id".
    plotly_div_id = "plotly_div_id"

    replace_me = f'<div id="{plotly_div_id}"'

    last_updated = datetime.today().strftime("%c")

    file = Path(filepath)
    header_menu = '<div id="headermenu">Performance Stats: '
    for kind in perf_kinds:
        for agg in perf_aggregates:
            perf_kind_label = kind.capitalize().replace("_", "-")
            if kind == perf_kinds[0] and agg == perf_aggregates[0]:
                header_menu += f' <a href="index.html">{perf_kind_label} ({agg})</a>'
            else:
                header_menu += f' | <a href="fig-perf-{kind}-{agg}.html">{perf_kind_label} ({agg})</a>'
    header_menu += f" <small>(Last updated: {last_updated})</small>"
    header_menu += "</div>"
    header_menu += replace_me

    file.write_text(file.read_text().replace(replace_me, header_menu))


def prepare_data(filepath: pathlib.Path) -> pd.DataFrame:
    """Reads in data from a given file in CSV format, sorts it groups it

    Args:
        filepath (pathlib.Path): The path to the CSV file to read in.

    Returns:
        pd.DataFrame: A prepared and ready to use dataframe
    """
    df = pd.read_csv(
        filepath_or_buffer=filepath,
        parse_dates=["date"],
        delimiter=",",
        header=0,
    )

    # Sort data frame by criteria and make sure to include timestamp for later
    # dropping of duplicates.
    df.sort_values(
        by=["date", "chroot", "name", "timestamp"],
        inplace=True,
    )

    # specify dropna=False because sometimes the "cpu_info_cpu_max_mhz" and
    # "cpu_info_cpu_min_mhz" columns are NaN and I want to still keep the entries.

    df = df.groupby(
        dropna=False,
        by=[
            "kind",
            "name",
            "chroot",
            "date",
            "cpu_info_flags",
            "cpu_info_vendor_id",
            "cpu_info_architecture",
            "cpu_info_model_name",
            "cpu_info_cpus",
            "cpu_info_byte_order",
            "testing_farm_request_id",
        ],
    ).agg(
        perf_max=("geomean_diff", "max"),
        perf_mean=("geomean_diff", "mean"),
        perf_median=("geomean_diff", "median"),
        perf_min=("geomean_diff", "min"),
        perf_std=("geomean_diff", "std"),
        perf_sum=("geomean_diff", "sum"),
        perf_var=("geomean_diff", "var"),
        # While we could just use the total_iterations column we want to create
        # it so that it reflects the group better.
        total_iterations=("total_iterations", "count"),
    )

    # Bring columns back (see https://stackoverflow.com/a/70336081/835098)
    df.reset_index(inplace=True)

    df["legend_name"] = df.apply(
        lambda row: f"{row["name"].replace("_", " ").upper().replace("VS", "vs.")} ({row["chroot"]})",
        axis=1,
    )

    df["testing_farm_artifacts_url"] = df.apply(
        lambda row: tfutil.get_artifacts_url(
            row["chroot"], row["testing_farm_request_id"]
        ),
        axis=1,
    )

    df.info()
    return df


def build_performance_diagrams(datafile: pathlib.Path | str) -> None:
    """The main program to prepare the data, generate figures, save them and create an index page for them."""

    # Do some visualization preparation
    # pio.renderers.default = "browser"
    #
    # See https://plotly.com/python/renderers/#setting-the-default-renderer
    # See https://plotly.com/python/templates/#theming-and-templates
    pio.templates.default = "plotly"

    if isinstance(datafile, str):
        datafile = pathlib.Path(datafile)

    df = prepare_data(filepath=datafile)

    perf_columns = [col for col in df.columns if col.startswith("perf_")]
    perf_columns.sort()
    perf_aggregates = [col.replace("perf_", "") for col in perf_columns]
    logging.info(f"Performance aggretates: {perf_aggregates}")

    # Get all kinds of performance measurements within the dataframe
    perf_kinds = df["kind"].explode().drop_duplicates().values
    perf_kinds.sort()

    for perf_kind in perf_kinds:
        logging.info(f"Generating performance diagrams for: {perf_kind}")
        filter = df["kind"] == perf_kind
        df_by_kind = df.where(filter, inplace=False).dropna()

        for perf_column in perf_columns:
            agg = perf_column.replace("perf_", "")
            logging.info(f"  - Performance aggregate: {agg}")

            fig = create_figure(
                df=df_by_kind, perf_kind=perf_kind, y_column_name=perf_column
            )
            filepath = f"fig-perf-{perf_kind}-{agg}.html"
            if perf_kind == perf_kinds[0] and perf_column == perf_columns[0]:
                filepath = "index.html"
            save_figure(fig=fig, filepath=filepath)
            add_html_header_menu(
                filepath=filepath,
                perf_kinds=perf_kinds,
                perf_aggregates=perf_aggregates,
            )
