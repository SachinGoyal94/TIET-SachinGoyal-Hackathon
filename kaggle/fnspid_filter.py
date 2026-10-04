# Kaggle CPU kernel: filter the FNSPID financial news dataset (27.4M headlines,
# 2000-2024, with tickers) down to our 14-ticker index universe.
#
# Output: /kaggle/working/fnspid_universe.csv
#         columns: ticker, date (UTC), title

import glob
import os

os.environ.setdefault("USE_TF", "0")

import pandas as pd

TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "JPM", "BAC",
           "GS", "XOM", "CVX", "WMT", "KO", "BA"]

SRC_REPO = "Zihan1004/FNSPID"
SRC_FILE = "Stock_news/nasdaq_exteral_data.csv"
OUT = "/kaggle/working/fnspid_universe.csv"


def download_source() -> str:
    # reuse an existing copy if a previous session left one
    for path in glob.glob("/kaggle/working/**/nasdaq_exteral_data.csv", recursive=True):
        if os.path.getsize(path) > 1e9:
            print("reusing", path, flush=True)
            return path
    from huggingface_hub import hf_hub_download

    print("downloading 23GB source (Kaggle pipe, resumable)...", flush=True)
    path = hf_hub_download(SRC_REPO, SRC_FILE, repo_type="dataset")
    print("downloaded:", path, flush=True)
    return path


def main():
    src = download_source()
    matches = []
    rows_seen = 0
    for chunk in pd.read_csv(src, usecols=["Date", "Article_title", "Stock_symbol"],
                             chunksize=2_000_000):
        rows_seen += len(chunk)
        sub = chunk[chunk["Stock_symbol"].isin(TICKERS)]
        if len(sub):
            matches.append(sub)
        print(f"scanned {rows_seen:,} rows, matched {sum(len(m) for m in matches):,}",
              flush=True)

    df = pd.concat(matches, ignore_index=True) if matches else pd.DataFrame(
        columns=["Date", "Article_title", "Stock_symbol"])
    df["Date"] = pd.to_datetime(df["Date"], format="mixed", errors="coerce", utc=True)
    df = df.dropna(subset=["Date"])
    df = df[df["Article_title"].astype(str).str.len() > 10]
    df = df.rename(columns={"Date": "date", "Article_title": "title",
                            "Stock_symbol": "ticker"})
    df["date"] = df["date"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    df = df.sort_values("date")
    df.to_csv(OUT, index=False)

    print("per-ticker counts:", dict(df["ticker"].value_counts()), flush=True)
    print("date range:", df["date"].min(), "->", df["date"].max(), flush=True)
    print(f"saved {len(df)} rows -> {OUT}", flush=True)


if __name__ == "__main__":
    main()
