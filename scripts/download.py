__all__ = ["download_pdf", "download_pdfs"]


# standard library
from itertools import product
from logging import getLogger
from os import PathLike
from pathlib import Path
from typing import Literal, get_args


# dependencies
import requests
from fire import Fire


# constants
ARCHIVE_URL = "https://www.asj.or.jp/nenkai/archive"
LOGGER = getLogger(__name__)


# type hints
PresentationType = Literal["a", "b", "c"]
Season = Literal["a", "b"]
Session = Literal[
    # fmt: off
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
    "U", "V", "W", "X", "Y", "Z", "Z1", "Z2", "Z3", "Z4",
    # fmt: on
]


def download_pdf(
    year: int,
    season: Season,
    session: Session,
    number: int,
    /,
    *,
    download_dir: PathLike[str] | str = ".",
    download_timeout: float = 10.0,
) -> Path:
    """Download a PDF file from the ASJ annual meeting archive."""
    for type_ in get_args(PresentationType):
        url = f"{ARCHIVE_URL}/{year}{season}/pdf/{session}{number:02d}{type_}.pdf"
        pdf = Path(download_dir) / f"{year}-{season}-{session}-{number}.pdf"

        try:
            resp = requests.get(url, stream=True, timeout=download_timeout)
            resp.raise_for_status()
        except requests.HTTPError:
            continue

        if not pdf.parent.exists():
            pdf.parent.mkdir(parents=True, exist_ok=True)

        with open(pdf, "wb") as f:
            f.write(resp.content)

        return pdf.resolve()

    raise RuntimeError(f"No PDF found: {year=}, {season=}, {session=}, {number=}")


def download_pdfs(
    begin_year: int,
    end_year: int,
    /,
    *,
    download_dir: PathLike[str] | str = ".",
    download_timeout: float = 10.0,
    max_notfounds: int = 5,
    max_number: int = 100,
    season_subdirs: bool = True,
    session_subdirs: bool = True,
    year_subdirs: bool = True,
) -> None:
    """Download all PDF files from the ASJ annual meeting archive."""
    for year, season, session in product(
        range(begin_year, end_year + 1),
        get_args(Season),
        get_args(Session),
    ):
        notfounds = 0

        for number in range(1, max_number + 1):
            try:
                download_pdf(
                    year,
                    season,
                    session,
                    number,
                    download_dir=Path(download_dir)
                    / (str(year) * year_subdirs)
                    / (season * season_subdirs)
                    / (session * session_subdirs),
                    download_timeout=download_timeout,
                )
                notfounds = 0
            except RuntimeError as error:
                LOGGER.warning(error)
                notfounds += 1

            if notfounds >= max_notfounds:
                LOGGER.warning(f"Skipped ahead: {year=}, {season=}, {session=}")
                break


if __name__ == "__main__":
    Fire(download_pdfs)
