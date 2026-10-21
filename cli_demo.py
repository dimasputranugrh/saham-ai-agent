import sys
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from agents.team import (
    analyze_single_stock_with_team,
    generate_intraday_scanner_alert,
    generate_morning_dsu_report,
)

console = Console()


def main():
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "dsu"

    if cmd == "dsu":
        console.print(Panel("[bold cyan]Menjalankan Simulasi Rapat Pagi DSU (4 Karyawan AI)...[/bold cyan]"))
        report = generate_morning_dsu_report()
        console.print(Markdown(report))
    elif cmd == "scan":
        console.print(Panel("[bold green]Menjalankan Intraday Scanner ('Beli Jam Segini')...[/bold green]"))
        _, report = generate_intraday_scanner_alert(0)
        console.print(Markdown(report))
    elif cmd == "cek":
        ticker = sys.argv[2] if len(sys.argv) > 2 else "BBCA"
        console.print(Panel(f"[bold yellow]Membedah Saham {ticker.upper()} bersama 4 Karyawan AI...[/bold yellow]"))
        report = analyze_single_stock_with_team(ticker)
        console.print(Markdown(report))
    else:
        console.print(
            "[bold]Cara Pakai CLI Demo:[/bold]\n"
            "  python cli_demo.py dsu          -> Tes laporan DSU pagi\n"
            "  python cli_demo.py scan         -> Tes scanner saham terbaik jam ini\n"
            "  python cli_demo.py cek BBCA     -> Tes bedah 1 saham spesifik"
        )


if __name__ == "__main__":
    main()
