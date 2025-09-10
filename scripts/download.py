# standard library
import asyncio
import re
from collections.abc import Iterator
from csv import writer as csv_writer
from itertools import product
from os import PathLike
from pathlib import Path


# dependencies
import pandas as pd
import requests
from bs4 import BeautifulSoup
from fire import Fire
from httpx import AsyncClient
from pylatexenc.latex2text import LatexNodes2Text
from tqdm import tqdm
from tqdm.asyncio import tqdm as async_tqdm


# constants
ARCHIVE_URL = "https://www.asj.or.jp/nenkai/archive"
MEETING_SEASONS = "a", "b"
PRESENTATION_TYPES = "a", "b", "c", "r"
SESSION_URL = re.compile(r"session-([A-Z][0-9]*)\.html")
PRESENTATION_URL = re.compile(r"([A-Z][0-9]+[a-z])\.pdf")


def download_abstracts(
    begin_year: int,
    end_year: int,
    /,
    *,
    outdir: PathLike[str] | str = ".",
    parallel: int = 10,
    progress: bool = True,
    timeout: float = 10.0,
) -> Path:
    """Download abstracts of the ASJ annual meetings.

    Args:
        begin_year: First year to download (inclusive).
        end_year: Last year to download (inclusive).
        outdir: Output directory to save the CSV file and abstracts.
        parallel: Number of parallel downloads.
        progress: Whether to show a progress bar.
        timeout: Timeout for each download request in seconds.

    Returns:
        Path of the CSV file listing presentations with abstract paths.

    """
    csv = list_presentations(
        begin_year,
        end_year,
        outdir=outdir,
        progress=progress,
        timeout=timeout,
    )
    presentations = pd.read_csv(csv)
    semaphore = asyncio.Semaphore(parallel)

    async def download_one(row: pd.Series, /, *, client: AsyncClient) -> Path:
        async with semaphore:
            resp = await client.get(row["Abstract"], timeout=timeout)
            resp.raise_for_status()

            pdf = (
                Path(outdir)
                / "abstracts"
                / str(row["Year"])
                / row["Season"]
                / row["Session number"]
                / f"{row['Presentation number']}.pdf"
            )
            pdf.parent.mkdir(parents=True, exist_ok=True)
            pdf.write_bytes(resp.content)
            return pdf.expanduser().resolve()

    async def download_all() -> list[Path]:
        async with AsyncClient() as client:
            tasks: list[Iterator[Path]] = []

            for _, row in presentations.iterrows():
                tasks.append(download_one(row, client=client))

            if progress:
                return await async_tqdm.gather(*tasks)
            else:
                return await asyncio.gather(*tasks)

    presentations["Abstract"] = asyncio.run(download_all())
    presentations.to_csv(csv, index=False)
    return csv.expanduser().resolve()


def list_presentations(
    begin_year: int,
    end_year: int,
    /,
    *,
    outdir: PathLike[str] | str = ".",
    progress: bool = True,
    timeout: float = 10.0,
) -> Path:
    """List presentations of the ASJ annual meetings in CSV format.

    Args:
        begin_year: First year to list (inclusive).
        end_year: Last year to list (inclusive).
        outdir: Output directory to save the CSV file.
        progress: Whether to show a progress bar.
        timeout: Timeout for each download request in seconds.

    Returns:
        Path of the CSV file listing presentations with abstract URLs.

    """

    with open(csv := Path(outdir) / "presentations.csv", "w") as f:
        writer = csv_writer(f)
        converter = LatexNodes2Text().latex_to_text

        writer.writerow(
            (
                "Year",
                "Season",
                "Session number",
                "Session title",
                "Presentation number",
                "Presentation title",
                "Abstract",
            )
        )

        for year, season in tqdm(
            list(product(range(begin_year, end_year + 1), MEETING_SEASONS)),
            disable=not progress,
        ):
            for s_number, s_title in get_sessions(
                year,
                season,
                timeout=timeout,
            ).items():
                for p_number, p_title in get_presentations(
                    year,
                    season,
                    s_number,
                    timeout=timeout,
                ).items():
                    writer.writerow(
                        (
                            year,
                            season,
                            s_number,
                            converter(s_title),
                            p_number,
                            converter(p_title),
                            f"{ARCHIVE_URL}/{year}{season}/pdf/{p_number}.pdf",
                        )
                    )

    return csv.expanduser().resolve()


def get_presentations(
    year: int,
    season: str,
    session: str,
    /,
    *,
    timeout: float = 10.0,
) -> dict[str, str]:
    """Get presentations {<number>: <title>, ...}.

    Args:
        year: Year of the meeting.
        season: Season of the meeting ('a' or 'b').
        session: Session number (e.g., 'A', 'B', etc.).
        timeout: Timeout for the request in seconds.

    Returns:
        Dictionary mapping presentation numbers to titles.

    """
    presentations: dict[str, str] = {}

    url = f"{ARCHIVE_URL}/{year}{season}/session-{session}.html"
    resp = requests.get(url, stream=True, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content.decode(), "html.parser")

    for tag in soup.find_all("a"):
        if "href" not in tag.attrs:
            continue

        if match := PRESENTATION_URL.search(tag["href"]):
            presentations[match.group(1)] = tag.get_text()

    return presentations


def get_sessions(
    year: int,
    season: str,
    /,
    *,
    timeout: float = 10.0,
) -> dict[str, str]:
    """Get sessions {<number>: <title>, ...}.

    Args:
        year: Year of the meeting.
        season: Season of the meeting ('a' or 'b').
        timeout: Timeout for the request in seconds.

    Returns:
        Dictionary mapping session numbers to titles.

    """
    sessions: dict[str, str] = {}

    url = f"{ARCHIVE_URL}/{year}{season}/index.html"
    resp = requests.get(url, stream=True, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content.decode(), "html.parser")

    for tag in soup.find_all("a"):
        if "href" not in tag.attrs:
            continue

        if match := SESSION_URL.search(tag["href"]):
            sessions[match.group(1)] = tag.get_text()

    return sessions


if __name__ == "__main__":
    Fire(
        {
            "download": download_abstracts,
            "list": list_presentations,
        }
    )
