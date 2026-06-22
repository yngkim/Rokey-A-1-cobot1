"""독립 실행: 빨대 삽입."""

import rclpy

from cobot1.task_runner import run_task


def main(args=None):
    result = run_task("insert_straw", node_name="insert_straw", args=args)
    print(f"[insert_straw] success={result.success} message={result.message}")
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
