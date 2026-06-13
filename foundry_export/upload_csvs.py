"""
Upload the five CSVs into the five Foundry datasets.

Uses raw v2 REST (the SDK doesn't expose list-transactions so we'd have a
chicken-and-egg with stale txns otherwise). Token is unwrapped from the
JSON envelope that pltr-cli stores in the macOS keyring.

NOTE on schemas: this script only writes files and commits the transaction.
After the first upload of each dataset, apply/infer the dataset schema in
Foundry (dataset page → "Apply schema", or Pipeline Builder will prompt on
first use) so the CSV columns become typed; subsequent snapshot uploads
keep the applied schema.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import keyring
import requests

HOST = "https://srujan.usw-17.palantirfoundry.com"
PREVIEW = {"preview": "true"}

DATASETS = {
    "patients":        "ri.foundry.main.dataset.7e038603-c23a-464e-b9ee-82ae89cac324",
    "notes":           "ri.foundry.main.dataset.190b06d9-958e-497e-be65-ad37ae144335",
    "protocols":       "ri.foundry.main.dataset.f59fec67-924c-45e8-ac9d-fd35170dbfaf",
    "icd10_reference": "ri.foundry.main.dataset.75d3fdec-654a-48e3-b5de-104ad9aef25f",
    # eval_labels holds the held-out ground truth (split out of patients.csv
    # so the Workshop Patient object never carries labels). Create a new
    # dataset in the bottleneck-radar project's raw/ folder, then paste its
    # RID here before running.
    "eval_labels":     "ri.foundry.main.dataset.REPLACE-WITH-EVAL-LABELS-RID",
    # note_versions holds prior notes (clinical history) for the trajectory
    # panel. Optional — only needed if you build the trajectory Function.
    # Create the dataset and paste its RID, or leave the placeholder to skip.
    "note_versions":   "ri.foundry.main.dataset.REPLACE-WITH-NOTE-VERSIONS-RID",
}


def get_token() -> str:
    blob = keyring.get_password("pltr-cli", "default")
    if not blob:
        sys.exit("no token found in keyring under pltr-cli/default")
    return json.loads(blob)["token"]


def find_open_txn(sess: requests.Session, dataset_rid: str) -> str | None:
    """Returns rid of an OPEN transaction on master branch, if any."""
    # Branches endpoint includes the latest transaction_rid per branch
    r = sess.get(
        f"{HOST}/api/v2/datasets/{dataset_rid}/branches/master",
        params=PREVIEW,
    )
    if r.status_code != 200:
        return None
    body = r.json()
    txn_rid = body.get("transactionRid")
    if not txn_rid:
        return None
    r = sess.get(
        f"{HOST}/api/v2/datasets/{dataset_rid}/transactions/{txn_rid}",
        params=PREVIEW,
    )
    if r.status_code == 200 and r.json().get("status") == "OPEN":
        return txn_rid
    return None


def abort_txn(sess: requests.Session, dataset_rid: str, txn_rid: str) -> None:
    r = sess.post(
        f"{HOST}/api/v2/datasets/{dataset_rid}/transactions/{txn_rid}/abort",
        params=PREVIEW,
    )
    r.raise_for_status()


def start_txn(sess: requests.Session, dataset_rid: str) -> str:
    r = sess.post(
        f"{HOST}/api/v2/datasets/{dataset_rid}/transactions",
        params={**PREVIEW, "branchName": "master"},
        json={"transactionType": "SNAPSHOT"},
    )
    r.raise_for_status()
    return r.json()["rid"]


def upload_file(sess: requests.Session, dataset_rid: str, txn_rid: str,
                file_path: Path) -> None:
    with file_path.open("rb") as f:
        r = sess.post(
            f"{HOST}/api/v2/datasets/{dataset_rid}/files/{file_path.name}/upload",
            params={**PREVIEW, "transactionRid": txn_rid},
            data=f.read(),
            headers={"Content-Type": "application/octet-stream"},
        )
    r.raise_for_status()


def commit_txn(sess: requests.Session, dataset_rid: str, txn_rid: str) -> None:
    r = sess.post(
        f"{HOST}/api/v2/datasets/{dataset_rid}/transactions/{txn_rid}/commit",
        params=PREVIEW,
    )
    r.raise_for_status()


def upload_one(sess: requests.Session, name: str, dataset_rid: str,
               csv_path: Path) -> None:
    print(f"\n=== {name} ({csv_path.name}, {csv_path.stat().st_size}b) ===")

    # Never reuse a dangling OPEN transaction — its contents are arbitrary
    # (a half-finished upload from a previous run, possibly other files).
    # Abort it and start a fresh SNAPSHOT so every commit is exactly one CSV.
    stale = find_open_txn(sess, dataset_rid)
    if stale:
        abort_txn(sess, dataset_rid, stale)
        print(f"  aborted stale open txn {stale}")
    txn = start_txn(sess, dataset_rid)
    print(f"  started txn {txn}")

    upload_file(sess, dataset_rid, txn, csv_path)
    print(f"  uploaded {csv_path.name}")

    commit_txn(sess, dataset_rid, txn)
    print(f"  ✓ committed")


def main() -> None:
    here = Path(__file__).resolve().parent
    sess = requests.Session()
    sess.headers["Authorization"] = f"Bearer {get_token()}"

    for name, rid in DATASETS.items():
        if "REPLACE-WITH" in rid:
            print(f"\n=== {name} ===\n  ! placeholder RID — create the dataset "
                  f"in Foundry and paste its RID into DATASETS; skipping")
            continue
        csv = here / f"{name}.csv"
        if not csv.exists():
            print(f"  ! {csv} missing; skipping")
            continue
        try:
            upload_one(sess, name, rid, csv)
        except requests.HTTPError as e:
            body = e.response.text[:400]
            print(f"  ✗ HTTP {e.response.status_code}: {body}")
            sys.exit(1)

    print("\nall datasets uploaded.")


if __name__ == "__main__":
    main()
