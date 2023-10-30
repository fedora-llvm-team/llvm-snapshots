#!/bin/env python3

# %%
import argparse
import re
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.io as pio
import plotly.graph_objects as go
from plotly.offline import plot
from pathlib import Path


# %%
def create_figure(df: pd.DataFrame, package_name: str) -> go.Figure:
    """Creates a figure for a particular package name

    Args:
        df (pd.DataFrame): The complete dataframe to grab information from
        package_name (str): The package name by which to lookup information from the dataframe df

    Returns:
        go.Figure: A line figure with all chroots in one graph
    """
    df = df[df.package == package_name]
    fig = px.line(
        data_frame=df,
        x="date",
        y="build_time",
        color="chroot",
        markers=True,
        line_shape="linear",
        title='Build times for the "{}" package'.format(package_name),
        symbol="chroot",
        hover_data=["package", "date", "state", "build_id"],
        labels={
            "build_time": "Build time",
            "date": "Date",
            "chroot": "OS + Arch",
            "state": "State",
            "build_id": "Copr Build ID",
            "package": "LLVM subpackage",
        }
        # text="build_time", # To show text at each location
    )

    # TODO(kwk): Show hour, minute and seconds on the y-axis
    # fig.update_yaxes(tickformat='%H:%M:%S')

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
    plot_element.on('plotly_click', function(data){{
        console.log(data);
        var point = data.points[0];
        if (point) {{
            console.log(point.customdata);
            build_id = point.customdata[2]
            window.open('https://copr.fedorainfracloud.org/coprs/build/' + build_id);
        }}
    }})
    """

    fig.write_html(
        file=filepath, include_plotlyjs="cdn", full_html=True, post_script=post_script, div_id="plotly_div_id",
    )

def add_html_header_menu(filepath: str, all_packages: [str],  plotly_div_id: str="plotly_div_id")  -> None:
    """Replace plotly's opening HTML-div element with itself and an additional
       menu so that you can navigate from any package to any other package
       without needing to visit the index again.

    Args:
        filepath (str): HTML file in which to do the replacement.
        all_packages (str]): All the packages names for which to generate a menu entry
        plotly_div_id (str, optional): Plotly's HTML div's ID. Defaults to "plotly_div_id".
    """    
    replace_me = '<div id="{}"'.format(plotly_div_id)

    file = Path(filepath)
    header_menu = '<div id="headermenu">Build-Stats by package: '
    header_menu += " | ".join(
            [
                '<a href="fig-{package_name}.html">{package_name}</a> '.format(
                    package_name=package_name
                )
                for package_name in all_packages
            ]
        )
    header_menu += '</div>'
    header_menu += replace_me

    file.write_text(file.read_text().replace(replace_me, header_menu))


# %%
def prepare_data(filepath: str = "build-stats.csv") -> pd.DataFrame:
    """Reads in data from a given file in CSV format, sort it and removes duplicates

    Args:
        filepath (str, optional): The path to the CSV file to read in. Defaults to 'build-stats.csv'.

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

    # Convert seconds in the build_time column to a timedelta
    # See https://stackoverflow.com/q/76532998
    df.build_time = pd.to_timedelta(df.build_time, unit="seconds") + pd.to_datetime(
        "1970/01/01"
    )

    df.info()
    return df


def create_index_page(all_packages: [str], filepath: str = "index.html") -> None:
    """Create an index HTML overview page that links to each figure page

    Args:
        all_packages (str]): A list of package names
        filepath (str, optional): File name to use when saving the index page. Defaults to 'index.html'.
    """ """"""
    with open(filepath, "w") as f:
        template = """
    <!DOCTYPE html>
    <html lang="en">
        <head>
            <meta charset="utf-8" />
            <title>{title}</title>
        </head>
        <body>
            <h1>{title}</h1>
            <ul>{package_link_items}</ul>
            <hr/>
            <small>Last updated: {last_updated}</small>
        </body>
    </html>
        """
        package_link_items = "\n".join(
            [
                '<li><a href="fig-{package_name}.html">{package_name}</a></li>'.format(
                    package_name=package_name
                )
                for package_name in all_packages
            ]
        )
        html_str = template.format(
            package_link_items=package_link_items,
            title="Build times for the LLVM snapshot packages",
            last_updated=datetime.today().strftime("%c"),
        )
        f.write(html_str)


def main() -> None:
    """The main program to prepare the data, generate figures, save them and create an index page for them."""

    parser = argparse.ArgumentParser(
        description="Create build time diagrams for a given CSV file"
    )
    parser.add_argument(
        "--datafile",
        dest="datafile",
        type=str,
        default="build-stats.csv",
        help="path to your build-stats.csv file",
    )
    args = parser.parse_args()

    # %%
    # Do some visualization preparation
    pio.renderers.default = "browser"  # See https://plotly.com/python/renderers/#setting-the-default-renderer
    pio.templates.default = (
        "plotly"  # See https://plotly.com/python/templates/#theming-and-templates
    )

    # Get the data to render out
    df = prepare_data(filepath=args.datafile)

    # Get a list of unique package names and sort them
    all_packages = df.package.unique()
    all_packages.sort()

    # Create and safe a figure as an HTML file for each package.
    for package_name in all_packages:
        fig = create_figure(df=df, package_name=package_name)
        # To debug, uncomment the following:
        # fig.show()
        # break
        filepath="fig-{}.html".format(package_name)
        save_figure(fig=fig, filepath=filepath)
        add_html_header_menu(filepath=filepath, all_packages=all_packages)

    # Create an index HTML overview page that links to each figure page
    create_index_page(all_packages=all_packages, filepath="index.html")


if __name__ == "__main__":
    main()
