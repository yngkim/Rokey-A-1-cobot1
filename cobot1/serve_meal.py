"""독립 실행: 식판 가져다주기."""

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("serve_meal", node_name="serve_meal", args=args)
    print(f"[serve_meal] success={result.success} message={result.message}")
    return 0 if result.success else 1
