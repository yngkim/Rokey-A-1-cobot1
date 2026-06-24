"""독립 실행: 페트병 뚜껑 닫기."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("close_bottle", node_name="close_bottle", args=args)
    print(f"[close_bottle] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
