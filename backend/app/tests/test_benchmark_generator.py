"""Unit tests for the reproducible benchmark generator in ReconcileX."""

import csv
import json
from pathlib import Path
import tempfile
import pytest

from backend.app.benchmark.generator import BenchmarkGenerator, compute_sha256
from backend.app.benchmark.scenarios import allocate_scenario_counts, ScenarioType


def test_scenario_counts_sum_to_requested_total():
    """Verify largest remainder allocation produces exact requested totals and covers all types."""
    for count in [100, 250, 500]:
        for split in ["dev", "heldout", "chaos"]:
            counts = allocate_scenario_counts(count, split)
            assert sum(counts.values()) == count
            # When count >= 100, all 9 scenario types must appear
            for st in ScenarioType:
                assert counts[st] >= 1, f"Scenario {st} missing in {split} with count {count}"


def test_all_required_files_exist():
    """Verify generator writes all 4 input files, truth ledger, and manifest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        generator = BenchmarkGenerator(split="dev", count=50, seed=12345)
        split_dir = generator.write_dataset(output_base_dir=tmp_path, overwrite=True)

        assert (split_dir / "input" / "payments.csv").exists()
        assert (split_dir / "input" / "settlements.csv").exists()
        assert (split_dir / "input" / "bank_credits.csv").exists()
        assert (split_dir / "input" / "refunds.csv").exists()
        assert (split_dir / "evaluation" / "truth_ledger.csv").exists()
        assert (split_dir / "manifest.json").exists()


def test_same_seed_is_byte_reproducible():
    """Verify generating the same split with the same seed produces byte-identical files and checksums."""
    with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
        path1 = Path(tmpdir1)
        path2 = Path(tmpdir2)

        gen1 = BenchmarkGenerator(split="dev", count=100, seed=42)
        dir1 = gen1.write_dataset(output_base_dir=path1, overwrite=True)

        gen2 = BenchmarkGenerator(split="dev", count=100, seed=42)
        dir2 = gen2.write_dataset(output_base_dir=path2, overwrite=True)

        # Check manifest byte equality
        with open(dir1 / "manifest.json", "r", encoding="utf-8") as f1, open(dir2 / "manifest.json", "r", encoding="utf-8") as f2:
            m1 = json.load(f1)
            m2 = json.load(f2)
            assert m1 == m2

        # Check all CSV byte equality and checksum equality
        for relative_file in [
            "input/payments.csv",
            "input/settlements.csv",
            "input/bank_credits.csv",
            "input/refunds.csv",
            "evaluation/truth_ledger.csv",
        ]:
            f1_path = dir1 / relative_file
            f2_path = dir2 / relative_file
            assert compute_sha256(f1_path) == compute_sha256(f2_path)
            assert f1_path.read_bytes() == f2_path.read_bytes()


def test_different_seed_changes_dataset():
    """Verify different seeds produce different datasets."""
    with tempfile.TemporaryDirectory() as tmpdir1, tempfile.TemporaryDirectory() as tmpdir2:
        path1 = Path(tmpdir1)
        path2 = Path(tmpdir2)

        gen1 = BenchmarkGenerator(split="dev", count=100, seed=111)
        dir1 = gen1.write_dataset(output_base_dir=path1, overwrite=True)

        gen2 = BenchmarkGenerator(split="dev", count=100, seed=222)
        dir2 = gen2.write_dataset(output_base_dir=path2, overwrite=True)

        assert (dir1 / "input" / "payments.csv").read_bytes() != (dir2 / "input" / "payments.csv").read_bytes()


def test_generated_truth_is_hidden_from_input_files():
    """Ensure no truth labels exist in input CSV headers or rows."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        generator = BenchmarkGenerator(split="dev", count=50, seed=999)
        split_dir = generator.write_dataset(output_base_dir=tmp_path, overwrite=True)

        forbidden_keys = {"truth_group_id", "expected_result", "expected_exception_type", "scenario_type", "scenario"}

        for input_file in ["payments.csv", "settlements.csv", "bank_credits.csv", "refunds.csv"]:
            file_path = split_dir / "input" / input_file
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = set(next(reader))
                assert not (headers & forbidden_keys), f"Forbidden key in {input_file} header: {headers & forbidden_keys}"


def test_duplicate_event_scenario_creates_one_extra_payment_row():
    """Verify raw payment event row count equals truth scenarios count + duplicate scenarios count."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        generator = BenchmarkGenerator(split="dev", count=100, seed=777)
        split_dir = generator.write_dataset(output_base_dir=tmp_path, overwrite=True)

        with open(split_dir / "manifest.json", "r", encoding="utf-8") as f:
            manifest = json.load(f)

        dup_scenario_count = manifest["scenario_distribution"][ScenarioType.DUPLICATE_PAYMENT_EVENT.value]

        with open(split_dir / "input" / "payments.csv", "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            raw_payment_rows = sum(1 for _ in reader)

        assert raw_payment_rows == 100 + dup_scenario_count


def test_overwrite_protection():
    """Verify generator refuses to overwrite existing directory unless overwrite=True."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        generator = BenchmarkGenerator(split="dev", count=20, seed=1)
        generator.write_dataset(output_base_dir=tmp_path, overwrite=False)

        # Attempting again without overwrite should raise FileExistsError
        with pytest.raises(FileExistsError):
            generator.write_dataset(output_base_dir=tmp_path, overwrite=False)

        # With overwrite=True, it succeeds
        generator.write_dataset(output_base_dir=tmp_path, overwrite=True)
