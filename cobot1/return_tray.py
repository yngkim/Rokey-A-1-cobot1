"""독립 실행: 식판 가져다놓기."""

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("return_tray", node_name="return_tray", args=args)
    print(f"[return_tray] success={result.success} message={result.message}")
    return 0 if result.success else 1
