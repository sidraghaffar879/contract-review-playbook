"""python -m contractreview.cli samples/vendor_msa.txt [--playbook my.yaml] -> out/<doc>.md + .json"""
from __future__ import annotations

import argparse
from pathlib import Path

from .review import ContractReviewer, to_json, to_markdown


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="*", default=["samples/vendor_msa.txt"])
    p.add_argument("--playbook", default=None)
    p.add_argument("--out", default="out")
    a = p.parse_args(argv)
    rv = ContractReviewer(a.playbook)
    Path(a.out).mkdir(exist_ok=True)
    for f in a.files:
        r = rv.review(f)
        md = to_markdown(r)
        (Path(a.out) / f"{Path(f).stem}.md").write_text(md)
        (Path(a.out) / f"{Path(f).stem}.json").write_text(to_json(r))
        print(md)


if __name__ == "__main__":
    main()
