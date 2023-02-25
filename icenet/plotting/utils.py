import datetime as dt
import glob
import logging
import os
import re

import cartopy.crs as ccrs
import matplotlib.cm as cm
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr


from ibicus.debias import LinearScaling

from icenet.process.forecasts import broadcast_forecast


def get_seas_forecast_da(hemisphere: str,
                         date: str,
                         bias_correct: bool = True,
                         source_path: object = os.path.join(".", "data", "mars.seas"),
                         ) -> tuple:
    """
    Atmospheric model Ensemble 15-day forecast (Set III - ENS)

Coordinates:
  * time                          (time) datetime64[ns] 2022-04-01 ... 2022-0...
  * yc                            (yc) float64 5.388e+06 ... -5.388e+06
  * xc                            (xc) float64 -5.388e+06 ... 5.388e+06

    :param hemisphere:
    :param date:
    :param bias_correct:
    :param source_path:
    """

    seas_file = os.path.join(
        source_path,
        hemisphere,
        "siconca",
        "{}.nc".format(date.strftime("%Y%m%d")))
    seas_da = xr.open_dataset(seas_file).siconc

    if bias_correct:
        # Let's have some maximum, though it's quite high
        (start_date, end_date) = (
            date - dt.timedelta(days=10 * 365),
            date + dt.timedelta(days=10 * 365)
        )
        obs_da = get_obs_da(hemisphere, start_date, end_date)
        seas_hist_files = dict(sorted({os.path.abspath(el):
                                       dt.datetime.strptime(
                                       os.path.basename(el)[0:8], "%Y%m%d")
                                      for el in
                                      glob.glob(os.path.join(source_path,
                                                             hemisphere,
                                                             "siconca",
                                                             "*.nc"))
                                      if re.search(r'^\d{8}\.nc$',
                                                   os.path.basename(el))
                                      and el != seas_file}.items()))

        def strip_overlapping_time(ds):
            data_file = os.path.abspath(ds.encoding["source"])

            try:
                idx = list(seas_hist_files.keys()).index(data_file)
            except ValueError:
                logging.exception("\n{} not in \n\n{}".format(data_file,
                                                              seas_hist_files))
                return None

            if idx < len(seas_hist_files) - 1:
                max_date = seas_hist_files[
                               list(seas_hist_files.keys())[idx + 1]] \
                           - dt.timedelta(days=1)
                logging.debug("Stripping {} to {}".format(data_file, max_date))
                return ds.sel(time=slice(None, max_date))
            else:
                logging.debug("Not stripping {}".format(data_file))
                return ds

        hist_da = xr.open_mfdataset(seas_hist_files,
                                    preprocess=strip_overlapping_time).siconc
        debiaser = LinearScaling(delta_type="additive",
                                 variable="siconc",
                                 reasonable_physical_range=[0., 1.])

        logging.info("Debiaser input ranges: obs {:.2f} - {:.2f}, "
                     "hist {:.2f} - {:.2f}, fut {:.2f} - {:.2f}".
                     format(float(obs_da.min()), float(obs_da.max()),
                            float(hist_da.min()), float(hist_da.max()),
                            float(seas_da.min()), float(seas_da.max())))

        seas_array = debiaser.apply(obs_da.values,
                                    hist_da.values,
                                    seas_da.values)
        seas_da.values = seas_array
        logging.info("Debiaser output range: {:.2f} - {:.2f}".
                     format(float(seas_da.min()), float(seas_da.max())))
    return seas_da


def get_forecast_ds(forecast_file: object,
                    forecast_date: str,
                    stddev: bool = False
                    ) -> tuple:
    """

    :param forecast_file:
    :param forecast_date:
    :param stddev:
    :returns tuple(fc_ds, obs_ds, land_mask):
    """
    forecast_date = pd.to_datetime(forecast_date)

    forecast_ds = xr.open_dataset(forecast_file)
    get_key = "sic_mean" if not stddev else "sic_stddev"

    forecast_ds = getattr(
        forecast_ds.sel(time=slice(forecast_date, forecast_date)),
        get_key)

    return forecast_ds


def filter_ds_by_obs(ds: object,
                     obs_da: object,
                     forecast_date: str) -> object:
    """

    :param ds:
    :param obs_da:
    :param forecast_date:
    :return:
    """
    forecast_date = pd.to_datetime(forecast_date)
    (start_date, end_date) = (
            forecast_date + dt.timedelta(days=int(ds.leadtime.min())),
            forecast_date + dt.timedelta(days=int(ds.leadtime.max()))
    )

    if len(obs_da.time) < len(ds.leadtime):
        if len(obs_da.time) < 1:
            raise RuntimeError("No observational data available between {} "
                               "and {}".format(start_date.strftime("%D"),
                                               end_date.strftime("%D")))

        logging.warning("Observational data not available for full range of "
                        "forecast lead times: {}-{} vs {}-{}".format(
                         obs_da.time.to_series()[0].strftime("%D"),
                         obs_da.time.to_series()[-1].strftime("%D"),
                         start_date.strftime("%D"),
                         end_date.strftime("%D")))
        (start_date, end_date) = (
            obs_da.time.to_series()[0],
            obs_da.time.to_series()[-1]
        )

    # We broadcast to get a nicely compatible dataset for plotting
    return broadcast_forecast(start_date=start_date,
                              end_date=end_date,
                              dataset=ds)


def get_obs_da(hemisphere: str,
               start_date: str,
               end_date: str,
               obs_source: object =
               os.path.join(".", "data", "osisaf"),
               ) -> object:
    """

    :param hemisphere:
    :param start_date:
    :param end_date:
    :param obs_source:
    :return:
    """
    obs_years = pd.Series(pd.date_range(start_date, end_date)).dt.year.unique()
    obs_dfs = [el for yr in obs_years for el in
               glob.glob(os.path.join(obs_source,
                                      hemisphere,
                                      "siconca", "{}.nc".format(yr)))]

    if len(obs_dfs) < len(obs_years):
        logging.warning("Cannot find all obs source files for {} - {} in {}".
                        format(start_date, end_date, obs_source))

    logging.info("Got files: {}".format(obs_dfs))
    obs_ds = xr.open_mfdataset(obs_dfs)
    obs_ds = obs_ds.sel(time=slice(start_date, end_date))

    return obs_ds.ice_conc


def calculate_data_extents(x1: int,
                           x2: int,
                           y1: int,
                           y2: int):
    """

    :param x1:
    :param x2:
    :param y1:
    :param y2:
    :return:
    """
    data_extent_estimate = 5400000.0    # 216 * 25000

    return [-(data_extent_estimate) + (x1 * 25000),
            data_extent_estimate - ((432 - x2) * 25000),
            -(data_extent_estimate) + ((432 - y2) * 25000),
            data_extent_estimate - (y1 * 25000)]


def calculate_proj_extents(x1: int,
                           x2: int,
                           y1: int,
                           y2: int):
    """

    :param x1:
    :param x2:
    :param y1:
    :param y2:
    :return:
    """
    data_extent_estimate = 5400000.0    # 216 * 25000

    return [-(data_extent_estimate) + (y1 * 25000),
            data_extent_estimate - ((432 - y2) * 25000),
            -(data_extent_estimate) + (x1 * 25000),
            data_extent_estimate - ((432 - x2) * 25000)]


def get_plot_axes(x1: int = 0,
                  x2: int = 432,
                  y1: int = 0,
                  y2: int = 432,
                  do_coastlines: bool = True):
    """

    :param x1:
    :param x2:
    :param y1:
    :param y2:
    :param do_coastlines:
    :return:
    """
    fig = plt.figure(figsize=(10, 8), dpi=150, layout='tight')

    if do_coastlines:
        proj = ccrs.LambertAzimuthalEqualArea(-90, 90)
        ax = fig.add_subplot(1, 1, 1, projection=proj)
        bounds = calculate_proj_extents(x1, x2, y1, y2)
        ax.set_extent(bounds, crs=proj)
    else:
        ax = fig.add_subplot(1, 1, 1)

    return ax


def show_img(ax,
             arr,
             x1: int = 0,
             x2: int = 432,
             y1: int = 0,
             y2: int = 432,
             cmap: object = None,
             do_coastlines: bool = True):
    """

    :param ax:
    :param arr:
    :param x1:
    :param x2:
    :param y1:
    :param y2:
    :param cmap:
    :param do_coastlines:
    :return:
    """

    if do_coastlines:
        data_globe = ccrs.Globe(datum="WGS84",
                                inverse_flattening=298.257223563,
                                semimajor_axis=6378137.0)
        data_crs = ccrs.LambertAzimuthalEqualArea(0, 90, globe=data_globe)

        im = ax.imshow(arr,
                       vmin=0.,
                       vmax=1.,
                       cmap=cmap,
                       transform=data_crs,
                       extent=calculate_data_extents(x1, x2, y1, y2))
        ax.coastlines()
    else:
        im = ax.imshow(arr, cmap=cmap, vmin=0., vmax=1.)

    return im

