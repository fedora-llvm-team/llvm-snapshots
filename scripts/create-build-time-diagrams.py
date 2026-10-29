#!/bin/env python3

# %%
import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio


# %%
def create_figure(df: pd.DataFrame, package_name: str = "") -> go.Figure:
    """Creates a figure for a particular package name

    When no package_name is specified, the whole dataframe is used.

    Args:
        df (pd.DataFrame): The complete dataframe to grab information from
        package_names (str , optional): The package name by which to lookup information from the dataframe df.

    Returns:
        go.Figure: A line figure with all chroots in one graph
    """
    if package_name != "":
        df = df[df.package == package_name]
    fig = px.line(
        data_frame=df,
        x="date",
        y="build_time",
        color="chroot",
        markers=True,
        line_shape="linear",
        symbol="chroot",
        hover_data=["package", "date", "state", "build_id"],
        category_orders={"chroot": sorted(df["chroot"].unique())},
        labels={
            "build_time": "Build time",
            "date": "Date",
            "chroot": "OS + Arch",
            "state": "State",
            "build_id": "Copr Build ID",
            "package": "LLVM subpackage",
        },
        # text="build_time", # To show text at each location
    )

    # Print annotations for the overall max build duration
    # TODO(would be nice to have this just per chroot maybe?)
    # for cr in df_llvm['chroot'].unique():
    #     my_df = df_llvm[df_llvm.chroot.isin([cr])]
    #     max_build_time = my_df['build_time'].max()
    #     max_build_times = my_df[my_df['build_time'] == max_build_time]
    #     for idx in max_build_times.index:
    #         y = max_build_times["build_time"][idx]
    #         x = max_build_times["date"][idx]
    #         fig.add_annotation(x=x, y=y, text="max: {}".format(y), hovertext=str(cr))

    # Uncomment this to show hovers for all chroots at once
    # fig.update_traces(mode="markers+lines", hovertemplate=None)
    # fig.update_layout(hovermode="x") # "x unified"

    # Increase the size of markers
    fig.update_traces(marker_size=7)
    fig.update_traces(textposition="bottom left")
    fig.update_xaxes(minor=dict(ticks="outside", showgrid=True))
    fig.update_layout(yaxis_tickformat="%H:%M:%S")

    return fig


# %%
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
    // a point on a line and be taken to the build in Copr.
    var plot_element = document.getElementById("{plot_id}");
    plot_element.on('plotly_click', function(data){
        console.log(data);
        var point = data.points[0];
        if (point) {
            console.log(point.customdata);
            build_id = point.customdata[2]
            window.open('https://copr.fedorainfracloud.org/coprs/build/' + build_id);
        }
    })

    // Pre-select chroots from URL ?chroot=<name>&chroot=<name2> (mimics legend double-click)
    var params = new URLSearchParams(window.location.search);
    var selectedChroots = params.getAll('chroot');
    if (selectedChroots.length > 0) {
        var traces = plot_element.data;
        var hideIdx = [];
        var showIdx = [];
        for (var i = 0; i < traces.length; i++) {
            var matched = false;
            for (var j = 0; j < selectedChroots.length; j++) {
                var sc = selectedChroots[j];
                if (traces[i].name === sc) {
                    matched = true;
                    break;
                }
            }
            if (matched) {
                showIdx.push(i);
            } else {
                hideIdx.push(i);
            }
        }
        if (showIdx.length > 0 && hideIdx.length > 0) {
            Plotly.restyle(plot_element, {visible: 'legendonly'}, hideIdx);
            Plotly.restyle(plot_element, {visible: true}, showIdx);
        }
    }

    function updateChrootUrl() {
        var traces = plot_element.data;
        var visible = [];
        var allVisible = true;
        for (var i = 0; i < traces.length; i++) {
            if (traces[i].visible === 'legendonly') {
                allVisible = false;
            } else {
                visible.push(traces[i].name);
            }
        }
        var url = new URL(window.location.href);
        url.searchParams.delete('chroot');
        if (!allVisible && visible.length > 0) {
            for (var i = 0; i < visible.length; i++) {
                url.searchParams.append('chroot', visible[i]);
            }
        }
        window.history.replaceState(null, '', url.toString());
        document.querySelectorAll('#headermenu a').forEach(function(a) {
            var linkUrl = new URL(a.href);
            linkUrl.searchParams.delete('chroot');
            if (!allVisible && visible.length > 0) {
                for (var i = 0; i < visible.length; i++) {
                    linkUrl.searchParams.append('chroot', visible[i]);
                }
            }
            a.href = linkUrl.toString();
        });
    }

    plot_element.on('plotly_restyle', updateChrootUrl);
    plot_element.on('plotly_legenddoubleclick', function() {
        setTimeout(updateChrootUrl, 0);
    });
    """

    fig.write_html(
        file=filepath,
        include_plotlyjs="cdn",
        full_html=True,
        post_script=post_script,
        div_id="plotly_div_id",
    )


def add_html_header_menu(filepath: str, plotly_div_id: str = "plotly_div_id") -> None:
    """Replace plotly's opening HTML-div element with itself and an additional
       menu so that you can navigate to different pages.

    Args:
        filepath (str): HTML file in which to do the replacement.
        plotly_div_id (str, optional): Plotly's HTML div's ID. Defaults to "plotly_div_id".
    """
    replace_me = f'<div id="{plotly_div_id}"'

    last_updated = datetime.today().strftime("%c")
    current_file = Path(filepath).name

    menu_items = [
        ("📋", "dashboard.html", "Snapshot builds dashboard"),
        ("📈", "build-times-all-states.html", "Build times (all states)"),
        ("📈", "build-times-only-succeeded.html", "Build times (only succeeded)"),
    ]

    file = Path(filepath)
    header_menu = '<div id="headermenu">'
    parts = []
    for icon, href, label in menu_items:
        if href == current_file:
            parts.append(f'{icon} <a href="{href}" style="font-weight:bold;color:inherit;text-decoration:none">{label}</a>')
        else:
            parts.append(f'{icon} <a href="{href}">{label}</a>')
    header_menu += " | ".join(parts)
    header_menu += f" <small>(Last updated: {last_updated})</small>"
    header_menu += "</div>"
    header_menu += '<script>document.addEventListener("DOMContentLoaded",function(){'
    header_menu += "var q=window.location.search;"
    header_menu += 'if(q){document.querySelectorAll("#headermenu a").forEach(function(a){'
    header_menu += "var u=new URL(a.href);"
    header_menu += "var p=new URLSearchParams(q);"
    header_menu += 'p.forEach(function(v,k){u.searchParams.append(k,v)});'
    header_menu += "a.href=u.toString();"
    header_menu += "})}"
    header_menu += "});</script>"
    header_menu += replace_me

    file.write_text(file.read_text().replace(replace_me, header_menu))


# %%
def prepare_data(filepath: str) -> pd.DataFrame:
    """Reads in data from a given file in CSV format, sort it and removes duplicates

    Args:
        filepath (str, optional): The path to the CSV file to read in.

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
        by=["date", "chroot", "timestamp"],
        inplace=True,
    )

    # We don't want a build to appear twice, so drop it based on the build_id and
    # only keep the latest information about a build.
    df.drop_duplicates(keep="last", inplace=True, subset=["build_id"])

    # Keep build time seconds as a separate column and
    # Convert seconds in the build_time column to a timedelta
    # See https://stackoverflow.com/q/76532998
    df["build_time_secs"] = df.build_time
    df.build_time = np.array(
        pd.to_timedelta(df.build_time, unit="seconds")
    ) + pd.to_datetime("1970/01/01")

    df.info()
    return df


def main() -> None:
    """The main program to prepare the data, generate figures, save them and create an index page for them."""

    parser = argparse.ArgumentParser(
        description="Create build time diagrams for a given CSV file"
    )
    parser.add_argument(
        "--datafile-big-merge",
        dest="datafile_big_merge",
        type=str,
        default="build-stats-big-merge.csv",
        help="path to your build-stats-big-merge.csv file",
    )
    args = parser.parse_args()

    # %%
    # Do some visualization preparation
    pio.renderers.default = "browser"  # See https://plotly.com/python/renderers/#setting-the-default-renderer
    pio.templates.default = (
        "plotly"  # See https://plotly.com/python/templates/#theming-and-templates
    )

    df_big_merge = prepare_data(filepath=args.datafile_big_merge)
    df_big_merge.build_id = df_big_merge.build_id.apply(lambda x: [x])

    filter = df_big_merge["state"] == "succeeded"
    df_big_merge_succeeded = df_big_merge.where(filter, inplace=False).dropna()

    # Create dedicated big-merge figure with nothing else in it.
    fig = create_figure(df=df_big_merge)
    filepath = "build-times-all-states.html"
    save_figure(fig=fig, filepath=filepath)
    add_html_header_menu(filepath=filepath)

    # Create dedicated big-merge figure with nothing else in it.
    fig = create_figure(df=df_big_merge_succeeded)
    filepath = "build-times-only-succeeded.html"
    save_figure(fig=fig, filepath=filepath)
    add_html_header_menu(filepath=filepath)


if __name__ == "__main__":
    main()
