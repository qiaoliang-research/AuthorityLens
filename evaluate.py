"""Run the deterministic AuthorityLens factual-coverage benchmark."""

from pathlib import Path

from benchmark.evaluator import (
    evaluate_benchmark,
    format_report,
    write_csv,
    write_markdown_report,
    write_results,
)


def main() -> None:
    report = evaluate_benchmark()
    root = Path(__file__).resolve().parent
    json_path = root / "benchmark_results.json"
    csv_path = root / "benchmark_results.csv"
    markdown_path = root / "benchmark_report.md"
    write_results(report, json_path)
    write_csv(report, csv_path)
    write_markdown_report(report, markdown_path)
    print(format_report(report))
    print(f"\nMachine-readable results: {json_path.name}, {csv_path.name}")
    print(f"Markdown report: {markdown_path.name}")


if __name__ == "__main__":
    main()
