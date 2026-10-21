import sys
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from agents.team import (
    analyze_single_stock_with_team,
    generate_intraday_scanner_alert,
    generate_morning_dsu_report,
    get_performance_dashboard_report,
    get_ticker_memory_report,
)
from memory.database import MemoryDatabase
from memory.learning_loop import LearningLoopOrchestrator

console = Console()


def main():
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "dsu"

    if cmd == "dsu":
        console.print(Panel("[bold cyan]Menjalankan Simulasi Rapat Pagi DSU (4 Karyawan AI + Persistent Memory)...[/bold cyan]"))
        report = generate_morning_dsu_report()
        console.print(Markdown(report))
    elif cmd == "scan":
        console.print(Panel("[bold green]Menjalankan Intraday Scanner ('Beli Jam Segini')...[/bold green]"))
        _, report = generate_intraday_scanner_alert(0)
        console.print(Markdown(report))
    elif cmd == "cek":
        ticker = sys.argv[2] if len(sys.argv) > 2 else "BBCA"
        console.print(Panel(f"[bold yellow]Membedah Saham {ticker.upper()} bersama 4 Karyawan AI + Memory Retrieval...[/bold yellow]"))
        report = analyze_single_stock_with_team(ticker)
        console.print(Markdown(report))
    elif cmd in ("evaluasi", "performa"):
        mode = sys.argv[2].upper() if len(sys.argv) > 2 else None
        console.print(Panel("[bold magenta]Menjalankan Evaluasi Prediksi & Menampilkan Dashboard Performa...[/bold magenta]"))
        report = get_performance_dashboard_report(execution_mode=mode)
        console.print(Markdown(report))
    elif cmd == "memori":
        ticker = sys.argv[2] if len(sys.argv) > 2 else "TLKM"
        console.print(Panel(f"[bold blue]Menampilkan Memori Historis & Kalibrasi untuk {ticker.upper()}...[/bold blue]"))
        report = get_ticker_memory_report(ticker)
        console.print(Markdown(report))
    elif cmd == "walkforward":
        console.print(Panel("[bold cyan]Menjalankan Walk-Forward Historical Backtest & Learning Loop...[/bold cyan]"))
        orch = LearningLoopOrchestrator()
        res = orch.run_walk_forward_backtest()
        console.print(res)
        report = get_performance_dashboard_report()
        console.print(Markdown(report))
    elif cmd == "backup":
        db = MemoryDatabase()
        target = db.backup_database()
        console.print(f"[bold green]✅ Backup database berhasil disimpan di:[/bold green] {target}")
    elif cmd == "restore":
        if len(sys.argv) < 3:
            console.print("[bold red]Harap sertakan path file backup: python cli_demo.py restore <path_backup.db>[/bold red]")
            return
        db = MemoryDatabase()
        db.restore_database(sys.argv[2])
        console.print(f"[bold green]✅ Database berhasil di-restore dari:[/bold green] {sys.argv[2]}")
    else:
        console.print(
            "[bold]Cara Pakai CLI Demo:[/bold]\n"
            "  python cli_demo.py dsu                   -> Tes laporan DSU pagi\n"
            "  python cli_demo.py scan                  -> Tes scanner saham terbaik jam ini\n"
            "  python cli_demo.py cek BBCA              -> Tes bedah 1 saham spesifik + memori\n"
            "  python cli_demo.py evaluasi              -> Jalankan evaluasi & lihat rapor performa AI\n"
            "  python cli_demo.py memori TLKM           -> Lihat memori pembelajaran pada saham tertentu\n"
            "  python cli_demo.py walkforward           -> Jalankan walk-forward backtest & self-learning\n"
            "  python cli_demo.py backup                -> Buat backup aman database SQLite\n"
            "  python cli_demo.py restore <file.db>     -> Restore database dari file backup"
        )


if __name__ == "__main__":
    main()
