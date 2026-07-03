"""Write the synthetic insurance corpus to disk for manual demo uploads.

Usage: PYTHONPATH=src:. python scripts/build_corpus.py [output_dir]
"""

import pathlib
import sys

from evals.corpus import build_corpus


def main() -> None:
    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "corpus-out")
    out.mkdir(parents=True, exist_ok=True)
    for doc in build_corpus():
        (out / doc.filename).write_bytes(doc.data)
    print(f"wrote {len(build_corpus())} documents to {out}/")  # noqa: T201


if __name__ == "__main__":
    main()
