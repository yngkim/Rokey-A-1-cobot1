"""독립 실행: 걸레 청소."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("clean_floor", node_name="clean_floor", args=args)
    print(f"[clean_floor] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
