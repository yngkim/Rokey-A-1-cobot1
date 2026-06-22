"""독립 실행: 페트병 뚜껑 열기."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("open_bottle", node_name="open_bottle", args=args)
    print(f"[open_bottle] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
