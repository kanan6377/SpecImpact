import hashlib
import json
import subprocess

import pytest
import yaml

from specimpact.benchmarks.fintan import (
    FINTAN_COMMIT,
    FINTAN_REPOSITORY,
    FintanManifestError,
    _validate_corpus_provenance,
    fetch_fintan_corpus,
)


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for path, content in {"a.xlsx": b"alpha", "nested/b.xlsx": b"bravo"}.items():
        destination = repo / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    def git(*args):
        return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    git("init", "--quiet")
    git("config", "user.email", "tests@example.invalid")
    git("config", "user.name", "Offline Tests")
    git("add", ".")
    git("commit", "--quiet", "-m", "fixture")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    return repo, commit


def _manifest(path, repository, commit, files):
    path.write_text(
        yaml.safe_dump(
            {
                "metadata": {"repository": repository, "commit": commit, "file_count": len(files)},
                "files": files,
            }
        ),
        encoding="utf-8",
    )


def test_fetches_selected_blobs_without_checkout(tmp_path):
    repo, commit = _repo(tmp_path)
    manifest = tmp_path / "manifest.yml"
    _manifest(manifest, str(repo), FINTAN_COMMIT, [
        {"source_path": "a.xlsx", "local_filename": "first.xlsx"},
        {"source_path": "nested/b.xlsx", "local_filename": "second.xlsx"},
    ])
    # Patch the supported pin so the fixture stays fully offline.
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        .replace(FINTAN_REPOSITORY, str(repo))
        .replace(FINTAN_COMMIT, commit),
        encoding="utf-8",
    )
    import specimpact.benchmarks.fintan as fintan
    original_repo, original_commit = fintan.FINTAN_REPOSITORY, fintan.FINTAN_COMMIT
    fintan.FINTAN_REPOSITORY, fintan.FINTAN_COMMIT = str(repo), commit
    try:
        output = fetch_fintan_corpus(manifest, tmp_path / "output")
    finally:
        fintan.FINTAN_REPOSITORY, fintan.FINTAN_COMMIT = original_repo, original_commit
    assert (output / "first.xlsx").read_bytes() == b"alpha"
    assert (output / "second.xlsx").read_bytes() == b"bravo"
    provenance = json.loads((output / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["commit"] == commit
    assert provenance["files"][0]["sha256"] == hashlib.sha256(b"alpha").hexdigest()


@pytest.mark.parametrize(
    "files",
    [
        [
            {"source_path": "../a.xlsx", "local_filename": "a.xlsx"},
            {"source_path": "b.xlsx", "local_filename": "b.xlsx"},
        ],
        [
            {"source_path": "a.xlsx", "local_filename": "same.xlsx"},
            {"source_path": "b.xlsx", "local_filename": "same.xlsx"},
        ],
    ],
)
def test_rejects_unsafe_or_duplicate_entries(tmp_path, files):
    manifest = tmp_path / "manifest.yml"
    _manifest(manifest, FINTAN_REPOSITORY, FINTAN_COMMIT, files)
    with pytest.raises(FintanManifestError):
        fetch_fintan_corpus(manifest, tmp_path / "output")


def test_rejects_tampered_missing_and_extra_corpus_files(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "first.xlsx").write_bytes(b"alpha")
    provenance = {
        "files": [
            {"local_filename": "first.xlsx", "sha256": hashlib.sha256(b"alpha").hexdigest()}
        ]
    }

    _validate_corpus_provenance(corpus, provenance)
    (corpus / "first.xlsx").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        _validate_corpus_provenance(corpus, provenance)
    (corpus / "first.xlsx").write_bytes(b"alpha")
    (corpus / "extra.xlsx").write_bytes(b"extra")
    with pytest.raises(ValueError, match="extra"):
        _validate_corpus_provenance(corpus, provenance)
    (corpus / "extra.xlsx").unlink()
    (corpus / "first.xlsx").unlink()
    with pytest.raises(ValueError, match="missing"):
        _validate_corpus_provenance(corpus, provenance)
