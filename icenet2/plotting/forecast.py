import argparse
import logging
import os

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

import pandas as pd

from icenet2.data.cli import date_arg
from icenet2.plotting.utils import get_forecast_obs_ds

matplotlib.rcParams.update({
    'figure.facecolor': 'w',
    'figure.dpi': 300
})


def plot_sic_error(fc_da: object,
                   obs_da: object,
                   land_mask: object,
                   output_path: object =
                   os.path.join("plot", "sic_error.mp4")) -> object:
    """

    :param fc_da:
    :param obs_da:
    :param land_mask:
    :param output_path:
    """

    diff = fc_da - obs_da

    def update(date):
        logging.debug("Plotting {}".format(date))

        maps[0].set_title("IceNet {}".format(
            pd.to_datetime(fc_da.isel(time=leadtime).time.values).strftime("%d/%m/%Y")))
        maps[1].set_title("OSISAF Obs {}".format(
            pd.to_datetime(obs_da.isel(time=leadtime).time.values).strftime("%d/%m/%Y")))

        maps[0].contourf(fc_plot, **contour_kwargs)
        maps[1].contourf(obs_plot, **contour_kwargs)
        maps[2].contourf(diff_plot, **diff_kwargs,
                         vmin=-1, vmax=1, cmap="RdBu_r")

        return maps

    fig, maps = plt.subplots(nrows=1, ncols=3, figsize=(18, 5))
    fig.set_dpi(150)

    leadtime = 0
    fc_plot = fc_da.isel(time=leadtime).to_numpy()
    obs_plot = obs_da.isel(time=leadtime).to_numpy()
    diff_plot = diff.isel(time=leadtime).to_numpy()

    contour_kwargs = dict(
        levels=200,
        vmin=0,
        vmax=1,
        cmap='YlOrRd'
    )
    diff_kwargs = {k: v for k, v in contour_kwargs.items()
                   if k not in ["vmin", "vmax", "cmap"]}

    ctf = maps[0].contourf(fc_plot, **contour_kwargs)
    cto = maps[1].contourf(obs_plot, **contour_kwargs)
    ctd = maps[2].contourf(diff_plot, **diff_kwargs,
                           vmin=-1, vmax=1, cmap="RdBu_r")

    maps[0].set_title("IceNet {}".format(
        pd.to_datetime(fc_da.isel(time=leadtime).time.values).strftime("%d/%m/%Y")))
    maps[1].set_title("OSISAF Obs {}".format(
        pd.to_datetime(obs_da.isel(time=leadtime).time.values).strftime("%d/%m/%Y")))
    maps[2].set_title("Diff")

    p0 = maps[0].get_position().get_points().flatten()
    p1 = maps[1].get_position().get_points().flatten()
    p2 = maps[2].get_position().get_points().flatten()

    ax_cbar = fig.add_axes([p0[0], 0, p1[2]-p0[0], 0.05])
    plt.colorbar(cto, cax=ax_cbar, orientation='horizontal')

    ax_cbar1 = fig.add_axes([p2[0], 0, p2[2]-p2[0], 0.05])
    plt.colorbar(ctd, cax=ax_cbar1, orientation='horizontal')

    for m_ax in maps[0:3]:
        m_ax.contourf(land_mask,
                      levels=[.5, 1],
                      colors=[matplotlib.cm.gray(180)],
                      zorder=3)

    fig.subplots_adjust(hspace=0.2, wspace=0.2)

    animation = FuncAnimation(fig,
                              update,
                              range(0, len(fc_da.time)),
                              blit=True,
                              interval=100)

    plt.close()

    logging.info("Saving plot to {}".format(output_path))
    animation.save(output_path,
                   fps=10,
                   extra_args=['-vcodec', 'libx264'])
    return animation


def sic_error_args() -> object:
    """

    :return:
    """

    ap = argparse.ArgumentParser()
    ap.add_argument("hemisphere", choices=("north", "south"))
    ap.add_argument("forecast_file", type=str)
    ap.add_argument("forecast_date", type=date_arg)

    ap.add_argument("-o", "--output-path", type=str,
                    default=os.path.join("plot", "sic_error.mp4"))
    ap.add_argument("-v", "--verbose", action="store_true", default=False)

    args = ap.parse_args()
    return args


def sic_error():
    args = sic_error_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)

    plot_sic_error(*get_forecast_obs_ds(args.hemisphere,
                                        args.forecast_file,
                                        args.forecast_date),
                   output_path=args.output_path)
