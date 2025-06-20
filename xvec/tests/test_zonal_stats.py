import geodatasets
import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rioxarray
import shapely
import xarray as xr

import xvec  # noqa: F401


@pytest.fixture()
def glaciers():
    sentinel_2 = rioxarray.open_rasterio(
        "https://zenodo.org/records/14906864/files/svalbard.tiff?download=1"
    )

    glaciers_df = gpd.read_file(
        "https://github.com/loreabad6/post/raw/refs/heads/main/inst/extdata/svalbard.gpkg"
    ).to_crs(sentinel_2.rio.crs)
    glaciers = (
        glaciers_df.set_index(["year", "name"])
        .to_xarray()
        .proj.assign_crs(
            spatial_ref=glaciers_df.crs
        )  # use xproj to store the CRS information
    )

    return glaciers, sentinel_2


@pytest.mark.parametrize("method", ["rasterize", "iterate", "exactextract"])
def test_structure(method):
    da = xr.DataArray(
        np.ones((10, 10, 5)),
        coords={
            "x": range(10),
            "y": range(20, 30),
            "time": pd.date_range("2023-01-01", periods=5),
        },
    )

    polygon1 = shapely.geometry.Polygon([(1, 22), (4, 22), (4, 26), (1, 26)])
    polygon2 = shapely.geometry.Polygon([(6, 22), (9, 22), (9, 29), (6, 26)])
    polygons = gpd.GeoSeries([polygon1, polygon2], crs="EPSG:4326")

    if method == "exactextract":
        expected = xr.DataArray(
            np.array([[12.0] * 5, [16.5] * 5]),
            coords={
                "geometry": polygons,
                "time": pd.date_range("2023-01-01", periods=5),
            },
        ).xvec.set_geom_indexes("geometry", crs="EPSG:4326")
    else:
        expected = xr.DataArray(
            np.array([[12.0] * 5, [18.0] * 5]),
            coords={
                "geometry": polygons,
                "time": pd.date_range("2023-01-01", periods=5),
            },
        ).xvec.set_geom_indexes("geometry", crs="EPSG:4326")
    actual = da.xvec.zonal_stats(polygons, "x", "y", stats="sum", method=method)
    xr.testing.assert_identical(actual, expected)

    actual_ix = da.xvec.zonal_stats(
        polygons, "x", "y", stats="sum", method=method, index=True
    )
    xr.testing.assert_identical(
        actual_ix, expected.assign_coords({"index": ("geometry", polygons.index)})
    )

    # dataset
    if method == "rasterize" or method == "iterate":
        ds = da.to_dataset(name="test")
        expected_ds = expected.to_dataset(name="test").set_coords("geometry")
        actual_ds = ds.xvec.zonal_stats(polygons, "x", "y", stats="sum", method=method)
        xr.testing.assert_identical(actual_ds, expected_ds)

        actual_ix_ds = ds.xvec.zonal_stats(
            polygons, "x", "y", stats="sum", method=method, index=True
        )
        xr.testing.assert_identical(
            actual_ix_ds,
            expected_ds.assign_coords({"index": ("geometry", polygons.index)}),
        )

        # named index
        polygons.index.name = "my_index"
        actual_ix_named = da.xvec.zonal_stats(
            polygons, "x", "y", stats="sum", method=method
        )
        xr.testing.assert_identical(
            actual_ix_named,
            expected.assign_coords({"my_index": ("geometry", polygons.index)}),
        )
        actual_ix_names_ds = ds.xvec.zonal_stats(
            polygons, "x", "y", stats="sum", method=method
        )
        xr.testing.assert_identical(
            actual_ix_names_ds,
            expected_ds.assign_coords({"my_index": ("geometry", polygons.index)}),
        )


def test_match():
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))
    rasterize = ds.xvec.zonal_stats(
        world.geometry, "longitude", "latitude", method="rasterize"
    )
    iterate = ds.xvec.zonal_stats(
        world.geometry, "longitude", "latitude", method="iterate"
    )

    xr.testing.assert_allclose(rasterize, iterate)


@pytest.mark.parametrize("method", ["rasterize", "iterate", "exactextract"])
def test_dataset(method):
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))
    result = ds.xvec.zonal_stats(world.geometry, "longitude", "latitude", method=method)

    if method == "exactextract":
        xr.testing.assert_allclose(
            xr.Dataset(
                {
                    "z": np.array(61625.53438858),
                    "u": np.array(4.15009377),
                    "v": np.array(-0.5161478),
                }
            ),
            result.mean(),
        )
    else:
        xr.testing.assert_allclose(
            xr.Dataset(
                {
                    "z": np.array(61367.76185577),
                    "u": np.array(4.19631497),
                    "v": np.array(-0.49170332),
                }
            ),
            result.mean(),
        )


@pytest.mark.parametrize("method", ["rasterize", "iterate", "exactextract"])
def test_dataarray(method):
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))
    result = ds.z.xvec.zonal_stats(
        world.geometry, "longitude", "latitude", method=method
    )

    assert result.shape == (127, 2, 3)
    assert result.dims == ("geometry", "month", "level")
    if method == "exactextract":
        assert result.mean() == pytest.approx(61625.53438858)
    else:
        assert result.mean() == pytest.approx(61367.76185577)


@pytest.mark.parametrize("method", ["rasterize", "iterate", "exactextract"])
def test_stat(method):
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))

    mean_ = ds.z.xvec.zonal_stats(
        world.geometry, "longitude", "latitude", method=method
    )
    median_ = ds.z.xvec.zonal_stats(
        world.geometry, "longitude", "latitude", method=method, stats="median"
    )
    if method == "exactextract":
        quantile_ = ds.z.xvec.zonal_stats(
            world.geometry,
            "longitude",
            "latitude",
            method=method,
            stats="quantile(q=0.2)",
        )
    else:
        quantile_ = ds.z.xvec.zonal_stats(
            world.geometry,
            "longitude",
            "latitude",
            method=method,
            stats="quantile",
            q=0.2,
        )

    if method == "exactextract":
        assert mean_.mean() == pytest.approx(61625.53438858)
        assert median_.mean() == pytest.approx(61628.67168691)
        assert quantile_.mean() == pytest.approx(61540.75632235)
    else:
        assert mean_.mean() == pytest.approx(61367.76185577)
        assert median_.mean() == pytest.approx(61370.18563539)
        assert quantile_.mean() == pytest.approx(61279.93619836)


@pytest.mark.parametrize("method", ["rasterize", "iterate"])
def test_all_touched(method):
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))

    default = ds.z.xvec.zonal_stats(
        world.geometry[:10],
        "longitude",
        "latitude",
        all_touched=False,
        stats="sum",
        method=method,
    )
    touched = ds.z.xvec.zonal_stats(
        world.geometry[:10],
        "longitude",
        "latitude",
        all_touched=True,
        stats="sum",
        method=method,
    )

    assert (default < touched).all()


def test_n_jobs():
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))

    one = ds.xvec.zonal_stats(
        world.geometry[:10], "longitude", "latitude", method="iterate", n_jobs=1
    )
    default = ds.xvec.zonal_stats(
        world.geometry[:10], "longitude", "latitude", method="iterate", n_jobs=1
    )

    xr.testing.assert_identical(one, default)


def test_method_error():
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))
    with pytest.raises(ValueError, match="method 'quick' is not supported"):
        ds.xvec.zonal_stats(world.geometry, "longitude", "latitude", method="quick")


@pytest.mark.parametrize("method", ["rasterize", "iterate"])
def test_crs(method):
    da = xr.DataArray(
        np.ones((10, 10, 5)),
        coords={
            "x": range(10),
            "y": range(20, 30),
            "time": pd.date_range("2023-01-01", periods=5),
        },
    )

    polygon1 = shapely.geometry.Polygon([(1, 22), (4, 22), (4, 26), (1, 26)])
    polygon2 = shapely.geometry.Polygon([(6, 22), (9, 22), (9, 29), (6, 26)])
    polygons = np.array([polygon1, polygon2])

    expected = xr.DataArray(
        np.array([[12.0] * 5, [18.0] * 5]),
        coords={
            "geometry": polygons,
            "time": pd.date_range("2023-01-01", periods=5),
        },
    ).xvec.set_geom_indexes("geometry", crs=None)

    if method == "exactextract":
        with pytest.raises(
            AttributeError,
            match="Geometry input does not have a Coordinate Reference System",
        ):
            da.xvec.zonal_stats(polygons, "x", "y", stats="sum", method=method)
    else:
        actual = da.xvec.zonal_stats(polygons, "x", "y", stats="sum", method=method)
        xr.testing.assert_identical(actual, expected)


@pytest.mark.parametrize("method", ["rasterize", "iterate"])
def test_callable(method):
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))
    ds_agg = ds.xvec.zonal_stats(
        world.geometry, "longitude", "latitude", method=method, stats=np.nanstd
    )
    ds_std = ds.xvec.zonal_stats(
        world.geometry, "longitude", "latitude", method=method, stats="std"
    )
    xr.testing.assert_identical(ds_agg, ds_std)

    da_agg = ds.z.xvec.zonal_stats(
        world.geometry,
        "longitude",
        "latitude",
        method=method,
        stats=np.nanstd,
        n_jobs=1,
    )
    da_std = ds.z.xvec.zonal_stats(
        world.geometry, "longitude", "latitude", method=method, stats="std"
    )
    xr.testing.assert_identical(da_agg, da_std)


@pytest.mark.parametrize("method", ["rasterize", "iterate", "exactextract"])
def test_multiple(method):
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))
    if method == "exactextract":
        result = ds.xvec.zonal_stats(
            world.geometry[:10].boundary,
            "longitude",
            "latitude",
            stats=[
                "mean",
                "sum",
                "quantile(q=0.20)",
            ],
            method=method,
            n_jobs=1,
        )
        assert sorted(result.dims) == sorted(
            [
                "level",
                "zonal_statistics",
                "geometry",
                "month",
            ]
        )

        assert (result.zonal_statistics == ["mean", "sum", "quantile(q=0.20)"]).all()
    else:
        result = ds.xvec.zonal_stats(
            world.geometry[:10].boundary,
            "longitude",
            "latitude",
            stats=[
                "mean",
                "sum",
                ("quantile", "quantile", {"q": [0.1, 0.2, 0.3]}),
                ("numpymean", np.nanmean),
                np.nanmean,
            ],
            method=method,
            n_jobs=1,
        )
        assert sorted(result.dims) == sorted(
            [
                "level",
                "zonal_statistics",
                "geometry",
                "month",
                "quantile",
            ]
        )

        assert (
            result.zonal_statistics
            == ["mean", "sum", "quantile", "numpymean", "nanmean"]
        ).all()


@pytest.mark.parametrize("method", ["rasterize", "iterate", "exactextract"])
def test_invalid(method):
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))
    with pytest.raises(ValueError, match=r"\['gorilla'\] is not a valid aggregation."):
        ds.xvec.zonal_stats(
            world.geometry[:10].boundary,
            "longitude",
            "latitude",
            stats=[
                "mean",
                ["gorilla"],
            ],
            method=method,
            n_jobs=1,
        )

    with pytest.raises(ValueError, match="3 is not a valid aggregation."):
        ds.xvec.zonal_stats(
            world.geometry[:10].boundary,
            "longitude",
            "latitude",
            stats=3,
            method=method,
            n_jobs=1,
        )


def test_variable_geometry_multiple(glaciers):
    da, sentinel_2 = glaciers

    result = sentinel_2.xvec.zonal_stats(
        da.geometry,
        x_coords="x",
        y_coords="y",
        stats=[
            "mean",
            "sum",
            ("numpymean", np.nanmean),
            np.nanmean,
        ],
    )

    assert result.sizes == {"year": 3, "name": 5, "zonal_statistics": 4, "band": 11}
    assert result.statistics.mean() == 17067828


def test_variable_geometry_single(glaciers):
    da, sentinel_2 = glaciers

    result = sentinel_2.xvec.zonal_stats(
        da.geometry,
        x_coords="x",
        y_coords="y",
        stats="mean",
    )

    assert result.sizes == {"year": 3, "name": 5, "band": 11}
    assert result.statistics.mean() == 13168.585


def test_exactextract_strategy():
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))

    result_feature_sequential = ds.z.xvec.zonal_stats(
        world.geometry,
        "longitude",
        "latitude",
        method="exactextract",
        strategy="feature-sequential",
    )
    result_raster_sequential = ds.z.xvec.zonal_stats(
        world.geometry,
        "longitude",
        "latitude",
        method="exactextract",
        strategy="raster-sequential",
    )

    xr.testing.assert_allclose(result_feature_sequential, result_raster_sequential)

    with pytest.raises(KeyError):
        ds.z.xvec.zonal_stats(
            world.geometry,
            "longitude",
            "latitude",
            method="exactextract",
            strategy="invalid_strategy",
        )


@pytest.mark.parametrize("method", ["rasterize", "iterate", "exactextract"])
def test_nodata(method):
    ds = xr.tutorial.open_dataset("eraint_uvz")
    world = gpd.read_file(geodatasets.get_path("naturalearth land"))

    arr = ds.z.where(ds.z > ds.z.mean(), -9999)
    unmasked = arr.xvec.zonal_stats(
        world.geometry, "longitude", "latitude", method=method
    )
    masked = arr.xvec.zonal_stats(
        world.geometry, "longitude", "latitude", method=method, nodata=-9999
    )

    assert unmasked.mean() < masked.mean()
