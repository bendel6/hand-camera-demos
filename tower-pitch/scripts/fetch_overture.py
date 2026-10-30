"""Download Overture Maps open data (buildings, roads, places, land use, water) for the Tbilisi context.

Usage: python scripts/fetch_overture.py <theme> <type> <out.parquet>
Bbox covers the site plus central Tbilisi (Old Town, Freedom Square)."""
import sys, os, time
import pyarrow.compute as pc, pyarrow.dataset as ds, pyarrow.fs as pfs, pyarrow.parquet as pq

RELEASE = os.environ.get("OVERTURE_RELEASE", "2026-10-21.0")
BBOX = (44.70, 41.67, 44.86, 41.775)  # xmin, ymin, xmax, ymax

theme, typ, out = sys.argv[1], sys.argv[2], sys.argv[3]
proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
fs = pfs.S3FileSystem(anonymous=True, region="us-west-2", proxy_options=proxy) if proxy else pfs.S3FileSystem(anonymous=True, region="us-west-2")
path = f"overturemaps-us-west-2/release/{RELEASE}/theme={theme}/type={typ}/"
t0 = time.time()
dataset = ds.dataset(path, filesystem=fs, format="parquet")
xmin, ymin, xmax, ymax = BBOX
flt = ((pc.field("bbox", "xmin") < xmax) & (pc.field("bbox", "xmax") > xmin)
       & (pc.field("bbox", "ymin") < ymax) & (pc.field("bbox", "ymax") > ymin))
table = dataset.to_table(filter=flt)
pq.write_table(table, out)
print(theme, typ, table.num_rows, "rows", round(time.time() - t0), "s")
